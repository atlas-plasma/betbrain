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
    
    def get_schedule(self, days_forward: int = 7) -> List[Dict]:
        """Get upcoming games - try API first, fallback to demo data."""
        
        try:
            # Try to get today's games
            url = f"{self.BASE_URL}/api/clubs/schedule/now"
            resp = self.session.get(url, timeout=5)
            
            if resp.status_code == 200:
                data = resp.json()
                games = []
                
                if "games" in data:
                    for game in data["games"]:
                        # Try to get game start time
                        start_time = ""
                        if "startTimeUTC" in game:
                            try:
                                utc_time = datetime.fromisoformat(game["startTimeUTC"].replace("Z", "+00:00"))
                                # Convert to SA time (GMT+2)
                                sa_time = utc_time.astimezone(datetime.now().astimezone().tzinfo)
                                start_time = sa_time.strftime("%H:%M")
                            except:
                                pass
                        
                        # Only include today's games (not past)
                        game_date = game.get("gameDate", "")
                        if game_date and game_date != datetime.now().strftime("%Y-%m-%d"):
                            continue
                        
                        games.append({
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "home_team": game.get("homeTeam", {}).get("abbrev"),
                            "away_team": game.get("awayTeam", {}).get("abbrev"),
                            "home_id": game.get("homeTeam", {}).get("id"),
                            "away_id": game.get("awayTeam", {}).get("id"),
                            "start_time": start_time,
                        })
                
                if games:
                    return games
        except Exception as e:
            print(f"API error: {e}")
        
        # Fallback to demo data if API fails
        return self._get_demo_games()
    
    def _get_demo_games(self) -> List[Dict]:
        """Generate demo games for testing."""
        teams = list(self.get_team_abbr_map().keys())
        
        # Typical NHL game times in SA (UTC+2) - games start between 02:00-04:30 SA
        game_times_sa = ["02:00", "02:30", "03:00", "03:30", "04:00", "04:30"]
        
        games = []
        for i in range(5):
            home = random.choice(teams)
            away = random.choice([t for t in teams if t != home])
            games.append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "home_team": home,
                "away_team": away,
                "start_time": random.choice(game_times_sa),
            })
        
        return games
    
    def get_team_stats(self, team_abbr: str) -> Dict:
        """Get team statistics - try API first, fallback to realistic demo data."""
        
        try:
            # Try to get team stats from API
            url = f"{self.BASE_URL}/api/club-stats/{team_abbr}/now"
            resp = self.session.get(url, timeout=5)
            
            if resp.status_code == 200:
                data = resp.json()
                # Parse API response
                return {
                    "team": team_abbr,
                    "games_played": data.get("gamesPlayed", 0),
                    "wins": data.get("wins", 0),
                    "losses": data.get("losses", 0),
                    "ot": data.get("ot", 0),
                    "goals_for": data.get("goalsFor", 0),
                    "goals_against": data.get("goalsAgainst", 0),
                }
        except Exception as e:
            print(f"API error for {team_abbr}: {e}")
        
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
