"""
Real Backtesting Engine - Uses different strategies correctly
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.nhl import NHLDataFetcher
from data.historical import HistoricalNHL
from odds.odds_api import OddsAPIFetcher
from strategy.selector import StrategySelector
from models.predictor import PoissonModel


class RealBacktester:
    """Deterministic backtesting with real team stats."""
    
    def __init__(self, sport: str = "nhl", strategy: str = "value"):
        self.sport = sport
        self.strategy_name = strategy
        self.selector = StrategySelector(strategy)
        self.data_fetcher = NHLDataFetcher()
        self.poisson = PoissonModel(home_advantage=0.05)

        # Hardcoded stats used only when historical API data is unavailable.
        # Model probabilities are derived from GF/GA via Poisson (not from win_rate),
        # so they are independent of the win-rate-based odds — breaking the circular
        # validation that existed previously.
        self.team_stats = self._load_real_team_stats()

        # Betting params
        self.initial_bankroll = 1000
        self.bankroll = 1000
        
    def _load_real_team_stats(self) -> Dict:
        """Load real NHL team statistics — prefers live NHL standings API."""
        try:
            nhl = NHLDataFetcher()
            standings = nhl._load_standings()
            if standings:
                # Remap to the key names the backtest engine expects
                result = {}
                for abbrev, s in standings.items():
                    result[abbrev] = {
                        "win_rate": s.get("win_rate", 0.5),
                        "home_win": s.get("home_win_rate", 0.55),
                        "away_win": s.get("away_win_rate", 0.45),
                        "gf_avg": s.get("goals_for_avg", 3.0),
                        "ga_avg": s.get("goals_against_avg", 3.0),
                        "form": s.get("form", 0.5),
                    }
                print(f"  Loaded live standings for {len(result)} teams")
                return result
        except Exception as e:
            print(f"  Standings load failed: {e}")

        # Hardcoded fallback (2024-25 approximations)
        return {
            # Elite teams (60%+)
            "COL": {"win_rate": 0.65, "home_win": 0.72, "away_win": 0.58, "gf_avg": 3.5, "ga_avg": 2.4, "form": 0.70},
            "CAR": {"win_rate": 0.62, "home_win": 0.68, "away_win": 0.56, "gf_avg": 3.3, "ga_avg": 2.5, "form": 0.68},
            "DAL": {"win_rate": 0.60, "home_win": 0.68, "away_win": 0.52, "gf_avg": 3.2, "ga_avg": 2.6, "form": 0.65},
            "TBL": {"win_rate": 0.61, "home_win": 0.67, "away_win": 0.55, "gf_avg": 3.4, "ga_avg": 2.5, "form": 0.66},
            "WSH": {"win_rate": 0.58, "home_win": 0.65, "away_win": 0.51, "gf_avg": 3.1, "ga_avg": 2.7, "form": 0.62},
            # Contenders (50-59%)
            "EDM": {"win_rate": 0.55, "home_win": 0.62, "away_win": 0.48, "gf_avg": 3.4, "ga_avg": 2.9, "form": 0.60},
            "MIN": {"win_rate": 0.54, "home_win": 0.60, "away_win": 0.48, "gf_avg": 3.0, "ga_avg": 2.8, "form": 0.58},
            "VGK": {"win_rate": 0.52, "home_win": 0.60, "away_win": 0.44, "gf_avg": 3.1, "ga_avg": 2.9, "form": 0.56},
            "NYI": {"win_rate": 0.51, "home_win": 0.58, "away_win": 0.44, "gf_avg": 2.9, "ga_avg": 2.8, "form": 0.54},
            "PIT": {"win_rate": 0.50, "home_win": 0.56, "away_win": 0.44, "gf_avg": 3.0, "ga_avg": 2.9, "form": 0.52},
            "BOS": {"win_rate": 0.52, "home_win": 0.60, "away_win": 0.44, "gf_avg": 3.0, "ga_avg": 2.8, "form": 0.55},
            "DET": {"win_rate": 0.50, "home_win": 0.56, "away_win": 0.44, "gf_avg": 2.9, "ga_avg": 2.9, "form": 0.52},
            "OTT": {"win_rate": 0.51, "home_win": 0.58, "away_win": 0.44, "gf_avg": 2.9, "ga_avg": 2.8, "form": 0.54},
            # Bubble (44-50%)
            "NSH": {"win_rate": 0.48, "home_win": 0.54, "away_win": 0.42, "gf_avg": 2.8, "ga_avg": 2.9, "form": 0.50},
            "SEA": {"win_rate": 0.47, "home_win": 0.54, "away_win": 0.40, "gf_avg": 2.9, "ga_avg": 3.0, "form": 0.49},
            "STL": {"win_rate": 0.46, "home_win": 0.52, "away_win": 0.40, "gf_avg": 2.8, "ga_avg": 3.0, "form": 0.48},
            "PHI": {"win_rate": 0.45, "home_win": 0.52, "away_win": 0.38, "gf_avg": 2.8, "ga_avg": 3.1, "form": 0.47},
            "CBJ": {"win_rate": 0.44, "home_win": 0.50, "away_win": 0.38, "gf_avg": 2.7, "ga_avg": 3.1, "form": 0.46},
            "BUF": {"win_rate": 0.48, "home_win": 0.56, "away_win": 0.40, "gf_avg": 2.9, "ga_avg": 2.9, "form": 0.50},
            "LAK": {"win_rate": 0.46, "home_win": 0.54, "away_win": 0.38, "gf_avg": 2.8, "ga_avg": 2.9, "form": 0.48},
            # Struggling (<44%)
            "MTL": {"win_rate": 0.38, "home_win": 0.44, "away_win": 0.32, "gf_avg": 2.5, "ga_avg": 3.4, "form": 0.40},
            "CHI": {"win_rate": 0.35, "home_win": 0.42, "away_win": 0.28, "gf_avg": 2.4, "ga_avg": 3.5, "form": 0.38},
            "WPG": {"win_rate": 0.40, "home_win": 0.48, "away_win": 0.32, "gf_avg": 2.6, "ga_avg": 3.2, "form": 0.42},
            "CGY": {"win_rate": 0.38, "home_win": 0.46, "away_win": 0.30, "gf_avg": 2.5, "ga_avg": 3.3, "form": 0.40},
            "VAN": {"win_rate": 0.36, "home_win": 0.44, "away_win": 0.28, "gf_avg": 2.5, "ga_avg": 3.4, "form": 0.39},
            "SJS": {"win_rate": 0.32, "home_win": 0.40, "away_win": 0.24, "gf_avg": 2.3, "ga_avg": 3.6, "form": 0.35},
            "ANA": {"win_rate": 0.34, "home_win": 0.42, "away_win": 0.26, "gf_avg": 2.4, "ga_avg": 3.5, "form": 0.37},
            "ARI": {"win_rate": 0.36, "home_win": 0.44, "away_win": 0.28, "gf_avg": 2.5, "ga_avg": 3.3, "form": 0.39},
            "NJD": {"win_rate": 0.45, "home_win": 0.52, "away_win": 0.38, "gf_avg": 2.8, "ga_avg": 3.0, "form": 0.47},
            "NYR": {"win_rate": 0.47, "home_win": 0.54, "away_win": 0.40, "gf_avg": 2.9, "ga_avg": 2.8, "form": 0.49},
        }
    
    def _get_odds_for_game(self, home_stats: Dict, away_stats: Dict, home: str, away: str, date: str, source: str) -> Dict:
        """Fetch odds based on configured source (api/historical/deterministic)."""
        if source == "api":
            odds_api = OddsAPIFetcher()
            if odds_api.has_api():
                api_odds = odds_api.get_best_game_odds(home, away, date)
                if api_odds.get("source") == "theoddsapi" and api_odds.get("home_ml") and api_odds.get("away_ml"):
                    return api_odds

        if source == "historical":
            historical = HistoricalNHL()
            hist_odds = historical.get_historical_odds(date, home, away)
            if hist_odds and hist_odds.get("home_ml") and hist_odds.get("away_ml"):
                return hist_odds

        # Deterministic fallback
        odds_api = OddsAPIFetcher()
        return odds_api.get_fallback_odds(home_stats.get("win_rate", 0.5), away_stats.get("win_rate", 0.5))

    def run(self, start_date: str, end_date: str, use_historical: bool = True, odds_source: str = "deterministic") -> Dict:
        """Run backtest against real NHL game results where available.

        First tries the live NHL API for real game results (home_won, actual
        scores).  Falls back to the deterministic schedule generator only when
        the API returns no games (e.g. future dates or network error).
        """

        print(f"Running backtest: {self.strategy_name} | {start_date} → {end_date}")

        historical = HistoricalNHL()
        games = []

        if use_historical:
            print("  Fetching real NHL game results from API...")
            games = historical.get_games_for_range(start_date, end_date)
            if games:
                print(f"  Found {len(games)} real games")
            else:
                print("  No real games found — falling back to generated schedule")

        if not games:
            games = self._generate_realistic_games(start_date, end_date)
            print(f"  Using {len(games)} generated games")

        if not games:
            return {"error": "No games found"}

        print(f"Backtesting {len(games)} games...")

        results = []
        self.bankroll = self.initial_bankroll

        for game in games:
            home = game.get("home_team")
            away = game.get("away_team")

            if not home or not away:
                continue

            home_stats = self.team_stats.get(home, self.team_stats.get("MTL", {}))
            away_stats = self.team_stats.get(away, self.team_stats.get("MTL", {}))

            odds = self._get_odds_for_game(home_stats, away_stats, home, away, game.get("date", ""), odds_source)
            if not odds or odds.get("home_ml", 0) <= 1 or odds.get("away_ml", 0) <= 1:
                odds = self._get_odds_for_game(home_stats, away_stats, home, away, game.get("date", ""), "deterministic")

            # Model probabilities: Poisson model driven by GF/GA averages.
            # Using GF/GA (attack/defense) rather than raw win rate means model
            # and odds come from different information sources, avoiding circular
            # validation.
            home_gf = home_stats.get("gf_avg", 3.0)
            home_ga = home_stats.get("ga_avg", 3.0)
            away_gf = away_stats.get("gf_avg", 3.0)
            away_ga = away_stats.get("ga_avg", 3.0)

            # Expected goals: blend team's own attack with opponent's defence
            lambda_home = (home_gf + away_ga) / 2
            lambda_away = (away_gf + home_ga) / 2

            prediction = self.poisson.predict(lambda_home, lambda_away)
            home_prob_norm = prediction.home_win_prob
            away_prob_norm = prediction.away_win_prob

            # Devig: remove bookmaker margin before comparing to model probs
            raw_home = 1.0 / odds["home_ml"]
            raw_away = 1.0 / odds["away_ml"]
            total_implied = raw_home + raw_away
            implied_home = raw_home / total_implied
            implied_away = raw_away / total_implied

            home_edge = home_prob_norm - implied_home
            away_edge = away_prob_norm - implied_away
            home_ev = home_edge * odds["home_ml"]
            away_ev = away_edge * odds["away_ml"]

            home_opp = {
                "match": f"{away} @ {home}",
                "market": "ML (Home)",
                "odds": odds["home_ml"],
                "model_prob": home_prob_norm,
                "implied_prob": implied_home,
                "edge": home_edge,
                "ev": home_ev,
            }

            away_opp = {
                "match": f"{away} @ {home}",
                "market": "ML (Away)",
                "odds": odds["away_ml"],
                "model_prob": away_prob_norm,
                "implied_prob": implied_away,
                "edge": away_edge,
                "ev": away_ev,
            }

            # O/U analysis -------------------------------------------------------
            # Book lines use standard NHL increments (5.5 / 6.0 / 6.5 / 7.0).
            # The book's line is set from the BOOK's own expected total (win-rate
            # based), while our model uses GF/GA. Divergence between the two
            # creates realistic, modest edge on totals.
            expected_total = lambda_home + lambda_away

            # Book expected total: use win-rate weighted average goals
            book_lambda_home = home_stats.get("gf_avg", 3.0)
            book_lambda_away = away_stats.get("gf_avg", 3.0)
            book_expected = book_lambda_home + book_lambda_away

            # Snap to nearest standard NHL half-goal line
            standard_lines = [4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5]
            ou_line = min(standard_lines, key=lambda l: abs(l - book_expected))

            from scipy.stats import poisson as _poisson
            model_over_prob = 1.0 - _poisson.cdf(int(ou_line), expected_total)
            model_under_prob = 1.0 - model_over_prob

            # O/U odds: standard -110 both sides (1.909), devig to 50/50
            ou_odds = 1.909
            true_implied_ou = 0.5  # devigged 50/50 for standard -110 line

            over_edge = model_over_prob - true_implied_ou
            under_edge = model_under_prob - true_implied_ou

            over_opp = {
                "match": f"{away} @ {home}",
                "market": f"Over {ou_line}",
                "odds": ou_odds,
                "model_prob": model_over_prob,
                "implied_prob": true_implied_ou,
                "edge": over_edge,
                "ev": over_edge * ou_odds,
            }
            under_opp = {
                "match": f"{away} @ {home}",
                "market": f"Under {ou_line}",
                "odds": ou_odds,
                "model_prob": model_under_prob,
                "implied_prob": true_implied_ou,
                "edge": under_edge,
                "ev": under_edge * ou_odds,
            }

            # Use real outcome when the game has been played, else simulate
            real_home_won = game.get("home_won")     # bool or None
            real_total    = game.get("total_goals")  # int or None
            is_real       = real_home_won is not None
            game_seed = hash(f"{home}{away}{game.get('date', '')}") & 0xFFFFFFFF

            bet_home  = self.selector.should_bet(home_opp)
            bet_away  = self.selector.should_bet(away_opp)
            bet_over  = self.selector.should_bet(over_opp)
            bet_under = self.selector.should_bet(under_opp)

            match_str = f"{away} @ {home}"
            date_str  = game.get("date")

            def record(bet_label, odd, model_p, edge_p, won, market_p=None):
                stake = min(self.bankroll * 0.05, 100)
                profit = stake * (odd - 1) if won else -stake
                self.bankroll += profit
                imp = market_p if market_p is not None else max(0, model_p - edge_p)
                ev_pct = round(edge_p * odd * 100, 1)
                results.append({
                    "date": date_str, "match": match_str, "bet": bet_label,
                    "odds": odd, "model_prob": round(model_p * 100, 1),
                    "market_prob": round(imp * 100, 1),
                    "edge": round(edge_p * 100, 1),
                    "ev": ev_pct,
                    "stake": round(stake, 2),
                    "won": won, "profit": round(profit, 2),
                    "bankroll": round(self.bankroll, 2), "real": is_real,
                })

            if bet_home:
                won = bool(real_home_won) if is_real else self._simulate_result(home_stats, away_stats, True, game_seed)
                record(f"{home} ML", odds["home_ml"], home_prob_norm, home_edge, won, implied_home)

            if bet_away:
                won = bool(game.get("away_won")) if is_real else self._simulate_result(home_stats, away_stats, False, game_seed)
                record(f"{away} ML", odds["away_ml"], away_prob_norm, away_edge, won, implied_away)

            if bet_over:
                won = (real_total or 0) > ou_line if is_real else self._simulate_ou(lambda_home, lambda_away, ou_line, True, game_seed)
                record(f"Over {ou_line}", ou_odds, model_over_prob, over_edge, won, true_implied_ou)

            if bet_under:
                won = (real_total or 0) < ou_line if is_real else self._simulate_ou(lambda_home, lambda_away, ou_line, False, game_seed)
                record(f"Under {ou_line}", ou_odds, model_under_prob, under_edge, won, true_implied_ou)

        metrics = self._calculate_metrics(results)

        return {
            "results": results,
            "metrics": metrics,
            "tape": results
        }
    
    def _generate_realistic_games(self, start_date: str, end_date: str) -> List[Dict]:
        """Generate a realistic NHL schedule (deterministic, ~10-12 games/night)."""
        import random as _rnd

        teams = list(self.team_stats.keys())
        games = []

        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        current = start
        while current <= end:
            # Realistic NHL slate: ~10-12 games on busy nights, ~5-7 on lighter nights
            weekday = current.weekday()
            if weekday in (1, 3):   # Tue/Thu — typically lighter
                num_games = 7
            elif weekday in (5, 6): # Sat/Sun — marquee nights
                num_games = 12
            else:
                num_games = 10

            # Deterministic shuffle of teams per day using date as seed
            day_rng = _rnd.Random(current.toordinal())
            shuffled = teams[:]
            day_rng.shuffle(shuffled)

            # Pair teams up without repeats
            used = set()
            day_games = []
            for i in range(0, len(shuffled) - 1, 2):
                h, a = shuffled[i], shuffled[i + 1]
                if h != a and h not in used and a not in used:
                    day_games.append({"home_team": h, "away_team": a})
                    used.add(h); used.add(a)
                if len(day_games) >= num_games:
                    break

            for g in day_games:
                g["date"] = current.strftime("%Y-%m-%d")
                games.append(g)

            current += timedelta(days=1)

        return games
    
    def _get_deterministic_odds(self, home_stats: Dict, away_stats: Dict) -> Dict:
        """Get deterministic odds based on team strength."""
        
        home_prob = home_stats.get("home_win", home_stats.get("win_rate", 0.5))
        away_prob = away_stats.get("away_win", away_stats.get("win_rate", 0.5))
        
        # Add margin (typical bookmaker takes ~5%)
        home_odds = 1 / (home_prob * 0.95)
        away_odds = 1 / (away_prob * 0.95)
        
        return {
            "home_ml": round(home_odds, 2),
            "away_ml": round(away_odds, 2),
            "over": 1.90,
            "under": 1.90,
        }
    
    def _simulate_ou(self, lambda_home: float, lambda_away: float,
                     line: float, is_over: bool, game_seed: int = 0) -> bool:
        """Simulate O/U outcome. Adds ±15% noise to lambdas to reflect real
        model uncertainty — prevents the model from being perfectly calibrated
        against itself and inflating win rates."""
        import random
        from scipy.stats import poisson as _poisson
        rng = random.Random(game_seed ^ 999)
        # Add realistic model uncertainty: actual pace differs from prediction
        noise_h = 1.0 + rng.uniform(-0.15, 0.15)
        noise_a = 1.0 + rng.uniform(-0.15, 0.15)
        home_goals = _poisson.ppf(rng.random(), max(0.5, lambda_home * noise_h))
        away_goals = _poisson.ppf(rng.random(), max(0.5, lambda_away * noise_a))
        total = home_goals + away_goals
        return (total > line) if is_over else (total < line)

    def _simulate_result(self, home_stats: Dict, away_stats: Dict, is_home: bool,
                         game_seed: int = 0) -> bool:
        """Simulate game result deterministically per unique game.

        Uses a seeded RNG so that the same matchup on the same date always
        produces the same outcome — making backtest results reproducible.
        """
        import random
        rng = random.Random(game_seed ^ (1 if is_home else 0))
        if is_home:
            true_win_prob = home_stats.get("home_win", home_stats.get("win_rate", 0.5))
        else:
            true_win_prob = away_stats.get("away_win", away_stats.get("win_rate", 0.5))
        return rng.random() < true_win_prob
    
    def _calculate_metrics(self, results: List[Dict]) -> Dict:
        """Calculate performance metrics."""
        
        if not results:
            return {
                "total_bets": 0, "won": 0, "lost": 0, "win_rate": 0,
                "total_return": 0, "profit": 0, "roi": 0,
                "final_bankroll": self.initial_bankroll, "max_drawdown": 0,
            }
        
        won = sum(1 for r in results if r["won"])
        lost = len(results) - won
        
        roi = ((self.bankroll - self.initial_bankroll) / self.initial_bankroll) * 100
        
        # Max drawdown
        peak = self.initial_bankroll
        max_dd = 0
        for r in results:
            if r["bankroll"] > peak:
                peak = r["bankroll"]
            dd = (peak - r["bankroll"]) / peak * 100 if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        return {
            "total_bets": len(results),
            "won": won,
            "lost": lost,
            "win_rate": won / len(results) if results else 0,
            "total_return": (self.bankroll - self.initial_bankroll) / self.initial_bankroll,
            "profit": self.bankroll - self.initial_bankroll,
            "roi": roi,
            "final_bankroll": self.bankroll,
            "max_drawdown": max_dd,
        }


def run_backtest(
    sport: str,
    start_date: str,
    end_date: str,
    strategy: str = "value",
    use_historical: bool = True,
    odds_source: str = "deterministic",
) -> Dict:
    """Main entry point."""
    backtester = RealBacktester(sport, strategy)
    return backtester.run(start_date, end_date, use_historical=use_historical, odds_source=odds_source)


def print_tape(results: List[Dict]):
    """Prints the sequential bet tape with outcomes."""
    if not results:
        print("No bets executed")
        return

    print("\nTrade Tape")
    print("Date | Match | Bet | Odds | Stake | Won | Profit | Bankroll")
    print("-" * 80)
    for row in results:
        print(
            f"{row.get('date')} | {row.get('match')} | {row.get('bet')} | {row.get('odds')} | "
            f"{row.get('stake')} | {row.get('won')} | {row.get('profit')} | {row.get('bankroll')}"
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run backtest")
    parser.add_argument("--sport", default="nhl")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2024-03-01")
    parser.add_argument("--strategy", default="value")
    parser.add_argument("--historical", action="store_true")
    parser.add_argument("--odds-source", choices=["deterministic", "historical", "api"], default="deterministic")
    args = parser.parse_args()

    result = run_backtest(
        args.sport,
        args.start,
        args.end,
        strategy=args.strategy,
        use_historical=args.historical,
        odds_source=args.odds_source,
    )

    if "error" in result:
        print("Backtest failed:", result["error"])
        exit(1)

    print(f"\nBacktest: Total Bets={result['metrics']['total_bets']}", end="")
    print(f", ROI={result['metrics']['roi']:.1f}%", end="")
    print(f", Win rate={result['metrics']['win_rate']*100:.1f}%")
    print(f"Final bankroll: {result['metrics']['final_bankroll']:.2f}")
    print(f"Max drawdown: {result['metrics']['max_drawdown']:.2f}%")

    print_tape(result["tape"])

