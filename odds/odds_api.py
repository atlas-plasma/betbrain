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

    # Bookmakers to prefer, in order. Betway first, then common sharp books.
    # TheOddsAPI key names: https://the-odds-api.com/sports-odds-data/bookmaker-apis.html
    PREFERRED_BOOKS = ["betway", "bet365", "unibet", "paddypower", "williamhill",
                       "draftkings", "fanduel", "betmgm", "bovada"]

    def get_market_odds(self, sport: str = "icehockey_nhl",
                        regions: str = "uk,eu,us",
                        markets: str = "h2h,totals") -> List[Dict]:
        """Fetch live odds for all upcoming NHL games.

        Tries UK region first (where Betway lives), then EU and US as fallback.
        Returns raw TheOddsAPI game list with bookmaker odds attached.
        """
        if not self.has_api():
            raise RuntimeError("ODDS_API_KEY not set")

        url = f"{self.BASE_URL}/{sport}/odds"
        params = {
            "apiKey":      self.api_key,
            "regions":     regions,
            "markets":     markets,
            "oddsFormat":  "decimal",
            "dateFormat":  "iso",
        }

        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        remaining = resp.headers.get("x-requests-remaining", "?")
        print(f"  [odds] TheOddsAPI — {remaining} requests remaining this month")
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

    def get_fallback_odds(self, home_stats: Dict, away_stats: Dict) -> Dict:
        """
        Synthetic odds that mirror what a sharp bookmaker would set.

        Uses Pythagorean win expectation (GF²/GF²+GA²) as the base —
        the same signal real oddsmakers use — then adds the empirical NHL
        home-ice advantage and applies a 5% vig.

        This means the model must find genuine additional edge (from PDO,
        goalie quality, B2B, etc.) over and above what Pythagorean + home
        advantage already predicts. Without this, the backtest rewards the
        model for discovering home advantage, which is trivially known.
        """
        NHL_HOME_WIN_RATE = 0.548   # empirical NHL home advantage

        def pyth_win(gf: float, ga: float) -> float:
            return (gf ** 2) / max(1e-6, gf ** 2 + ga ** 2)

        h_gf = home_stats.get("full_gf", home_stats.get("goals_for_avg", 3.0))
        h_ga = home_stats.get("full_ga", home_stats.get("goals_against_avg", 3.0))
        a_gf = away_stats.get("full_gf", away_stats.get("goals_for_avg", 3.0))
        a_ga = away_stats.get("full_ga", away_stats.get("goals_against_avg", 3.0))

        home_pyth = pyth_win(h_gf, h_ga)
        away_pyth = pyth_win(a_gf, a_ga)

        # Relative quality: normalise so the two probs sum to 1
        total = home_pyth + away_pyth
        home_rel = home_pyth / total if total > 0 else 0.5

        # Shift relative quality by home advantage.
        # home_rel=0.5 (equal teams) → home_prob = 0.5 + 0.048 = 0.548 ✓
        # home_rel=0.7 (stronger home) → home_prob = 0.7 + 0.048 = 0.748 ✓
        HOME_ADV = NHL_HOME_WIN_RATE - 0.5   # = 0.048
        home_prob = max(0.05, min(0.95, home_rel + HOME_ADV))
        away_prob = 1.0 - home_prob

        # Apply 5% bookmaker margin: implied probs sum to 1.05
        MARGIN = 1.05
        home_price = round(1.0 / (home_prob * MARGIN), 3)
        away_price = round(1.0 / (away_prob * MARGIN), 3)

        return {
            "home_ml": max(1.01, home_price),
            "away_ml": max(1.01, away_price),
            "over":    1.909,
            "under":   1.909,
            "source":  "fallback",
        }
