"""
NHL Advanced Stats Fetcher.

Pulls goalie quality, PDO, back-to-back detection, home/away true splits,
L10 form, Pythagorean expectation, streak momentum — everything needed
for a research-grade prediction model.

All data comes from the free NHL API (no auth required).
Results are cached per session to minimise API calls.
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

LEAGUE_AVG_SV  = 0.908   # NHL 2024-25 league average save %
LEAGUE_AVG_SH  = 0.097   # NHL 2024-25 league average shooting %
LEAGUE_AVG_GF  = 3.03    # NHL 2024-25 average goals for per game
LEAGUE_AVG_GA  = 3.03    # same (symmetric)
HOME_WIN_RATE  = 0.548   # historical NHL home win rate


class NHLAdvancedStats:
    """One-stop shop for rich team analytics."""

    BASE = "https://api-web.nhle.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "BetBrain/1.0"})
        self._club_stats_cache: Dict[str, Dict] = {}
        self._schedule_cache:   Dict[str, list] = {}
        self._standings_cache:  Dict[str, Dict] = {}
        self._ou_cache:         Dict[str, Dict] = {}
        self._h2h_cache:        Dict[tuple, Dict] = {}

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #

    def enrich(self, team_abbr: str, game_date: str, standings: Dict) -> Dict:
        """
        Return an enriched stats dict for a team.
        Merges base standings data with:
          - goalie quality (save%, GAA, GSAA)
          - team shooting % → PDO
          - home / away true splits
          - L10 weighted form
          - Pythagorean win expectation
          - back-to-back flag
          - streak momentum
        """
        base = standings.get(team_abbr, {})
        club = self._get_club_stats(team_abbr)

        # -- Goaltender quality --
        goalie = self._primary_goalie(club)
        goalie_sv  = goalie.get("sv", LEAGUE_AVG_SV)
        goalie_gaa = goalie.get("gaa", LEAGUE_AVG_GF)
        shots_per_game = (club.get("shots_against_total", 0) /
                          max(1, club.get("goalie_gp", 1)))
        gsaa_per_game = (goalie_sv - LEAGUE_AVG_SV) * shots_per_game

        # -- Team shooting % and PDO --
        sh_pct = club.get("team_sh_pct", LEAGUE_AVG_SH)
        pdo = (sh_pct + goalie_sv) * 100  # league avg ≈ 100

        # -- Home / away true splits (now stored directly from _load_standings) --
        true_home_wr = base.get("home_win_rate", base.get("win_rate", 0.5) + 0.05)
        true_away_wr = base.get("away_win_rate", base.get("win_rate", 0.5) - 0.05)

        # -- L10 form (more predictive than full season) --
        l10_gf = base.get("l10_gf_avg", base.get("goals_for_avg",  LEAGUE_AVG_GF))
        l10_ga = base.get("l10_ga_avg", base.get("goals_against_avg", LEAGUE_AVG_GA))
        l10_wr = base.get("l10_win_rate", base.get("win_rate", 0.5))

        # -- Full-season averages --
        full_gf = base.get("goals_for_avg",  LEAGUE_AVG_GF)
        full_ga = base.get("goals_against_avg", LEAGUE_AVG_GA)
        full_wr = base.get("win_rate", 0.5)
        full_gp = max(1, base.get("games_played", 1))

        # Blend: 65% L10, 35% full season (L10 is more predictive)
        blended_gf = 0.65 * l10_gf + 0.35 * full_gf
        blended_ga = 0.65 * l10_ga + 0.35 * full_ga
        blended_wr = 0.65 * l10_wr + 0.35 * full_wr

        # -- Pythagorean win expectation --
        pyth = (full_gf ** 2) / max(1e-6, (full_gf ** 2 + full_ga ** 2))

        # -- Regulation quality --
        reg_wr   = base.get("reg_win_rate", full_wr)
        ot_heavy = base.get("shootout_wins", 0) / full_gp

        # -- Streak momentum --
        streak_code  = base.get("streak_code", "")
        streak_count = base.get("streak_count", 0)
        streak_signal = 0.0
        if streak_code == "W":
            streak_signal = min(0.04, streak_count * 0.008)
        elif streak_code in ("L", "OT"):
            streak_signal = -min(0.04, streak_count * 0.008)

        # -- Back-to-back detection --
        b2b, b2b_home = self._is_back_to_back(team_abbr, game_date)

        # -- Special teams --
        pp_pct = base.get("powerplay_pct", club.get("pp_pct", 20))
        pk_pct = base.get("penalty_kill_pct", club.get("pk_pct", 80))

        # -- Tier, style, and O/U hit rate --
        gf_avg = blended_gf
        ga_avg = blended_ga
        tier        = self._get_team_tier(full_wr)
        style       = self._get_team_style(gf_avg, ga_avg)
        ou_hit_rate = self._get_ou_hit_rate(team_abbr, 5.5)

        return {
            # Existing fields (compatibility with base pipeline)
            "team": team_abbr,
            "games_played": full_gp,
            "wins": base.get("wins", 0),
            "win_rate": full_wr,
            "home_win_rate": true_home_wr,
            "away_win_rate": true_away_wr,
            "goals_for_avg": blended_gf,
            "goals_against_avg": blended_ga,
            "form": blended_wr,
            "powerplay_pct": pp_pct,
            "penalty_kill_pct": pk_pct,
            "save_pct": goalie_sv,

            # New advanced fields
            "goalie_name":     goalie.get("name", "Unknown"),
            "goalie_sv_pct":   round(goalie_sv, 4),
            "goalie_gaa":      round(goalie_gaa, 3),
            "goalie_gsaa_pg":  round(gsaa_per_game, 3),
            "team_sh_pct":     round(sh_pct, 4),
            "pdo":             round(pdo, 2),
            "pdo_label":       _pdo_label(pdo),

            "l10_gf":          round(l10_gf, 3),
            "l10_ga":          round(l10_ga, 3),
            "l10_win_rate":    round(l10_wr, 3),

            "pyth_win_pct":    round(pyth, 4),
            "reg_win_rate":    round(reg_wr, 4),
            "ot_heavy":        round(ot_heavy, 3),

            "streak_code":     streak_code,
            "streak_count":    streak_count,
            "streak_signal":   round(streak_signal, 4),

            "back_to_back":    b2b,
            "b2b_is_home":     b2b_home,

            # Raw numbers for debugging
            "full_gf": round(full_gf, 3),
            "full_ga": round(full_ga, 3),

            # Tier, style, O/U hit rate
            "tier":        tier,
            "style":       style,
            "ou_hit_rate": ou_hit_rate,
        }

    def enrich_historical(self, team_abbr: str, game_date: str, standings: Dict) -> Dict:
        """
        Point-in-time enrichment for backtesting — NO look-ahead.

        Uses only the standings data for the specific game_date (passed in as
        a dict already fetched via /v1/standings/{date}).  Goalie save% and
        team shooting% are estimated from goals data because the NHL API has
        no point-in-time club-stats endpoint:

          estimated_sv_pct  = 1 - (GA_avg / NHL_AVG_SHOTS_PER_GAME)
          estimated_sh_pct  = GF_avg / NHL_AVG_SHOTS_PER_GAME

        ~30 shots per game is the well-established NHL average; the estimates
        are unbiased approximations with no future information.
        """
        NHL_AVG_SHOTS = 30.0   # NHL average shots on goal per team per game

        base = standings.get(team_abbr, {})

        full_gf = base.get("goals_for_avg",  LEAGUE_AVG_GF)
        full_ga = base.get("goals_against_avg", LEAGUE_AVG_GA)
        full_wr = base.get("win_rate", 0.5)
        full_gp = max(1, base.get("games_played", 1))

        # Estimate goalie sv% and team sh% from goals data (no future info)
        sh_pct    = max(0.070, min(0.140, full_gf / NHL_AVG_SHOTS))
        goalie_sv = max(0.870, min(0.940, 1.0 - full_ga / NHL_AVG_SHOTS))
        pdo       = (sh_pct + goalie_sv) * 100

        gsaa_per_game = (goalie_sv - LEAGUE_AVG_SV) * NHL_AVG_SHOTS

        # Home / away splits
        true_home_wr = base.get("home_win_rate", full_wr + 0.05)
        true_away_wr = base.get("away_win_rate", full_wr - 0.05)

        # L10 form
        l10_gf = base.get("l10_gf_avg", full_gf)
        l10_ga = base.get("l10_ga_avg", full_ga)
        l10_wr = base.get("l10_win_rate", full_wr)

        blended_gf = 0.65 * l10_gf + 0.35 * full_gf
        blended_ga = 0.65 * l10_ga + 0.35 * full_ga
        blended_wr = 0.65 * l10_wr + 0.35 * full_wr

        # Pythagorean
        pyth = (full_gf ** 2) / max(1e-6, (full_gf ** 2 + full_ga ** 2))

        reg_wr   = base.get("reg_win_rate", full_wr)
        ot_heavy = base.get("shootout_wins", 0) / full_gp

        # Streak momentum
        streak_code  = base.get("streak_code", "")
        streak_count = base.get("streak_count", 0)
        streak_signal = 0.0
        if streak_code == "W":
            streak_signal = min(0.04, streak_count * 0.008)
        elif streak_code in ("L", "OT"):
            streak_signal = -min(0.04, streak_count * 0.008)

        # Back-to-back (checks schedule for yesterday's game — no look-ahead)
        b2b, b2b_home = self._is_back_to_back(team_abbr, game_date)

        pp_pct = base.get("powerplay_pct", 20)
        pk_pct = base.get("penalty_kill_pct", 80)

        # -- Tier and style (no live O/U lookup for historical) --
        tier  = self._get_team_tier(full_wr)
        style = self._get_team_style(blended_gf, blended_ga)
        _default_ou = {"over_pct": 0.5, "under_pct": 0.5, "avg_total": 5.8, "sample": 0}

        return {
            "team":              team_abbr,
            "games_played":      full_gp,
            "wins":              base.get("wins", 0),
            "win_rate":          full_wr,
            "home_win_rate":     true_home_wr,
            "away_win_rate":     true_away_wr,
            "goals_for_avg":     blended_gf,
            "goals_against_avg": blended_ga,
            "form":              blended_wr,
            "powerplay_pct":     pp_pct,
            "penalty_kill_pct":  pk_pct,
            "save_pct":          goalie_sv,
            # Advanced (estimated, no look-ahead)
            "goalie_name":       "Est.",
            "goalie_sv_pct":     round(goalie_sv, 4),
            "goalie_gaa":        round(full_ga, 3),
            "goalie_gsaa_pg":    round(gsaa_per_game, 3),
            "team_sh_pct":       round(sh_pct, 4),
            "pdo":               round(pdo, 2),
            "pdo_label":         _pdo_label(pdo),
            "l10_gf":            round(l10_gf, 3),
            "l10_ga":            round(l10_ga, 3),
            "l10_win_rate":      round(l10_wr, 3),
            "pyth_win_pct":      round(pyth, 4),
            "reg_win_rate":      round(reg_wr, 4),
            "ot_heavy":          round(ot_heavy, 3),
            "streak_code":       streak_code,
            "streak_count":      streak_count,
            "streak_signal":     round(streak_signal, 4),
            "back_to_back":      b2b,
            "b2b_is_home":       b2b_home,
            "full_gf":           round(full_gf, 3),
            "full_ga":           round(full_ga, 3),
            # Tier, style, O/U hit rate (default for historical)
            "tier":        tier,
            "style":       style,
            "ou_hit_rate": _default_ou,
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_team_tier(win_rate: float) -> str:
        if win_rate >= 0.60:
            return "elite"
        elif win_rate >= 0.50:
            return "contender"
        elif win_rate >= 0.44:
            return "bubble"
        return "struggling"

    @staticmethod
    def _get_team_style(gf_avg: float, ga_avg: float) -> str:
        if gf_avg >= 3.4 and ga_avg >= 3.2:
            return "high_scoring"
        elif gf_avg >= 3.4 and ga_avg < 3.2:
            return "offensive"
        elif gf_avg < 3.0 and ga_avg < 3.0:
            return "defensive"
        return "balanced"

    def _get_ou_hit_rate(self, team: str, ou_line: float = 5.5) -> dict:
        """Fetch last 10 completed games and compute O/U hit rate."""
        _default = {"over_pct": 0.5, "under_pct": 0.5, "avg_total": 5.8, "sample": 0}
        cache_key = (team, ou_line)
        if cache_key in self._ou_cache:
            return self._ou_cache[cache_key]
        try:
            r = self.session.get(
                f"{self.BASE}/v1/club-schedule-season/{team}/now", timeout=8
            )
            if r.status_code != 200:
                return _default
            games = r.json().get("games", [])
            completed = [
                g for g in games
                if g.get("gameState") in ("OFF", "FINAL")
            ]
            last10 = completed[-10:]
            if not last10:
                return _default
            totals = [
                g.get("homeTeam", {}).get("score", 0) + g.get("awayTeam", {}).get("score", 0)
                for g in last10
            ]
            over_count  = sum(1 for t in totals if t > ou_line)
            under_count = sum(1 for t in totals if t < ou_line)
            n = len(totals)
            result = {
                "over_pct":  round(over_count / n, 4),
                "under_pct": round(under_count / n, 4),
                "avg_total": round(sum(totals) / n, 2),
                "sample":    n,
            }
            self._ou_cache[cache_key] = result
            return result
        except Exception as e:
            print(f"  [adv] ou-hit-rate error {team}: {e}")
            return _default

    def get_h2h(self, home: str, away: str) -> Dict:
        """Return head-to-head record between home and away teams this season."""
        _default = {
            "h2h_games": 0, "home_wins": 0, "away_wins": 0,
            "home_win_pct": 0.5, "avg_total": 5.8, "sample": 0,
        }
        cache_key = (home, away)
        if cache_key in self._h2h_cache:
            return self._h2h_cache[cache_key]
        try:
            games = self._get_team_schedule(home)
            completed = [
                g for g in games
                if g.get("gameState") in ("OFF", "FINAL")
            ]
            h2h_games = []
            for g in completed:
                h_team = g.get("homeTeam", {}).get("abbrev", "")
                a_team = g.get("awayTeam", {}).get("abbrev", "")
                if away not in (h_team, a_team):
                    continue
                h2h_games.append(g)

            if not h2h_games:
                self._h2h_cache[cache_key] = _default
                return _default

            home_wins = 0
            away_wins = 0
            totals = []
            for g in h2h_games:
                h_team = g.get("homeTeam", {}).get("abbrev", "")
                a_team = g.get("awayTeam", {}).get("abbrev", "")
                h_score = g.get("homeTeam", {}).get("score", 0)
                a_score = g.get("awayTeam", {}).get("score", 0)
                if h_team == home:
                    won = h_score > a_score
                else:
                    won = a_score > h_score
                if won:
                    home_wins += 1
                else:
                    away_wins += 1
                totals.append(h_score + a_score)

            n = len(h2h_games)
            result = {
                "h2h_games":    n,
                "home_wins":    home_wins,
                "away_wins":    away_wins,
                "home_win_pct": round(home_wins / n, 4) if n > 0 else 0.5,
                "avg_total":    round(sum(totals) / n, 2) if totals else 5.8,
                "sample":       n,
            }
            self._h2h_cache[cache_key] = result
            return result
        except Exception as e:
            print(f"  [adv] h2h error {home}/{away}: {e}")
            return _default

    def _get_club_stats(self, abbrev: str) -> Dict:
        if abbrev in self._club_stats_cache:
            return self._club_stats_cache[abbrev]
        try:
            r = self.session.get(f"{self.BASE}/v1/club-stats/{abbrev}/now", timeout=8)
            if r.status_code == 200:
                d = r.json()
                skaters = d.get("skaters", [])
                goalies = d.get("goalies", [])
                # Team shooting %
                total_goals = sum(s.get("goals", 0) for s in skaters)
                total_shots = sum(s.get("shots", 0) for s in skaters) or 1
                sh_pct = total_goals / total_shots

                # Goalie aggregate for shots_against total
                shots_against_total = sum(g.get("shotsAgainst", 0) for g in goalies)
                goalie_gp = sum(g.get("gamesStarted", 0) for g in goalies) or 1

                result = {
                    "team_sh_pct": sh_pct,
                    "shots_against_total": shots_against_total,
                    "goalie_gp": goalie_gp,
                    "goalies": goalies,
                }
                self._club_stats_cache[abbrev] = result
                return result
        except Exception as e:
            print(f"  [adv] club-stats error {abbrev}: {e}")
        return {}

    def _primary_goalie(self, club: Dict) -> Dict:
        """Return stats for the goalie with the most starts."""
        goalies = club.get("goalies", [])
        if not goalies:
            return {}
        # Pick most-started goalie with at least 5 starts
        starters = [g for g in goalies if g.get("gamesStarted", 0) >= 5]
        if not starters:
            starters = goalies
        best = max(starters, key=lambda g: g.get("gamesStarted", 0))
        fname = best.get("firstName", {})
        lname = best.get("lastName", {})
        name = f"{fname.get('default','')} {lname.get('default','')}".strip()
        return {
            "name": name,
            "sv":   best.get("savePercentage", LEAGUE_AVG_SV),
            "gaa":  best.get("goalsAgainstAverage", LEAGUE_AVG_GF),
            "gp":   best.get("gamesStarted", 0),
        }

    def _get_team_schedule(self, abbrev: str) -> list:
        """Current-season schedule (used for live analysis only)."""
        if abbrev in self._schedule_cache:
            return self._schedule_cache[abbrev]
        try:
            r = self.session.get(
                f"{self.BASE}/v1/club-schedule-season/{abbrev}/now", timeout=8
            )
            if r.status_code == 200:
                games = r.json().get("games", [])
                self._schedule_cache[abbrev] = games
                return games
        except Exception as e:
            print(f"  [adv] schedule error {abbrev}: {e}")
        return []

    def _get_games_on_date(self, date_str: str) -> list:
        """Fetch all finished games on a specific date (historical-safe)."""
        cache_key = f"_date_games_{date_str}"
        if hasattr(self, cache_key):
            return getattr(self, cache_key)
        games = []
        try:
            r = self.session.get(f"{self.BASE}/v1/schedule/{date_str}", timeout=8)
            if r.status_code == 200:
                for day in r.json().get("gameWeek", []):
                    if day.get("date") != date_str:
                        continue
                    for g in day.get("games", []):
                        if g.get("gameState") in ("OFF", "FINAL"):
                            games.append(g)
        except Exception as e:
            print(f"  [adv] date-schedule error {date_str}: {e}")
        setattr(self, cache_key, games)
        return games

    def _is_back_to_back(self, abbrev: str, game_date: str) -> tuple[bool, Optional[bool]]:
        """
        Returns (is_b2b, is_home_in_this_game).
        Uses the historical schedule API so backtests work correctly for any season.
        """
        try:
            target = datetime.strptime(game_date, "%Y-%m-%d").date()
            yesterday = (target - timedelta(days=1)).strftime("%Y-%m-%d")
            games = self._get_games_on_date(yesterday)
            for g in games:
                home = g.get("homeTeam", {}).get("abbrev", "")
                away = g.get("awayTeam", {}).get("abbrev", "")
                if home == abbrev or away == abbrev:
                    was_home_yesterday = (home == abbrev)
                    return True, was_home_yesterday
        except Exception:
            pass
        return False, None


def _pdo_label(pdo: float) -> str:
    if pdo >= 103:
        return "very_lucky"
    elif pdo >= 101.5:
        return "lucky"
    elif pdo <= 97:
        return "very_unlucky"
    elif pdo <= 98.5:
        return "unlucky"
    return "neutral"
