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
            over_prob_base = min(0.75, 0.5 + (over_lean - 1.0) * 2)
        elif over_lean <= 0.92:
            over_prob_base = max(0.25, 0.5 - (1.0 - over_lean) * 2)
        else:
            over_prob_base = 0.5

        # -- Style-based O/U signal --
        home_style = home_stats.get("style", "balanced")
        away_style = away_stats.get("style", "balanced")

        style_adj = 0.0
        if home_style == "defensive" and away_style == "defensive":
            style_adj = -0.12   # strong under signal
        elif (home_style == "defensive" and away_style == "balanced") or \
             (home_style == "balanced" and away_style == "defensive"):
            style_adj = -0.06   # mild under signal
        elif (home_style == "high_scoring" and away_style == "high_scoring") or \
             (home_style == "offensive" and away_style == "struggling") or \
             (home_style == "struggling" and away_style == "offensive"):
            style_adj = +0.08   # over signal
        elif (home_style == "offensive" and away_style == "defensive") or \
             (home_style == "defensive" and away_style == "offensive"):
            style_adj = 0.0     # cancel out → neutral

        over_prob_base += style_adj

        # -- O/U historical hit rate signal --
        home_ou = home_stats.get("ou_hit_rate", {})
        away_ou = away_stats.get("ou_hit_rate", {})
        home_sample = home_ou.get("sample", 0)
        away_sample = away_ou.get("sample", 0)

        if home_sample >= 5 and away_sample >= 5:
            avg_over_pct = (home_ou.get("over_pct", 0.5) + away_ou.get("over_pct", 0.5)) / 2
            if avg_over_pct > 0.65:
                over_prob_base += 0.06
            elif avg_over_pct < 0.35:
                over_prob_base -= 0.06
        elif home_sample >= 5:
            avg_over_pct = home_ou.get("over_pct", 0.5)
            if avg_over_pct > 0.65:
                over_prob_base += 0.06
            elif avg_over_pct < 0.35:
                over_prob_base -= 0.06
        elif away_sample >= 5:
            avg_over_pct = away_ou.get("over_pct", 0.5)
            if avg_over_pct > 0.65:
                over_prob_base += 0.06
            elif avg_over_pct < 0.35:
                over_prob_base -= 0.06

        # -- Team tier for O/U: elite vs struggling → over signal --
        home_tier = home_stats.get("tier", "contender")
        away_tier = away_stats.get("tier", "contender")
        if (home_tier == "elite" and away_tier == "struggling") or \
           (home_tier == "struggling" and away_tier == "elite"):
            over_prob_base += 0.04

        # Clamp and derive pick
        over_prob_base = max(0.05, min(0.95, over_prob_base))
        under_prob_base = 1.0 - over_prob_base

        if over_prob_base >= 0.58:
            ou_pick = "over"
            ou_conf = over_prob_base
        elif under_prob_base >= 0.58:
            ou_pick = "under"
            ou_conf = under_prob_base
        else:
            ou_pick = "skip"
            ou_conf = max(over_prob_base, under_prob_base)

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
            f"Form: {home} ({home_tier}) W%={home_wr:.0%} PP={home_pp}% GF/G={home_gf:.2f} style={home_style} (home). "
            f"{away} ({away_tier}) W%={away_wr:.0%} PP={away_pp}% GF/G={away_gf:.2f} style={away_style} (away). "
            f"Form scores {home_score:.2f} vs {away_score:.2f}. "
            f"Expected total {avg_gf:.1f} goals (line {ou_line}). "
            f"Style adj={style_adj:+.2f}, O/U over_prob={over_prob_base:.2f}."
        )

        return AgentVote(
            agent_name=self.name,
            ml_pick=ml_pick,
            ml_confidence=round(ml_conf, 4),
            ou_pick=ou_pick,
            ou_confidence=round(ou_conf, 4),
            home_win_prob=round(home_win, 4),
            away_win_prob=round(away_win, 4),
            over_prob=round(over_prob_base, 4),
            reasoning=reasoning,
        )
