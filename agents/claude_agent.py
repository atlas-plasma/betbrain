"""
Claude AI Agent — uses the Anthropic API to reason about a matchup.

If ANTHROPIC_API_KEY is not set the agent gracefully abstains (returns
"skip" votes with low confidence) so the other agents can still form consensus.
"""

import os
import json
from typing import Optional
from .base import BaseAgent, AgentVote


def _build_prompt(home: str, away: str, home_stats: dict, away_stats: dict, ou_line: float) -> str:
    def fmt(team, stats, side):
        gp = stats.get("games_played", "?")
        wr = stats.get("win_rate", 0.5)
        gf = stats.get("goals_for_avg", 3.0)
        ga = stats.get("goals_against_avg", 3.0)
        pp = stats.get("powerplay_pct", 20)
        pk = stats.get("penalty_kill_pct", 80)
        sv = stats.get("save_pct", 0.910)
        return (
            f"  {team} ({side}): GP={gp}, W%={wr:.1%}, GF/G={gf:.2f}, GA/G={ga:.2f}, "
            f"PP={pp}%, PK={pk}%, SV%={sv:.3f}"
        )

    return f"""You are an expert NHL sports betting analyst. Analyze this matchup and give your best prediction.

MATCHUP: {away} (away) @ {home} (home)
O/U LINE: {ou_line}

TEAM STATS (current season):
{fmt(home, home_stats, "home")}
{fmt(away, away_stats, "away")}

Answer ONLY with a JSON object in this exact format (no markdown, no extra text):
{{
  "ml_pick": "home" | "away" | "skip",
  "ml_confidence": 0.0-1.0,
  "ou_pick": "over" | "under" | "skip",
  "ou_confidence": 0.0-1.0,
  "home_win_prob": 0.0-1.0,
  "away_win_prob": 0.0-1.0,
  "over_prob": 0.0-1.0,
  "reasoning": "2-3 sentence explanation"
}}

Rules:
- ml_confidence and ou_confidence must reflect genuine certainty (0.5 = coin flip, only use >0.75 if very confident)
- home_win_prob + away_win_prob must sum to ~1.0
- Be concise and specific in reasoning
"""


class ClaudeAgent(BaseAgent):
    """Claude AI reasoning agent via Anthropic SDK."""

    name = "Claude AI"
    MODEL = "claude-haiku-4-5-20251001"  # Fast + cheap for structured predictions

    def __init__(self):
        self._client: Optional[object] = None
        self._available = False
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if api_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=api_key)
                self._available = True
            except ImportError:
                pass

    def analyze(
        self,
        home: str,
        away: str,
        home_stats: dict,
        away_stats: dict,
        ou_line: float = 6.5,
    ) -> AgentVote:
        if not self._available:
            return AgentVote(
                agent_name=self.name,
                ml_pick="skip",
                ml_confidence=0.5,
                ou_pick="skip",
                ou_confidence=0.5,
                home_win_prob=0.5,
                away_win_prob=0.5,
                over_prob=0.5,
                reasoning="Claude AI unavailable (set ANTHROPIC_API_KEY).",
            )

        prompt = _build_prompt(home, away, home_stats, away_stats, ou_line)

        try:
            message = self._client.messages.create(
                model=self.MODEL,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()

            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            data = json.loads(raw)

            ml_pick = data.get("ml_pick", "skip")
            ml_conf = float(data.get("ml_confidence", 0.5))
            ou_pick = data.get("ou_pick", "skip")
            ou_conf = float(data.get("ou_confidence", 0.5))
            home_win = float(data.get("home_win_prob", 0.5))
            away_win = float(data.get("away_win_prob", 0.5))
            over_prob = float(data.get("over_prob", 0.5))
            reasoning = data.get("reasoning", "Claude analysis complete.")

            # Normalise probabilities
            total = home_win + away_win
            if total > 0:
                home_win /= total
                away_win /= total

            return AgentVote(
                agent_name=self.name,
                ml_pick=ml_pick,
                ml_confidence=round(max(0.0, min(1.0, ml_conf)), 4),
                ou_pick=ou_pick,
                ou_confidence=round(max(0.0, min(1.0, ou_conf)), 4),
                home_win_prob=round(home_win, 4),
                away_win_prob=round(away_win, 4),
                over_prob=round(max(0.0, min(1.0, over_prob)), 4),
                reasoning=reasoning,
            )

        except Exception as e:
            return AgentVote(
                agent_name=self.name,
                ml_pick="skip",
                ml_confidence=0.5,
                ou_pick="skip",
                ou_confidence=0.5,
                home_win_prob=0.5,
                away_win_prob=0.5,
                over_prob=0.5,
                reasoning=f"Claude API error: {str(e)[:80]}",
            )
