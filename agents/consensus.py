"""
Consensus Aggregator — combines votes from all agents into a final pick.

Algorithm:
  1. Collect ML votes from all agents (home / away / skip).
  2. For the majority ML pick, compute:
       agreement_rate = agents_voting_for_winner / total_non-skip_agents
       avg_confidence  = mean(confidence of agents voting for winner)
       final_confidence = agreement_rate * avg_confidence
  3. Same logic for O/U.
  4. Compute consensus home_win_prob as weighted average of agent probabilities
     (agents that abstained get weight 0.5).
"""

from dataclasses import dataclass, field
from typing import List
from .base import AgentVote


@dataclass
class ConsensusResult:
    """Aggregated result from all agents."""
    home: str
    away: str

    # Final ML pick
    ml_pick: str          # "home" | "away" | "skip"
    ml_confidence: float  # 0–1, composite

    # Final O/U pick
    ou_pick: str          # "over" | "under" | "skip"
    ou_confidence: float  # 0–1, composite

    # Averaged model probabilities
    home_win_prob: float
    away_win_prob: float
    over_prob: float

    # Tier label derived from confidence
    tier: str             # "high" | "medium" | "low"

    # Combined reasoning from all agents
    agent_votes: List[AgentVote] = field(default_factory=list)
    reasoning: str = ""

    # Raw vote tallies
    ml_vote_tally: dict = field(default_factory=dict)
    ou_vote_tally: dict = field(default_factory=dict)


def _aggregate_votes(votes: List[AgentVote], pick_attr: str, conf_attr: str) -> tuple[str, float, dict]:
    """
    Returns (winning_pick, composite_confidence, tally_dict).
    """
    tally: dict[str, list[float]] = {}
    for v in votes:
        pick = getattr(v, pick_attr)
        conf = getattr(v, conf_attr)
        if pick == "skip":
            continue
        tally.setdefault(pick, []).append(conf)

    if not tally:
        return "skip", 0.5, {}

    # Pick with most votes (break ties by highest average confidence)
    winner = max(tally, key=lambda k: (len(tally[k]), sum(tally[k]) / len(tally[k])))
    winning_confs = tally[winner]

    total_voters = sum(len(v) for v in tally.values())
    agreement_rate = len(winning_confs) / total_voters
    avg_conf = sum(winning_confs) / len(winning_confs)
    composite = agreement_rate * avg_conf

    tally_summary = {k: len(v) for k, v in tally.items()}
    return winner, round(composite, 4), tally_summary


def _weighted_avg_prob(votes: List[AgentVote], prob_attr: str) -> float:
    """Average agent probabilities, weighting by their non-skip signal."""
    vals = [getattr(v, prob_attr) for v in votes]
    return round(sum(vals) / len(vals), 4) if vals else 0.5


def _tier(confidence: float) -> str:
    if confidence >= 0.60:
        return "high"
    elif confidence >= 0.45:
        return "medium"
    return "low"


class ConsensusAggregator:
    """Aggregate a list of AgentVotes into a ConsensusResult."""

    def aggregate(self, home: str, away: str, votes: List[AgentVote]) -> ConsensusResult:
        ml_pick, ml_conf, ml_tally = _aggregate_votes(votes, "ml_pick", "ml_confidence")
        ou_pick, ou_conf, ou_tally = _aggregate_votes(votes, "ou_pick", "ou_confidence")

        home_win_prob = _weighted_avg_prob(votes, "home_win_prob")
        away_win_prob = _weighted_avg_prob(votes, "away_win_prob")
        over_prob = _weighted_avg_prob(votes, "over_prob")

        # Normalise ML probs
        total = home_win_prob + away_win_prob
        if total > 0:
            home_win_prob = round(home_win_prob / total, 4)
            away_win_prob = round(away_win_prob / total, 4)

        # Build combined reasoning
        lines = []
        for v in votes:
            if v.reasoning:
                lines.append(f"[{v.agent_name}] {v.reasoning}")

        reasoning = " | ".join(lines)

        # Overall confidence = max(ml, ou) for tier
        best_conf = max(ml_conf, ou_conf)

        return ConsensusResult(
            home=home,
            away=away,
            ml_pick=ml_pick,
            ml_confidence=ml_conf,
            ou_pick=ou_pick,
            ou_confidence=ou_conf,
            home_win_prob=home_win_prob,
            away_win_prob=away_win_prob,
            over_prob=over_prob,
            tier=_tier(best_conf),
            agent_votes=votes,
            reasoning=reasoning,
            ml_vote_tally=ml_tally,
            ou_vote_tally=ou_tally,
        )
