"""Odds API utility for pulling bookmaker odds data."""

import os
import requests
from typing import List, Dict, Optional


class OddsAPIFetcher:
    """Fetch odds from TheOddsAPI or fallback to deterministic odds."""

    BASE_URL = "https://api.the-odds-api.com/v4/sports"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ODDS_API_KEY", "")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "BetBrain/1.0"})

    def has_api(self) -> bool:
        return bool(self.api_key)

    def get_market_odds(self, sport: str = "icehockey_nhl", region: str = "us", market: str = "h2h", date_format: str = "iso") -> List[Dict]:
        if not self.has_api():
            raise RuntimeError("Odds API key is not configured")

        url = f"{self.BASE_URL}/{sport}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": region,
            "markets": market,
            "oddsFormat": "decimal",
            "dateFormat": date_format,
        }

        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_best_game_odds(self, home: str, away: str, game_date: str = None) -> Dict:
        """Find odds for a specific matchup."""
        if not self.has_api():
            raise RuntimeError("Odds API key is not configured")

        try:
            games = self.get_market_odds()

            def normalize_team(n: str):
                return n.strip().lower() if n else ""

            best = None
            for game in games:
                h = normalize_team(game.get("home_team"))
                a = normalize_team(game.get("away_team"))
                if h == normalize_team(home) and a == normalize_team(away):
                    # choose first site with head-to-head odds
                    for site in game.get("bookmakers", []):
                        for market in site.get("markets", []):
                            if market.get("key") == "h2h":
                                outcomes = market.get("outcomes", [])
                                odds = {o.get("name"): o.get("price") for o in outcomes}
                                if "home" in odds and "away" in odds:
                                    return {
                                        "home_ml": odds.get("home"),
                                        "away_ml": odds.get("away"),
                                        "over": odds.get("over", 1.90),
                                        "under": odds.get("under", 1.90),
                                        "source": "theoddsapi",
                                        "site": site.get("title"),
                                    }
            return {"source": "no_match"}
        except Exception:
            return {"source": "error"}

    def get_fallback_odds(self, home_strength: float, away_strength: float) -> Dict:
        """Deterministic odds based on relative strength when API is unavailable."""
        spread = max(0.02, min(0.45, home_strength - away_strength))
        home_price = round(1 / ((0.5 + spread) * 0.95), 2)
        away_price = round(1 / ((0.5 - spread) * 0.95), 2)

        return {
            "home_ml": max(1.01, home_price),
            "away_ml": max(1.01, away_price),
            "over": 1.90,
            "under": 1.90,
            "source": "fallback",
        }
