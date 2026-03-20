"""
NHL Data Fetcher
Free API: api-web.nhle.com (no auth required)
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd


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
            "PHX": "Arizona Coyotes",
            "CHI": "Chicago Blackhawks",
            "DET": "Detroit Red Wings",
            "STL": "St. Louis Blues",
            "NSH": "Nashville Predators",
            "DAL": "Dallas Stars",
            "COL": "Colorado Avalanche",
            "MIN": "Minnesota Wild",
            "BOS": "Boston Bruins",
            "BUF": "Buffalo Sabres",
            "DET": "Detroit Red Wings",
            "FLA": "Florida Panthers",
            "CAR": "Carolina Hurricanes",
            "NJ": "New Jersey Devils",
            "NYR": "New York Rangers",
            "NYI": "New York Islanders",
            "PHI": "Philadelphia Flyers",
            "PIT": "Pittsburgh Penguins",
            "CBJ": "Columbus Blue Jackets",
            "WSH": "Washington Capitals",
            "OTT": "Ottawa Senators",
            "TBL": "Tampa Bay Lightning",
            "MON": "Montréal Canadiens",
        }
    
    def get_schedule(self, days_forward: int = 7) -> List[Dict]:
        """Get upcoming games."""
        end_date = datetime.now() + timedelta(days=days_forward)
        
        games = []
        current = datetime.now()
        
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            url = f"{self.BASE_URL}/api/clubs/schedule/now/{date_str}"
            
            try:
                resp = self.session.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if "games" in data:
                        for game in data["games"]:
                            games.append({
                                "date": date_str,
                                "home_team": game.get("homeTeam", {}).get("abbrev"),
                                "away_team": game.get("awayTeam", {}).get("abbrev"),
                                "home_id": game.get("homeTeam", {}).get("id"),
                                "away_id": game.get("awayTeam", {}).get("id"),
                            })
            except Exception as e:
                print(f"Error fetching {date_str}: {e}")
            
            current += timedelta(days=1)
        
        return games
    
    def get_team_stats(self, team_abbr: str) -> Dict:
        """Get team statistics for current season."""
        # Simplified - would need proper API endpoint
        return {
            "team": team_abbr,
            "games_played": 0,
            "wins": 0,
            "losses": 0,
            "ot": 0,
            "points": 0,
            "goals_for": 0,
            "goals_against": 0,
            "home_record": "",
            "away_record": "",
        }
    
    def get_recent_games(self, team_abbr: str, n: int = 10) -> List[Dict]:
        """Get last N games for a team."""
        # In production, would fetch from API
        # For now, return structure
        return []
    
    def get_head_to_head(self, team1: str, team2: str, n: int = 10) -> List[Dict]:
        """Get head-to-head history."""
        return []
    
    def get_player_stats(self, team_id: int) -> Dict:
        """Get key player stats (injuries, etc)."""
        return {"injuries": [], "key_players_out": []}


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
