from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class GameOpportunity:
    match: str
    start_time: str
    market: str
    win_pick: str
    odds: float
    model_prob: float
    implied_prob: float
    edge: float
    ev: float
    recommendation: str
    confidence: str
    reasoning: str
    goal_pred: Optional[float] = None
    analysis_notes: Optional[str] = None


@dataclass
class TeamStats:
    team: str
    win_rate: float
    home_win_rate: float
    away_win_rate: float
    goals_for_avg: float
    goals_against_avg: float
    form: float
    injuries: int


@dataclass
class BacktestResult:
    total_bets: int
    won: int
    lost: int
    win_rate: float
    total_return: float
    profit: float
    roi: float
    final_bankroll: float
    max_drawdown: float
