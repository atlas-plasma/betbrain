"""
Historical NHL Data Fetcher - Real backtesting data
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, List
import json


class HistoricalNHL:
    """Fetch historical NHL data for backtesting."""
    
    BASE_URL = "https://api-web.nhle.com"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "BetBrain/1.0"})
    
    def get_season_games(self, season: str = "20242025") -> List[Dict]:
        """Get all games from a season."""
        
        games = []
        
        # Get games by month
        for month in range(10, 15):  # October through April
            url = f"{self.BASE_URL}/api/clubs/schedule/{season}/{month:02d}"
            
            try:
                resp = self.session.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for week in data.get("week", []):
                        for day in week.get("day", []):
                            for game in day.get("games", []):
                                games.append(self._parse_game(game))
            except Exception as e:
                print(f"Error fetching {season}/{month}: {e}")
        
        return games
    
    def _parse_game(self, game: Dict) -> Dict:
        """Parse game data."""
        
        home = game.get("homeTeam", {})
        away = game.get("awayTeam", {})
        
        # Get score (if game played)
        home_score = game.get("homeScore", 0)
        away_score = game.get("awayScore", 0)
        
        return {
            "date": game.get("date"),
            "season": game.get("season"),
            "home_team": home.get("abbrev"),
            "away_team": away.get("abbrev"),
            "home_score": home_score,
            "away_score": away_score,
            "home_won": home_score > away_score,
            "away_won": away_score > home_score,
            "is_played": home_score > 0 or away_score > 0,
            "venue": game.get("venue", {}).get("name"),
        }
    
    def get_team_record(self, team: str, date: str) -> Dict:
        """Get team record up to a date."""
        
        # Would fetch from API in production
        return {
            "team": team,
            "date": date,
            "wins": 0,
            "losses": 0,
            "ot": 0,
            "goals_for": 0,
            "goals_against": 0,
        }
    
    def get_historical_odds(self, game_date: str, home: str, away: str) -> Dict:
        """Get historical odds (would need odds API)."""
        # Placeholder - would integrate with odds API
        import random
        return {
            "home_ml": round(1.5 + random.random() * 1.5, 2),
            "away_ml": round(1.5 + random.random() * 1.5, 2),
            "over": 1.90,
            "under": 1.90,
        }


def fetch_season(season: str = "20242025") -> List[Dict]:
    """Fetch a full season of NHL games."""
    fetcher = HistoricalNHL()
    return fetcher.get_season_games(season)


if __name__ == "__main__":
    # Test
    fetcher = HistoricalNHL()
    games = fetcher.get_season_games("20242025")
    print(f"Fetched {len(games)} games")
    for g in games[:5]:
        print(g)
