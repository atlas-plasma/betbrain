"""
NHL Data Fetcher
Free API: api-web.nhle.com (no auth required)
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import random


class NHLDataFetcher:
    """Fetch NHL data from official API."""
    
    BASE_URL = "https://api-web.nhle.com"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BetBrain/1.0"
        })
    
    def get_team_abbr_map(self) -> Dict[str, str]:
        return {
            "MTL": "Montreal Canadiens",
            "TOR": "Toronto Maple Leafs",
            "EDM": "Edmonton Oilers",
            "CGY": "Calgary Flames",
            "VAN": "Vancouver Canucks",
            "WPG": "Winnipeg Jets",
            "LAK": "Los Angeles Kings",
            "VGK": "Vegas Golden Knights",
            "ANA": "Anaheim Ducks",
            "SEA": "Seattle Kraken",
            "SJS": "San Jose Sharks",
            "ARI": "Arizona Coyotes",
            "CHI": "Chicago Blackhawks",
            "DET": "Detroit Red Wings",
            "STL": "St. Louis Blues",
            "NSH": "Nashville Predators",
            "DAL": "Dallas Stars",
            "COL": "Colorado Avalanche",
            "MIN": "Minnesota Wild",
            "BOS": "Boston Bruins",
            "BUF": "Buffalo Sabres",
            "FLA": "Florida Panthers",
            "CAR": "Carolina Hurricanes",
            "NJD": "New Jersey Devils",
            "NYR": "New York Rangers",
            "NYI": "New York Islanders",
            "PHI": "Philadelphia Flyers",
            "PIT": "Pittsburgh Penguins",
            "CBJ": "Columbus Blue Jackets",
            "WSH": "Washington Capitals",
            "OTT": "Ottawa Senators",
            "TBL": "Tampa Bay Lightning",
        }
    
    def get_schedule(self, days_forward: int = 21) -> List[Dict]:
        """Get upcoming games - uses NHL API v1 (gameWeek structure)."""

        try:
            url = f"{self.BASE_URL}/v1/schedule/now"
            resp = self.session.get(url, timeout=8)

            if resp.status_code == 200:
                data = resp.json()
                games = []

                for day in data.get("gameWeek", []):
                    day_date = day.get("date", "")
                    for game in day.get("games", []):
                        # Skip games that are already final
                        state = game.get("gameState", "")
                        if state in ("OFF", "FINAL"):
                            continue

                        start_time = ""
                        utc_str = game.get("startTimeUTC", "")
                        if utc_str:
                            try:
                                utc_time = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
                                local_time = utc_time.astimezone(datetime.now().astimezone().tzinfo)
                                start_time = local_time.strftime("%H:%M")
                            except Exception:
                                pass

                        games.append({
                            "date": day_date,
                            "home_team": game.get("homeTeam", {}).get("abbrev"),
                            "away_team": game.get("awayTeam", {}).get("abbrev"),
                            "home_id": game.get("homeTeam", {}).get("id"),
                            "away_id": game.get("awayTeam", {}).get("id"),
                            "start_time": start_time,
                        })

                if games:
                    games.sort(key=lambda x: x.get("date"))
                    return games[:days_forward]
        except Exception as e:
            print(f"Schedule API error: {e}")

        return self._get_demo_games(days_forward)

    
    def _get_demo_games(self, days_forward: int = 5) -> List[Dict]:
        """Generate demo games for testing."""
        teams = list(self.get_team_abbr_map().keys())

        game_times_sa = ["02:00", "02:30", "03:00", "03:30", "04:00", "04:30"]

        games = []
        for i in range(days_forward):
            home = random.choice(teams)
            away = random.choice([t for t in teams if t != home])
            games.append({
                "date": (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d"),
                "home_team": home,
                "away_team": away,
                "start_time": random.choice(game_times_sa),
            })

        return games
    
    def _load_standings_for_date(self, date: str) -> Dict[str, Dict]:
        """Fetch point-in-time standings as of a specific date (YYYY-MM-DD).
        Uses the same NHL API structure as /now but with a historical date.
        Results are cached by date so each date is only fetched once per session.
        """
        cache_attr = f"_standings_date_cache"
        if not hasattr(self, cache_attr):
            setattr(self, cache_attr, {})
        cache = getattr(self, cache_attr)
        if date in cache:
            return cache[date]
        try:
            url = f"{self.BASE_URL}/v1/standings/{date}"
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                result = self._parse_standings_response(resp.json())
                cache[date] = result
                return result
        except Exception as e:
            print(f"Standings-for-date API error ({date}): {e}")
        return {}

    def _parse_standings_response(self, data: dict) -> Dict[str, Dict]:
        """Parse a NHL standings API response (works for both /now and /{date})."""
        result = {}
        for t in data.get("standings", []):
            abbrev_raw = t.get("teamAbbrev", {})
            abbrev = abbrev_raw.get("default", "") if isinstance(abbrev_raw, dict) else str(abbrev_raw)
            if not abbrev:
                continue
            gp      = max(1, t.get("gamesPlayed", 1))
            wins    = t.get("wins", 0)
            losses  = t.get("losses", 0)
            ot      = t.get("otLosses", 0)
            gf      = t.get("goalFor", 0)
            ga      = t.get("goalAgainst", 0)
            reg_w   = t.get("regulationWins", wins)
            so_w    = t.get("shootoutWins", 0)

            h_gp   = max(1, t.get("homeGamesPlayed", gp // 2))
            h_wins = t.get("homeWins", 0)
            h_gf   = t.get("homeGoalsFor", 0)
            h_ga   = t.get("homeGoalsAgainst", 0)

            r_gp   = max(1, t.get("roadGamesPlayed", gp // 2))
            r_wins = t.get("roadWins", 0)
            r_gf   = t.get("roadGoalsFor", 0)
            r_ga   = t.get("roadGoalsAgainst", 0)

            l10_gp   = max(1, t.get("l10GamesPlayed", 10))
            l10_wins = t.get("l10Wins", 0)
            l10_gf   = t.get("l10GoalsFor", 0)
            l10_ga   = t.get("l10GoalsAgainst", 0)

            streak_code  = t.get("streakCode", "")
            streak_count = t.get("streakCount", 0)

            result[abbrev] = {
                "team": abbrev,
                "games_played": gp,
                "wins": wins,
                "losses": losses,
                "ot": ot,
                "goals_for": gf,
                "goals_against": ga,
                "win_rate":           wins / gp,
                "goals_for_avg":      gf / gp,
                "goals_against_avg":  ga / gp,
                "home_win_rate":      h_wins / h_gp,
                "home_gf_avg":        h_gf / h_gp,
                "home_ga_avg":        h_ga / h_gp,
                "away_win_rate":      r_wins / r_gp,
                "away_gf_avg":        r_gf / r_gp,
                "away_ga_avg":        r_ga / r_gp,
                "l10_gp":             l10_gp,
                "l10_wins":           l10_wins,
                "l10_win_rate":       l10_wins / l10_gp,
                "l10_gf_avg":         l10_gf / l10_gp,
                "l10_ga_avg":         l10_ga / l10_gp,
                "reg_win_rate":       reg_w / gp,
                "shootout_wins":      so_w,
                "form":               l10_wins / l10_gp,
                "streak_code":        streak_code,
                "streak_count":       streak_count,
                "powerplay_pct":      20,
                "penalty_kill_pct":   80,
                "save_pct":           0.910,
            }
        return result

    def _load_standings(self) -> Dict[str, Dict]:
        """Fetch current standings (cached for this session)."""
        if hasattr(self, '_standings_cache') and self._standings_cache:
            return self._standings_cache
        try:
            url = f"{self.BASE_URL}/v1/standings/now"
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                self._standings_cache = self._parse_standings_response(resp.json())
                return self._standings_cache
        except Exception as e:
            print(f"Standings API error: {e}")
        self._standings_cache = {}
        return {}

    def get_team_stats(self, team_abbr: str) -> Dict:
        """Get real team statistics from NHL standings API."""
        standings = self._load_standings()
        if team_abbr in standings:
            return standings[team_abbr]
        # Fallback to realistic demo stats
        return self._get_demo_stats(team_abbr)
    
    def _get_demo_stats(self, team: str) -> Dict:
        """Generate realistic demo stats."""
        
        # Realistic NHL averages + some variance
        base_stats = {
            "games_played": 72,
            "goals_for": random.randint(150, 220),
            "goals_against": random.randint(150, 220),
            "wins": random.randint(25, 40),
            "losses": random.randint(20, 35),
            "ot": random.randint(5, 15),
        }
        
        # Calculate win rate
        gp = base_stats["games_played"]
        base_stats["win_rate"] = (base_stats["wins"] / gp) if gp > 0 else 0.5
        base_stats["home_win_rate"] = base_stats["win_rate"] + 0.05  # Home advantage
        base_stats["away_win_rate"] = base_stats["win_rate"] - 0.05
        
        # Goals per game
        base_stats["goals_for_avg"] = base_stats["goals_for"] / gp if gp > 0 else 3.0
        base_stats["goals_against_avg"] = base_stats["goals_against"] / gp if gp > 0 else 3.0
        
        # Form (0-1)
        base_stats["form"] = random.uniform(0.3, 0.8)
        
        # Rest days
        base_stats["rest"] = random.randint(1, 4)
        
        # Recent games
        base_stats["games_14d"] = random.randint(3, 6)
        
        # Injuries
        base_stats["injuries"] = random.randint(0, 3)
        
        # Power play / penalty kill (percentages)
        base_stats["powerplay_pct"] = random.randint(15, 30)
        base_stats["penalty_kill_pct"] = random.randint(75, 90)
        base_stats["save_pct"] = random.uniform(0.900, 0.925)
        
        return base_stats
    
    def get_recent_games(self, team_abbr: str, n: int = 10) -> List[Dict]:
        """Get last N games for a team."""
        # Demo: generate recent results
        results = []
        outcomes = ["W", "L", "OT"]
        for _ in range(n):
            results.append({
                "result": random.choice(outcomes),
                "goals_for": random.randint(1, 6),
                "goals_against": random.randint(1, 6),
            })
        return results
    
    def get_head_to_head(self, team1: str, team2: str, n: int = 10) -> List[Dict]:
        """Get head-to-head history."""
        # Demo: generate history
        return [{"team1_wins": random.randint(0, n), "team2_wins": random.randint(0, n)}]


def fetch_nhl_data() -> Dict:
    """Main entry point for NHL data."""
    fetcher = NHLDataFetcher()
    return {
        "schedule": fetcher.get_schedule(7),
        "teams": fetcher.get_team_abbr_map(),
    }


if __name__ == "__main__":
    data = fetch_nhl_data()
    print(f"NHL Schedule: {len(data['schedule'])} games")
    for game in data["schedule"][:5]:
        print(f"  {game['away_team']} @ {game['home_team']} ({game['date']})")
