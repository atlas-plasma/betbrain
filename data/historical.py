"""
Historical NHL Data Fetcher — uses the real NHL API to get played game results.
One API call returns 7 days, so a 3-month backtest costs ~13 calls (~2-3s).
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, List


class HistoricalNHL:
    BASE_URL = "https://api-web.nhle.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "BetBrain/1.0"})
        self._cache: Dict[str, List[Dict]] = {}  # date -> list of games

    def get_games_for_range(self, start_date: str, end_date: str) -> List[Dict]:
        """Fetch all played games between start_date and end_date (inclusive).

        Walks the date range in 7-day steps (one API call per week) and
        returns only games that have a final score.
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        games = []
        cursor = start

        while cursor <= end:
            week_games = self._fetch_week(cursor.strftime("%Y-%m-%d"))
            for g in week_games:
                game_date = g.get("date", "")
                if start_date <= game_date <= end_date:
                    games.append(g)
            # Jump a week forward
            cursor += timedelta(days=7)

        # Deduplicate by game id in case of overlapping fetches
        seen = set()
        unique = []
        for g in games:
            key = (g["date"], g["home_team"], g["away_team"])
            if key not in seen:
                seen.add(key)
                unique.append(g)

        return sorted(unique, key=lambda x: x["date"])

    def _fetch_week(self, date_str: str) -> List[Dict]:
        """Fetch one week of games from the NHL API (cached)."""
        if date_str in self._cache:
            return self._cache[date_str]

        try:
            url = f"{self.BASE_URL}/v1/schedule/{date_str}"
            resp = self.session.get(url, timeout=8)
            resp.raise_for_status()
            data = resp.json()

            games = []
            for day in data.get("gameWeek", []):
                day_date = day.get("date", "")
                for game in day.get("games", []):
                    # Only include finished games (gameState == "OFF")
                    if game.get("gameState") != "OFF":
                        continue
                    home = game.get("homeTeam", {})
                    away = game.get("awayTeam", {})
                    home_score = home.get("score", 0) or 0
                    away_score = away.get("score", 0) or 0
                    games.append({
                        "date": day_date,
                        "home_team": home.get("abbrev"),
                        "away_team": away.get("abbrev"),
                        "home_score": home_score,
                        "away_score": away_score,
                        "home_won": home_score > away_score,
                        "away_won": away_score > home_score,
                        "total_goals": home_score + away_score,
                    })

            self._cache[date_str] = games
            return games

        except Exception as e:
            print(f"  NHL API error for {date_str}: {e}")
            return []

    # Legacy compat
    def get_season_games(self, season: str = "20242025") -> List[Dict]:
        return self.get_games_for_range("2024-10-01", "2025-04-30")

    def get_historical_odds(self, game_date: str, home: str, away: str) -> Dict:
        import random
        return {
            "home_ml": round(1.5 + random.random() * 1.5, 2),
            "away_ml": round(1.5 + random.random() * 1.5, 2),
            "over": 1.909,
            "under": 1.909,
        }
