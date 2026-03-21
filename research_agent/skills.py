"""Skill definitions for ResearchAgent and future agent orchestration."""

from typing import Dict


def fetch_injury_updates(team: str, source: str = "newsapi") -> Dict:
    """Fetch injury and lineup updates from configured source."""
    if source == "newsapi":
        from .agent import ResearchAgent
        agent = ResearchAgent()
        info = agent.get_team_news(team)
        return {
            "team": team,
            "injuries": info.get("injuries", []),
            "news_count": len(info.get("news", [])),
            "source": "newsapi" if agent.news_api_key else "mock"
        }

    # other sources can be added here
    return {"team": team, "injuries": [], "source": "none"}


def fetch_schedule(days: int = 3) -> Dict:
    """Fetch next scheduld days using NHL data feed."""
    from data.nhl import NHLDataFetcher
    fetcher = NHLDataFetcher()
    games = fetcher.get_schedule(days)
    return {"days": days, "games": games}
