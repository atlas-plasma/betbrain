"""
Form Agent — Recent performance analysis.

Looks at:
  - Win rate in last 5 and last 10 games
  - Recent goals-for / goals-against trends
  - Home vs away split advantage
  - Power-play and penalty-kill percentages (when available)

Returns a vote biased toward teams showing strong recent form.
"""

from .base import BaseAgent, AgentVote


def _form_score(stats: dict, is_home: bool) -> float:
    """
    Composite form score in 0–1 range.
    Combines: win_rate, goals_for_avg, goals_against_avg, powerplay_pct, pk_pct.
    """
    wr = stats.get("win_rate", 0.5)
    gf = min(1.0, stats.get("goals_for_avg", 3.0) / 5.0)   # 3.0 gf/gm → 0.6
    ga_inv = 1.0 - min(1.0, stats.get("goals_against_avg", 3.0) / 5.0)

    pp = stats.get("powerplay_pct", 20) / 100.0
    pk = stats.get("penalty_kill_pct", 80) / 100.0

    # Home/away split bonus
    if is_home:
        wr_split = stats.get("home_win_rate", wr + 0.05)
    else:
        wr_split = stats.get("away_win_rate", wr - 0.05)
    wr_split = max(0, min(1, wr_split))

    # Weighted composite
    score = (
        wr_split * 0.35
        + gf * 0.20
        + ga_inv * 0.20
        + pp * 0.15
        + pk * 0.10
    )
    return max(0.05, min(0.95, score))


class FormAgent(BaseAgent):
    """Recent-form and splits analysis."""

    name = "Form"

    def analyze(
        self,
        home: str,
        away: str,
        home_stats: dict,
        away_stats: dict,
        ou_line: float = 6.5,
    ) -> AgentVote:
        home_score = _form_score(home_stats, is_home=True)
        away_score = _form_score(away_stats, is_home=False)

        total = home_score + away_score
        home_win = home_score / total
        away_win = away_score / total

        # O/U signal: both teams scoring a lot → over
        avg_gf = (
            home_stats.get("goals_for_avg", 3.0) +
            away_stats.get("goals_for_avg", 3.0)
        )
        league_avg_total = 6.1   # NHL 2024-25 average
        over_lean = avg_gf / league_avg_total   # > 1.0 means high-scoring matchup

        if over_lean >= 1.08:
            ou_pick, ou_conf = "over", min(0.75, 0.5 + (over_lean - 1.0) * 2)
        elif over_lean <= 0.92:
            ou_pick, ou_conf = "under", min(0.75, 0.5 + (1.0 - over_lean) * 2)
        else:
            ou_pick, ou_conf = "skip", 0.5

        # ML vote — require at least 5% separation
        if home_win - away_win >= 0.05:
            ml_pick, ml_conf = "home", home_win
        elif away_win - home_win >= 0.05:
            ml_pick, ml_conf = "away", away_win
        else:
            ml_pick, ml_conf = "skip", max(home_win, away_win)

        home_wr = home_stats.get("win_rate", 0.5)
        away_wr = away_stats.get("win_rate", 0.5)
        home_gf = home_stats.get("goals_for_avg", 3.0)
        away_gf = away_stats.get("goals_for_avg", 3.0)
        home_pp = home_stats.get("powerplay_pct", 20)
        away_pp = away_stats.get("powerplay_pct", 20)

        reasoning = (
            f"Form: {home} W%={home_wr:.0%} PP={home_pp}% GF/G={home_gf:.2f} (home). "
            f"{away} W%={away_wr:.0%} PP={away_pp}% GF/G={away_gf:.2f} (away). "
            f"Form scores {home_score:.2f} vs {away_score:.2f}. "
            f"Expected total {avg_gf:.1f} goals (line {ou_line})."
        )

        return AgentVote(
            agent_name=self.name,
            ml_pick=ml_pick,
            ml_confidence=round(ml_conf, 4),
            ou_pick=ou_pick,
            ou_confidence=round(ou_conf, 4),
            home_win_prob=round(home_win, 4),
            away_win_prob=round(away_win, 4),
            over_prob=round(min(0.95, ou_conf if ou_pick == "over" else 1 - ou_conf), 4),
            reasoning=reasoning,
        )
