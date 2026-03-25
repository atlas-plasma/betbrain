"""
Consensus Aggregator — weighted multi-agent vote fusion.

Agent weights (tuned by information value):
  Statistical  0.40   — model with PDO, goalie, B2B, Pythagorean
  Research     0.25   — injury / lineup intelligence (only when it has signal)
  Form         0.20   — recent form, special teams, splits
  ELO          0.15   — long-run quality signal

Claude AI / other LLM: treated as a peer with full weight when available,
otherwise its weight is redistributed proportionally.

Final confidence = agreement_rate × weighted_avg_confidence
Kelly fraction also computed here for stake sizing.
"""

from dataclasses import dataclass, field
from typing import List, Dict
from .base import AgentVote

# Agent weights — must sum to 1.0 for agents that vote
_BASE_WEIGHTS: Dict[str, float] = {
    "Statistical":  0.40,
    "Research":     0.25,
    "Form":         0.20,
    "ELO":          0.15,
    "AI Analyst":   0.0,   # bonus weight when present (added from skip bucket)
    "Claude AI":    0.0,
}
# When Claude/AI is available and votes, it gets this weight (taken equally from others)
_AI_BONUS_WEIGHT = 0.20

INITIAL_BANKROLL = 1000.0
KELLY_FRACTION   = 0.25    # fractional Kelly (conservative)
MAX_BET_FRAC     = 0.05    # never more than 5% per bet


@dataclass
class ConsensusResult:
    home: str
    away: str

    ml_pick: str
    ml_confidence: float
    ou_pick: str
    ou_confidence: float

    home_win_prob: float
    away_win_prob: float
    over_prob: float

    tier: str

    agent_votes: List[AgentVote] = field(default_factory=list)
    reasoning: str = ""

    ml_vote_tally: dict = field(default_factory=dict)
    ou_vote_tally: dict = field(default_factory=dict)

    # Kelly bet sizing
    kelly_ml:  float = 0.0   # fraction of bankroll to bet ML
    kelly_ou:  float = 0.0   # fraction of bankroll to bet O/U


def _effective_weights(votes: List[AgentVote]) -> Dict[str, float]:
    """Build weight map adjusted for AI agent presence."""
    weights = dict(_BASE_WEIGHTS)
    has_ai = any(v.agent_name in ("Claude AI", "AI Analyst") and v.ml_pick != "skip"
                 for v in votes)
    if has_ai:
        # Redistribute AI bonus proportionally from non-AI agents
        for k in ("Statistical", "Form", "ELO", "Research"):
            weights[k] = max(0, weights[k] - _AI_BONUS_WEIGHT * weights[k] /
                             sum(weights[a] for a in ("Statistical","Form","ELO","Research")))
        for v in votes:
            if v.agent_name in ("Claude AI", "AI Analyst"):
                weights[v.agent_name] = _AI_BONUS_WEIGHT
    return weights


def _aggregate(votes: List[AgentVote], pick_attr: str, conf_attr: str,
               weights: Dict[str, float]) -> tuple:
    """Returns (winning_pick, composite_confidence, tally)."""
    tally: Dict[str, float] = {}   # pick → total weight
    conf_sum: Dict[str, float] = {}
    weight_count: Dict[str, float] = {}

    for v in votes:
        pick = getattr(v, pick_attr)
        conf = getattr(v, conf_attr)
        w    = weights.get(v.agent_name, 0.10)
        if pick == "skip":
            continue
        tally.setdefault(pick, 0)
        conf_sum.setdefault(pick, 0)
        weight_count.setdefault(pick, 0)
        tally[pick] += w
        conf_sum[pick] += conf * w
        weight_count[pick] += w

    if not tally:
        return "skip", 0.5, {}

    # Winner = highest total weight
    winner = max(tally, key=tally.get)
    wt = weight_count[winner]
    avg_conf = conf_sum[winner] / wt if wt > 0 else 0.5
    total_w  = sum(tally.values())
    agreement_rate = tally[winner] / total_w if total_w > 0 else 0

    composite = agreement_rate * avg_conf
    tally_counts = {k: round(v, 2) for k, v in tally.items()}
    return winner, round(composite, 4), tally_counts


def _kelly_stake(model_prob: float, odds: float) -> float:
    """Fractional Kelly criterion stake (as fraction of bankroll)."""
    b = odds - 1.0          # net odds
    if b <= 0 or model_prob <= 0:
        return 0.0
    q = 1.0 - model_prob
    f = (b * model_prob - q) / b    # full Kelly
    frac_kelly = f * KELLY_FRACTION
    return round(max(0.0, min(MAX_BET_FRAC, frac_kelly)), 4)


def _tier(conf: float) -> str:
    if conf >= 0.60:
        return "high"
    elif conf >= 0.55:
        return "medium"
    return "low"


def _weighted_prob(votes: List[AgentVote], attr: str, weights: Dict[str, float]) -> float:
    total_w = val_w = 0.0
    for v in votes:
        w = weights.get(v.agent_name, 0.10)
        total_w += w
        val_w   += getattr(v, attr) * w
    return round(val_w / max(1e-9, total_w), 4)


class ConsensusAggregator:

    def aggregate(
        self,
        home: str,
        away: str,
        votes: List[AgentVote],
        home_ml_odds: float = 2.0,
        away_ml_odds: float = 2.0,
        ou_odds: float = 1.909,
    ) -> ConsensusResult:

        weights = _effective_weights(votes)

        ml_pick, ml_conf, ml_tally = _aggregate(votes, "ml_pick", "ml_confidence", weights)
        ou_pick, ou_conf, ou_tally = _aggregate(votes, "ou_pick", "ou_confidence", weights)

        home_win = _weighted_prob(votes, "home_win_prob", weights)
        away_win = _weighted_prob(votes, "away_win_prob", weights)
        over_p   = _weighted_prob(votes, "over_prob",     weights)

        # Normalise ML probs
        total = home_win + away_win
        if total > 0:
            home_win = round(home_win / total, 4)
            away_win = round(away_win / total, 4)

        # Kelly sizing
        if ml_pick == "home":
            kelly_ml = _kelly_stake(home_win, home_ml_odds)
        elif ml_pick == "away":
            kelly_ml = _kelly_stake(away_win, away_ml_odds)
        else:
            kelly_ml = 0.0

        if ou_pick == "over":
            kelly_ou = _kelly_stake(over_p, ou_odds)
        elif ou_pick == "under":
            kelly_ou = _kelly_stake(1 - over_p, ou_odds)
        else:
            kelly_ou = 0.0

        # Reasoning: collect agent notes
        lines = [f"[{v.agent_name}] {v.reasoning}" for v in votes if v.reasoning]
        reasoning = " | ".join(lines)

        best_conf = max(ml_conf, ou_conf)

        return ConsensusResult(
            home=home, away=away,
            ml_pick=ml_pick, ml_confidence=ml_conf,
            ou_pick=ou_pick, ou_confidence=ou_conf,
            home_win_prob=home_win, away_win_prob=away_win, over_prob=over_p,
            tier=_tier(best_conf),
            agent_votes=votes, reasoning=reasoning,
            ml_vote_tally=ml_tally, ou_vote_tally=ou_tally,
            kelly_ml=kelly_ml, kelly_ou=kelly_ou,
        )
