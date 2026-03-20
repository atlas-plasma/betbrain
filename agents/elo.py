"""
ELO Rating Agent.

Maintains an in-memory ELO table seeded from win-rate stats (converted to
a 1200–1800 rating range). Predicts win probabilities via the standard ELO
formula and votes accordingly.
"""

from .base import BaseAgent, AgentVote

# Seed ELO: map win_rate (0–1) → 1200–1800
_ELO_TABLE: dict[str, float] = {}

K_FACTOR = 20   # standard ELO K for NHL
HOME_ELO_BONUS = 40  # home ice advantage in ELO points


def _win_rate_to_elo(win_rate: float) -> float:
    """Seed ELO: 0.5 win-rate → 1500, range 1200–1800."""
    return 1200 + win_rate * 1200


def _expected(rating_a: float, rating_b: float) -> float:
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


class ELOAgent(BaseAgent):
    """ELO-based agent seeded from current season stats."""

    name = "ELO"

    def analyze(
        self,
        home: str,
        away: str,
        home_stats: dict,
        away_stats: dict,
        ou_line: float = 6.5,
    ) -> AgentVote:
        # Seed or retrieve ELO
        if home not in _ELO_TABLE:
            _ELO_TABLE[home] = _win_rate_to_elo(home_stats.get("win_rate", 0.5))
        if away not in _ELO_TABLE:
            _ELO_TABLE[away] = _win_rate_to_elo(away_stats.get("win_rate", 0.5))

        home_elo = _ELO_TABLE[home] + HOME_ELO_BONUS
        away_elo = _ELO_TABLE[away]

        home_win = _expected(home_elo, away_elo)
        away_win = 1 - home_win

        # ELO has no O/U signal — abstain
        ou_pick = "skip"
        ou_conf = 0.5

        # ML vote
        if home_win >= 0.55:
            ml_pick, ml_conf = "home", home_win
        elif away_win >= 0.55:
            ml_pick, ml_conf = "away", away_win
        else:
            ml_pick, ml_conf = "skip", max(home_win, away_win)

        elo_diff = home_elo - away_elo
        reasoning = (
            f"ELO ratings: {home} {home_elo:.0f} (+{HOME_ELO_BONUS} home ice) vs "
            f"{away} {away_elo:.0f} (diff={elo_diff:+.0f}). "
            f"Win probability: {home_win*100:.1f}% home."
        )

        return AgentVote(
            agent_name=self.name,
            ml_pick=ml_pick,
            ml_confidence=round(ml_conf, 4),
            ou_pick=ou_pick,
            ou_confidence=ou_conf,
            home_win_prob=round(home_win, 4),
            away_win_prob=round(away_win, 4),
            over_prob=0.5,
            reasoning=reasoning,
            extra={"home_elo": home_elo, "away_elo": away_elo},
        )
