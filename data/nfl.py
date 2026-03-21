"""NFL Data Fetcher stub.

This module is provisioned for future NFL support.
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, List


class NFLDataFetcher:
    """Fetch NFL data from public endpoints when available."""

    BASE_URL = "https://api.sportsdata.io/v3/nfl/scores/json"

    def __init__(self, api_key: str = None):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "BetBrain/1.0"})
        self.api_key = api_key

    def _headers(self):
        return {"Ocp-Apim-Subscription-Key": self.api_key} if self.api_key else {}

    def get_schedule(self, season: str, week: int) -> List[Dict]:
        """Fetch NFL schedule for a given season and week."""
        if not self.api_key:
            raise ValueError("NFL API key required")

        url = f"{self.BASE_URL}/Games/{season}/{week}"
        resp = self.session.get(url, headers=self._headers(), timeout=10)
        resp.raise_for_status()

        games = []
        for game in resp.json():
            games.append({
                "date": game.get("Day"),
                "home_team": game.get("HomeTeam"),
                "away_team": game.get("AwayTeam"),
                "start_time": game.get("DateTime"),
            })
        return games
