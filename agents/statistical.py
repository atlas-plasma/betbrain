"""
Statistical Agent — Poisson goal model + Bayesian home-advantage adjustment.

Uses team Goals-For and Goals-Against averages to build independent Poisson
distributions for each team, then integrates over all scorelines to compute
win / draw / loss and over/under probabilities.
"""

import math
from .base import BaseAgent, AgentVote


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _poisson_win_probs(home_lambda: float, away_lambda: float, max_goals: int = 10):
    """Return (home_win, draw, away_win) from independent Poisson distributions."""
    home_win = draw = away_win = 0.0
    for h in range(max_goals + 1):
        ph = _poisson_pmf(h, home_lambda)
        for a in range(max_goals + 1):
            pa = _poisson_pmf(a, away_lambda)
            p = ph * pa
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p
    return home_win, draw, away_win


def _poisson_over_prob(home_lambda: float, away_lambda: float, line: float, max_goals: int = 20) -> float:
    """P(total goals > line) using joint Poisson."""
    int_line = int(line)
    over = 0.0
    for h in range(max_goals + 1):
        ph = _poisson_pmf(h, home_lambda)
        for a in range(max_goals + 1):
            if h + a > int_line:
                over += ph * _poisson_pmf(a, away_lambda)
    return over


class StatisticalAgent(BaseAgent):
    """Poisson-based statistical model."""

    name = "Statistical"

    # NHL average goals per game (used as league prior for Bayesian blending)
    LEAGUE_AVG_GF = 3.05
    LEAGUE_AVG_GA = 3.05
    HOME_ADVANTAGE = 0.10   # 10% boost to home goals (well-documented in NHL)
    MIN_GAMES_TRUST = 15    # below this, blend with league average

    def analyze(
        self,
        home: str,
        away: str,
        home_stats: dict,
        away_stats: dict,
        ou_line: float = 6.5,
    ) -> AgentVote:
        home_gp = max(1, home_stats.get("games_played", 20))
        away_gp = max(1, away_stats.get("games_played", 20))

        # Bayesian blend: regress toward league average for small samples
        home_trust = min(1.0, home_gp / self.MIN_GAMES_TRUST)
        away_trust = min(1.0, away_gp / self.MIN_GAMES_TRUST)

        h_gf = (home_stats.get("goals_for_avg", self.LEAGUE_AVG_GF) * home_trust
                + self.LEAGUE_AVG_GF * (1 - home_trust))
        h_ga = (home_stats.get("goals_against_avg", self.LEAGUE_AVG_GA) * home_trust
                + self.LEAGUE_AVG_GA * (1 - home_trust))
        a_gf = (away_stats.get("goals_for_avg", self.LEAGUE_AVG_GF) * away_trust
                + self.LEAGUE_AVG_GF * (1 - away_trust))
        a_ga = (away_stats.get("goals_against_avg", self.LEAGUE_AVG_GA) * away_trust
                + self.LEAGUE_AVG_GA * (1 - away_trust))

        # Dixon-Coles style expected goals (attack × defence / league average)
        home_lambda = (h_gf * a_ga / self.LEAGUE_AVG_GA) * (1 + self.HOME_ADVANTAGE)
        away_lambda = a_gf * h_ga / self.LEAGUE_AVG_GA

        home_lambda = max(0.5, min(7.0, home_lambda))
        away_lambda = max(0.5, min(7.0, away_lambda))

        home_win, draw, away_win = _poisson_win_probs(home_lambda, away_lambda)

        # In hockey there are no official draws — overtime/shootout eventually produces a winner.
        # Redistribute draw probability proportionally.
        if (home_win + away_win) > 0:
            ratio = draw / (home_win + away_win)
            home_win += home_win * ratio
            away_win += away_win * ratio

        # Clamp
        total = home_win + away_win
        if total > 0:
            home_win /= total
            away_win /= total

        over_prob = _poisson_over_prob(home_lambda, away_lambda, ou_line)

        # ML vote
        if home_win >= 0.55:
            ml_pick, ml_conf = "home", home_win
        elif away_win >= 0.55:
            ml_pick, ml_conf = "away", away_win
        else:
            ml_pick, ml_conf = "skip", max(home_win, away_win)

        # O/U vote
        if over_prob >= 0.58:
            ou_pick, ou_conf = "over", over_prob
        elif over_prob <= 0.42:
            ou_pick, ou_conf = "under", 1 - over_prob
        else:
            ou_pick, ou_conf = "skip", 0.5

        reasoning = (
            f"Poisson model: λ_home={home_lambda:.2f}, λ_away={away_lambda:.2f}. "
            f"Home win {home_win*100:.1f}%, Away win {away_win*100:.1f}%. "
            f"Expected total {home_lambda+away_lambda:.1f} goals (line {ou_line})."
        )

        return AgentVote(
            agent_name=self.name,
            ml_pick=ml_pick,
            ml_confidence=round(ml_conf, 4),
            ou_pick=ou_pick,
            ou_confidence=round(ou_conf, 4),
            home_win_prob=round(home_win, 4),
            away_win_prob=round(away_win, 4),
            over_prob=round(over_prob, 4),
            reasoning=reasoning,
            extra={"home_lambda": home_lambda, "away_lambda": away_lambda},
        )
