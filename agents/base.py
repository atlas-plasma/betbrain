"""Base agent interface — all agents return AgentVote objects."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentVote:
    """A single agent's vote on a matchup."""
    agent_name: str

    # Moneyline vote
    ml_pick: str           # "home" | "away" | "skip"
    ml_confidence: float   # 0.0 – 1.0

    # Over/Under vote
    ou_pick: str           # "over" | "under" | "skip"
    ou_confidence: float   # 0.0 – 1.0

    # Model probabilities (0–1)
    home_win_prob: float = 0.5
    away_win_prob: float = 0.5
    over_prob: float = 0.5

    # Agent reasoning (shown in dashboard)
    reasoning: str = ""

    # Raw model data (optional, for debugging)
    extra: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """All agents implement this interface."""

    name: str = "BaseAgent"

    @abstractmethod
    def analyze(
        self,
        home: str,
        away: str,
        home_stats: dict,
        away_stats: dict,
        ou_line: float = 6.5,
    ) -> AgentVote:
        """Return an AgentVote for this matchup."""
        ...
