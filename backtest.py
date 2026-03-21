"""
Backtesting Engine — uses the same StatisticalAgent as the analysis page.

The model that runs live (PDO, goaltender quality, B2B, L10-weighted form,
Pythagorean expectation) is exactly what gets backtested here. No separate
"backtest model" — one model, tested honestly.

For historical games we use current-season team stats as a proxy
(we don't have point-in-time PDO/goalie splits from the past, so we use
today's calibration as an approximation). Real game OUTCOMES come from the
NHL API — wins, losses, total goals are all real.
"""

import sys
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.nhl import NHLDataFetcher
from data.nhl_advanced import NHLAdvancedStats
from data.historical import HistoricalNHL
from odds.odds_api import OddsAPIFetcher
from strategy.selector import StrategySelector
from agents.statistical import StatisticalAgent
import sqlite3
import cache.backtest_cache as backtest_cache

DB_PATH = PROJECT_ROOT / "betbrain.db"

def _load_real_odds(start_date: str, end_date: str) -> Dict:
    """Load real historical odds from SBRO data keyed by (date, home, away)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT date,home,away,home_ml,away_ml,ou_line,home_score,away_score,total "
            "FROM historical_odds WHERE date>=? AND date<=?",
            (start_date, end_date)
        ).fetchall()
        conn.close()
        return {
            (r[0], r[1], r[2]): {
                "home_ml": r[3], "away_ml": r[4], "ou_line": r[5] or 6.0,
                "home_score": r[6], "away_score": r[7], "total": r[8],
                "source": "sbro_real",
            }
            for r in rows
        }
    except Exception as e:
        print(f"  [real odds] DB error: {e}")
        return {}


_OU_LINES = [4.5, 5.5, 6.5, 7.5]


def _snap_ou(expected: float) -> float:
    return min(_OU_LINES, key=lambda x: abs(x - expected))


def _devig(odds_a: float, odds_b: float):
    raw_a, raw_b = 1.0 / odds_a, 1.0 / odds_b
    total = raw_a + raw_b
    return raw_a / total, raw_b / total


def _ev(model_prob: float, odds: float) -> float:
    return model_prob * (odds - 1) - (1 - model_prob)


def _kelly(model_prob: float, odds: float, fraction: float = 0.25) -> float:
    b = odds - 1
    if b <= 0 or model_prob <= 0:
        return 0.0
    q = 1 - model_prob
    f = (b * model_prob - q) / b
    return max(0.0, min(0.05, f * fraction))


class Backtester:

    INITIAL_BANKROLL = 1000.0

    def __init__(self, strategy: str = "value"):
        self.strategy_name = strategy
        self.selector      = StrategySelector(strategy)
        self.agent         = StatisticalAgent()
        self.odds_api      = OddsAPIFetcher()
        self.nhl           = NHLDataFetcher()
        self.adv           = NHLAdvancedStats()

        # Stats are loaded per game date (point-in-time) — no pre-loading here
        self._date_stats_cache: Dict[str, Dict[str, Dict]] = {}

        self.bankroll = self.INITIAL_BANKROLL

    def _stats_for_date(self, date: str) -> Dict[str, Dict]:
        """
        Return enriched team stats as of a specific historical date.
        Uses /v1/standings/{date} so every feature (win_rate, L10, GF/GA,
        streak, splits) reflects only information available on that date.
        Goalie SV% is estimated from GA data — no /now endpoints called.
        Results are cached so each date triggers only one API call.
        """
        if date in self._date_stats_cache:
            return self._date_stats_cache[date]

        print(f"  Loading point-in-time standings for {date}...")
        standings = self.nhl._load_standings_for_date(date)

        if not standings:
            # Fall back to current standings if date is too early / API gap
            standings = self.nhl._load_standings()

        stats: Dict[str, Dict] = {}
        for abbrev in standings:
            enriched = self.adv.enrich_historical(abbrev, date, standings)
            # Merge any remaining base fields not in enriched
            for k, v in standings[abbrev].items():
                if k not in enriched:
                    enriched[k] = v
            stats[abbrev] = enriched

        self._date_stats_cache[date] = stats
        return stats

    # ------------------------------------------------------------------ #

    def run(self, start_date: str, end_date: str, use_historical: bool = True) -> Dict:
        print(f"Backtest: {self.strategy_name} | {start_date} → {end_date}")

        # Fetch real game results
        games = []
        if use_historical:
            print("  Fetching real NHL results from API...")
            games = HistoricalNHL().get_games_for_range(start_date, end_date)
            print(f"  {len(games)} real games found")

        if not games:
            games = self._generate_games(start_date, end_date)
            print(f"  Using {len(games)} generated games")

        if not games:
            return {"error": "No games found for this date range"}

        self.bankroll = self.INITIAL_BANKROLL
        results = []

        # Load real historical odds for this date range (if we have them)
        real_odds_map = _load_real_odds(start_date, end_date)
        real_odds_count = len(real_odds_map)
        print(f"  Real odds available: {real_odds_count} games from SBRO")

        for game in games:
            home = game.get("home_team")
            away = game.get("away_team")
            if not home or not away:
                continue

            # Point-in-time stats: only data available on the game date
            game_date = game.get("date", "")
            date_stats = self._stats_for_date(game_date) if game_date else {}
            home_stats = date_stats.get(home) or self._default_stats(home)
            away_stats = date_stats.get(away) or self._default_stats(away)

            MIN_GP = 10
            if (home_stats.get("games_played", 0) < MIN_GP or
                    away_stats.get("games_played", 0) < MIN_GP):
                continue

            # ----- Odds: real SBRO if available, synthetic fallback otherwise -----
            real = real_odds_map.get((game_date, home, away))
            if real:
                home_ml  = real["home_ml"]
                away_ml  = real["away_ml"]
                ou_odds  = 1.909
                ou_line  = real["ou_line"]
                odds_src = "sbro_real"
                # Override game outcome with SBRO's recorded score if NHL API didn't provide it
                if game.get("home_won") is None and real.get("total") is not None:
                    game = {**game,
                            "home_won": (real["home_score"] or 0) > (real["away_score"] or 0),
                            "total_goals": real["total"]}
            else:
                fb = self.odds_api.get_fallback_odds(home_stats, away_stats)
                home_ml  = fb["home_ml"]
                away_ml  = fb["away_ml"]
                ou_odds  = 1.909
                odds_src = "synthetic"
            # ----- Model probabilities -----
            # First pass: get expected lambdas to snap the O/U line
            if not real:
                vote_preview = self.agent.analyze(home, away, home_stats, away_stats, ou_line=6.5)
                h_lam = vote_preview.extra.get("home_lambda", 3.0)
                a_lam = vote_preview.extra.get("away_lambda", 3.0)
                ou_line = _snap_ou(h_lam + a_lam)

            vote = self.agent.analyze(home, away, home_stats, away_stats, ou_line=ou_line)
            home_win = vote.home_win_prob
            away_win = vote.away_win_prob
            over_p   = vote.over_prob

            # ----- Devig -----
            impl_home, impl_away  = _devig(home_ml, away_ml)
            impl_over, impl_under = _devig(ou_odds, ou_odds)  # both 1.909

            home_edge = home_win - impl_home
            away_edge = away_win - impl_away
            over_edge  = over_p - impl_over
            under_edge = (1 - over_p) - impl_under

            # ----- Build opportunity dicts for strategy selector -----
            base = {
                "home_team":      home,
                "away_team":      away,
                "confidence":     "high" if max(home_win, away_win) > 0.60 else "medium",
                "home_pdo":       home_stats.get("pdo", 100),
                "away_pdo":       away_stats.get("pdo", 100),
                "home_pdo_label": home_stats.get("pdo_label", "neutral"),
                "away_pdo_label": away_stats.get("pdo_label", "neutral"),
                "home_b2b":       home_stats.get("back_to_back", False),
                "away_b2b":       away_stats.get("back_to_back", False),
                "home_goalie_sv": home_stats.get("goalie_sv_pct", 0.908) * 100,
                "away_goalie_sv": away_stats.get("goalie_sv_pct", 0.908) * 100,
            }

            home_opp = {**base, "win_pick": home, "market": "Moneyline",
                        "edge": home_edge, "model_prob": home_win,
                        "kelly": _kelly(home_win, home_ml)}
            away_opp = {**base, "win_pick": away, "market": "Moneyline",
                        "edge": away_edge, "model_prob": away_win,
                        "kelly": _kelly(away_win, away_ml)}
            over_opp = {**base, "win_pick": f"Over {ou_line}",
                        "market": f"Over {ou_line}",
                        "edge": over_edge, "model_prob": over_p,
                        "kelly": _kelly(over_p, ou_odds)}
            under_opp = {**base, "win_pick": f"Under {ou_line}",
                         "market": f"Under {ou_line}",
                         "edge": under_edge, "model_prob": 1 - over_p,
                         "kelly": _kelly(1 - over_p, ou_odds)}

            # ----- Outcomes -----
            real_home_won = game.get("home_won")
            real_total    = game.get("total_goals")
            is_real       = real_home_won is not None
            seed = hash(f"{home}{away}{game.get('date', '')}") & 0xFFFFFFFF

            match_str = f"{away} @ {home}"
            date_str  = game.get("date", "")

            def record(label, odds_val, model_p, impl_p, edge_val, won, market_str=""):
                stake  = min(self.bankroll * 0.05, 100)
                profit = round(stake * (odds_val - 1) if won else -stake, 2)
                self.bankroll = round(self.bankroll + profit, 2)
                nonlocal odds_src
                results.append({
                    "date":        date_str,
                    "match":       match_str,
                    "bet":         label,
                    "market":      market_str or label,
                    "odds":        odds_val,
                    "model_prob":  round(model_p * 100, 1),
                    "market_prob": round(impl_p * 100, 1),
                    "edge":        round(edge_val * 100, 1),
                    "ev":          round(_ev(model_p, odds_val) * 100, 1),
                    "stake":       round(stake, 2),
                    "won":         won,
                    "profit":      profit,
                    "bankroll":    self.bankroll,
                    "real":        is_real,
                    "odds_source": odds_src,
                })

            if self.selector.should_bet(home_opp):
                won = bool(real_home_won) if is_real else (
                    random.Random(seed).random() < home_win)
                record(f"{home} ML", home_ml, home_win, impl_home, home_edge, won, "Moneyline")

            if self.selector.should_bet(away_opp):
                won = not bool(real_home_won) if is_real else (
                    random.Random(seed ^ 1).random() < away_win)
                record(f"{away} ML", away_ml, away_win, impl_away, away_edge, won, "Moneyline")

            if self.selector.should_bet(over_opp):
                won = (real_total or 0) > ou_line if is_real else (
                    random.Random(seed ^ 2).random() < over_p)
                record(f"Over {ou_line}", ou_odds, over_p, impl_over, over_edge, won, f"Over {ou_line}")

            if self.selector.should_bet(under_opp):
                won = (real_total or 0) < ou_line if is_real else (
                    random.Random(seed ^ 3).random() < (1 - over_p))
                record(f"Under {ou_line}", ou_odds, 1 - over_p, impl_under, under_edge, won, f"Under {ou_line}")

        return {
            "results": results,
            "metrics": self._metrics(results),
        }

    # ------------------------------------------------------------------ #

    def _metrics(self, results: List[Dict]) -> Dict:
        if not results:
            return {"total_bets": 0, "won": 0, "lost": 0, "win_rate": 0,
                    "profit": 0, "roi": 0, "final_bankroll": self.INITIAL_BANKROLL,
                    "max_drawdown": 0, "by_month": []}
        won  = sum(1 for r in results if r["won"])
        lost = len(results) - won
        roi  = (self.bankroll - self.INITIAL_BANKROLL) / self.INITIAL_BANKROLL * 100
        peak = self.INITIAL_BANKROLL
        max_dd = 0
        for r in results:
            peak = max(peak, r["bankroll"])
            dd = (peak - r["bankroll"]) / peak * 100
            max_dd = max(max_dd, dd)

        # Per-month breakdown — lets you see where edge actually comes from
        months: Dict[str, Dict] = {}
        for r in results:
            month = r.get("date", "")[:7]  # "YYYY-MM"
            if month not in months:
                months[month] = {"bets": 0, "won": 0, "profit": 0.0}
            months[month]["bets"]   += 1
            months[month]["won"]    += int(r["won"])
            months[month]["profit"] += r["profit"]

        by_month = [
            {
                "month":    m,
                "bets":     v["bets"],
                "won":      v["won"],
                "win_rate": round(v["won"] / v["bets"], 3) if v["bets"] else 0,
                "profit":   round(v["profit"], 2),
                "roi":      round(v["profit"] / (v["bets"] * 50) * 100, 1) if v["bets"] else 0,
            }
            for m, v in sorted(months.items())
        ]

        # ---- Calibration: does model confidence match actual win rate? ----
        # Group bets into confidence bands. A well-calibrated model should
        # show actual win rate ≈ predicted probability in each band.
        # This is completely independent of odds quality — pure signal test.
        bands = [
            ("50–55%", 0.50, 0.55),
            ("55–60%", 0.55, 0.60),
            ("60–65%", 0.60, 0.65),
            ("65–70%", 0.65, 0.70),
            ("70%+",   0.70, 1.01),
        ]
        calibration = []
        for label, lo, hi in bands:
            bucket = [r for r in results if lo <= r["model_prob"] / 100 < hi]
            if not bucket:
                continue
            avg_pred  = sum(r["model_prob"] / 100 for r in bucket) / len(bucket)
            actual_wr = sum(1 for r in bucket if r["won"]) / len(bucket)
            breakeven = sum(1 / r["odds"] for r in bucket) / len(bucket)
            calibration.append({
                "band":      label,
                "bets":      len(bucket),
                "predicted": round(avg_pred * 100, 1),
                "actual":    round(actual_wr * 100, 1),
                "breakeven": round(breakeven * 100, 1),
                "edge":      round((actual_wr - breakeven) * 100, 1),
            })

        return {
            "total_bets":     len(results),
            "won":            won,
            "lost":           lost,
            "win_rate":       won / len(results),
            "profit":         round(self.bankroll - self.INITIAL_BANKROLL, 2),
            "roi":            round(roi, 2),
            "final_bankroll": round(self.bankroll, 2),
            "max_drawdown":   round(max_dd, 2),
            "by_month":       by_month,
            "calibration":    calibration,
        }

    def _default_stats(self, team: str) -> Dict:
        return {
            "win_rate": 0.5, "home_win_rate": 0.55, "away_win_rate": 0.45,
            "goals_for_avg": 3.0, "goals_against_avg": 3.0,
            "l10_gf_avg": 3.0, "l10_ga_avg": 3.0, "l10_win_rate": 0.5,
            "pdo": 100.0, "pdo_label": "neutral",
            "goalie_sv_pct": 0.908, "goalie_gsaa_pg": 0.0,
            "pyth_win_pct": 0.5, "reg_win_rate": 0.5,
            "streak_signal": 0.0, "back_to_back": False,
            "goalie_name": "Unknown",
        }

    def _generate_games(self, start_date: str, end_date: str) -> List[Dict]:
        """Deterministic fallback schedule."""
        teams = list(self.team_stats.keys()) or [
            "BOS","TOR","NYR","MTL","EDM","COL","CAR","DAL",
            "FLA","TBL","VGK","MIN","WSH","BUF","PIT","PHI",
        ]
        games = []
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end   = datetime.strptime(end_date, "%Y-%m-%d")
        cur   = start
        while cur <= end:
            rng = random.Random(cur.toordinal())
            shuffled = teams[:]
            rng.shuffle(shuffled)
            count = {1: 7, 3: 7, 5: 12, 6: 12}.get(cur.weekday(), 10)
            used = set()
            for i in range(0, len(shuffled) - 1, 2):
                h, a = shuffled[i], shuffled[i + 1]
                if h not in used and a not in used and h != a:
                    games.append({"home_team": h, "away_team": a,
                                  "date": cur.strftime("%Y-%m-%d")})
                    used.add(h); used.add(a)
                if len([g for g in games if g["date"] == cur.strftime("%Y-%m-%d")]) >= count:
                    break
            cur += timedelta(days=1)
        return games


# ------------------------------------------------------------------ #
# Public entry point
# ------------------------------------------------------------------ #

def run_backtest(
    sport: str,
    start_date: str,
    end_date: str,
    strategy: str = "value",
    use_historical: bool = True,
    force_rerun: bool = False,
    **_kwargs,
) -> Dict:
    if not force_rerun:
        cached = backtest_cache.load(strategy, start_date, end_date)
        if cached:
            print(f"[cache] HIT  {strategy} {start_date}→{end_date} (cached {cached.get('_cached_at')})")
            return cached

    print(f"[cache] MISS {strategy} {start_date}→{end_date} — running backtest...")
    bt = Backtester(strategy=strategy)
    result = bt.run(start_date, end_date, use_historical=use_historical)

    if "error" not in result:
        backtest_cache.save(strategy, start_date, end_date, result)
        print(f"[cache] SAVED {strategy} {start_date}→{end_date}")

    return result
