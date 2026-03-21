"""
Research Agent - Fetches real-time data for betting analysis
"""

import requests
from datetime import datetime
from typing import Dict, List


class ResearchAgent:
    """Research agent for gathering betting intelligence."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BetBrain/1.0"
        })
        self.news_api_key = None
        try:
            from dotenv import load_dotenv
            import os
            load_dotenv()
            self.news_api_key = os.getenv("NEWSAPI_KEY")
        except Exception:
            self.news_api_key = None
    
    def get_team_news(self, team: str) -> Dict:
        """Get recent news for a team."""
        if self.news_api_key:
            return self._get_newsapi_team_info(team)

        # Fallback mock data
        return {
            "team": team,
            "injuries": [],
            "form": "neutral",
            "news": [],
            "last_updated": datetime.now().isoformat()
        }

    def _get_newsapi_team_info(self, team: str) -> Dict:
        """Fetch from NewsAPI and parse for injuries + sentiment."""
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": f"{team} injury nhl",
            "language": "en",
            "pageSize": 5,
            "apiKey": self.news_api_key,
        }

        try:
            r = self.session.get(url, params=params, timeout=8)
            r.raise_for_status()
            data = r.json()

            articles = [
                {"title": item.get("title"), "url": item.get("url")}
                for item in data.get("articles", [])
            ]

            injuries = []
            for art in articles:
                if "injury" in (art.get("title") or "").lower():
                    injuries.append({"impact": 2, "source": art.get("url")})

            return {
                "team": team,
                "injuries": injuries,
                "form": "neutral",
                "news": articles,
                "last_updated": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "team": team,
                "injuries": [],
                "form": "neutral",
                "news": [],
                "last_updated": datetime.now().isoformat(),
                "error": str(e)
            }
    
    def get_injury_report(self, team: str) -> List[Dict]:
        """Get injury report for team."""
        # Real implementation would scrape injury data
        return []
    
    def get_team_form(self, team: str, games: int = 5) -> Dict:
        """Get team's recent form."""
        # Real implementation would scrape standings
        return {
            "team": team,
            "wins_last_5": 3,
            "goals_scored": 12,
            "goals_conceded": 8,
        }


def research_game(home_team: str, away_team: str) -> Dict:
    """Research a specific matchup."""
    agent = ResearchAgent()
    
    home_info = agent.get_team_news(home_team)
    away_info = agent.get_team_news(away_team)
    
    return {
        "home": home_info,
        "away": away_info,
        "factors": [
            f"{home_team} home advantage",
            f"{away_team} away struggle",
        ]
    }


if __name__ == "__main__":
    # Test
    result = research_game("COL", "EDM")
    print(result)
