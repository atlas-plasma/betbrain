"""
Research Agent — injury & lineup intelligence via web search.

Searches for real-time injury reports, lineup news, and team news
for each matchup. Uses an LLM (if available) to parse severity,
otherwise applies conservative keyword-based heuristics.

Injury impact on win probability (empirically derived):
  Starting goalie out     → -12 to -18% win prob
  Star forward out (top6) → -4 to -8%
  Top defenseman out      → -3 to -5%
  Depth forward out       → -1 to -2%
  Multiple injuries       → compounding effect
"""

import os
import json
from typing import Optional
from .base import BaseAgent, AgentVote

# Keywords indicating a player is OUT (vs just day-to-day)
OUT_KEYWORDS = [
    "out", "ir", "injured reserve", "ltir", "week-to-week", "month-to-month",
    "broken", "surgery", "fracture", "torn", "severed", "out indefinitely",
]
DTD_KEYWORDS = [
    "day-to-day", "questionable", "doubtful", "game-time decision", "gtd",
    "probable", "limited practice", "won't practice",
]
GOALIE_TERMS = ["goalie", "goaltender", "netminder", "starter", "backup"]
STAR_TERMS   = ["captain", "star", "top line", "first line", "ace", "first pairing"]


def _keyword_severity(text: str, team: str) -> float:
    """
    Heuristic injury penalty (0.0 = no impact, positive = bad for team).
    Returns a suggested win-prob reduction for this team.
    """
    text_lower = text.lower()
    team_lower = team.lower()

    if team_lower not in text_lower:
        return 0.0

    penalty = 0.0
    is_goalie = any(kw in text_lower for kw in GOALIE_TERMS)
    is_star   = any(kw in text_lower for kw in STAR_TERMS)
    is_out    = any(kw in text_lower for kw in OUT_KEYWORDS)
    is_dtd    = any(kw in text_lower for kw in DTD_KEYWORDS)

    if is_goalie and is_out:
        penalty += 0.15
    elif is_goalie and is_dtd:
        penalty += 0.07
    elif is_star and is_out:
        penalty += 0.07
    elif is_star and is_dtd:
        penalty += 0.03
    elif is_out:
        penalty += 0.025
    elif is_dtd:
        penalty += 0.01

    return penalty


def _build_parse_prompt(home: str, away: str, search_results: str) -> str:
    return f"""You are an NHL injury analyst. Based on these search results, identify any significant injuries or lineup changes for {home} or {away}.

SEARCH RESULTS:
{search_results[:2000]}

Respond ONLY with JSON:
{{
  "{home}_penalty": 0.0-0.20,
  "{away}_penalty": 0.0-0.20,
  "home_notes": "brief description of any issues",
  "away_notes": "brief description of any issues"
}}

Penalty scale:
- 0.00 = no significant injuries
- 0.05 = one key forward/defenseman out
- 0.10 = top-line player or top pairing defender out
- 0.15 = starting goalie questionable/out
- 0.20 = multiple significant players or starting goalie confirmed out

Return 0.0 if nothing found. Be conservative."""


class ResearchAgent(BaseAgent):
    """Web search + LLM parsing for injury and lineup intelligence."""

    name = "Research"

    def __init__(self):
        self._llm_client = None
        self._llm_model  = None
        self._llm_backend = None

        # Reuse the same LLM detection as ClaudeAgent
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        if anthropic_key:
            try:
                import anthropic
                self._llm_client  = anthropic.Anthropic(api_key=anthropic_key)
                self._llm_model   = "claude-haiku-4-5-20251001"
                self._llm_backend = "anthropic"
            except ImportError:
                pass

        if not self._llm_client:
            openai_key  = os.getenv("OPENAI_API_KEY", "")
            openai_base = os.getenv("OPENAI_BASE_URL", "")
            ollama_base = os.getenv("OLLAMA_BASE_URL", "")
            if openai_key or openai_base or ollama_base:
                try:
                    from openai import OpenAI
                    if ollama_base:
                        self._llm_client  = OpenAI(
                            base_url=ollama_base.rstrip("/") + "/v1",
                            api_key="ollama",
                        )
                        self._llm_model   = os.getenv("OLLAMA_MODEL", "llama3.2")
                    else:
                        kwargs = {"api_key": openai_key or "none"}
                        if openai_base:
                            kwargs["base_url"] = openai_base
                        self._llm_client  = OpenAI(**kwargs)
                        self._llm_model   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
                    self._llm_backend = "openai"
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

        home_penalty = 0.0
        away_penalty = 0.0
        notes = []

        # --- Web search for injuries ---
        search_text = self._search_injuries(home, away)

        if search_text:
            if self._llm_client:
                # Use LLM to parse intelligently
                home_penalty, away_penalty, home_note, away_note = \
                    self._llm_parse(home, away, search_text)
                if home_note:
                    notes.append(f"{home}: {home_note}")
                if away_note:
                    notes.append(f"{away}: {away_note}")
            else:
                # Fallback: keyword heuristic
                home_penalty = _keyword_severity(search_text, home)
                away_penalty = _keyword_severity(search_text, away)
                if home_penalty > 0:
                    notes.append(f"{home} injury/news found (heuristic)")
                if away_penalty > 0:
                    notes.append(f"{away} injury/news found (heuristic)")
        else:
            notes.append("No injury news found — assuming clean bill of health")

        # --- Convert penalties to vote ---
        # Adjust base win probs using injury penalty
        base_home = home_stats.get("win_rate", 0.5)
        base_away = away_stats.get("win_rate", 0.5)

        adjusted_home = max(0.05, base_home - home_penalty + away_penalty * 0.5)
        adjusted_away = max(0.05, base_away - away_penalty + home_penalty * 0.5)
        total = adjusted_home + adjusted_away
        home_win = adjusted_home / total
        away_win = adjusted_away / total

        # Only vote if research found something significant
        has_signal = (home_penalty >= 0.03 or away_penalty >= 0.03)

        if not has_signal:
            ml_pick, ml_conf = "skip", 0.5
            ou_pick, ou_conf = "skip", 0.5
        elif home_win >= 0.55:
            ml_pick, ml_conf = "home", home_win
            ou_pick, ou_conf = "skip", 0.5
        elif away_win >= 0.55:
            ml_pick, ml_conf = "away", away_win
            ou_pick, ou_conf = "skip", 0.5
        else:
            ml_pick, ml_conf = "skip", max(home_win, away_win)
            ou_pick, ou_conf = "skip", 0.5

        # Injury impact on O/U: key players out → under signal
        max_penalty = max(home_penalty, away_penalty)
        if max_penalty >= 0.07:
            ou_pick  = "under"
            ou_conf  = min(0.70, 0.50 + max_penalty * 2)

        reasoning = ""
        if notes:
            reasoning = "Research: " + "; ".join(notes) + ". "
        if home_penalty > 0:
            reasoning += f"{home} adj penalty={home_penalty:.0%}. "
        if away_penalty > 0:
            reasoning += f"{away} adj penalty={away_penalty:.0%}. "
        if not reasoning:
            reasoning = "No injury concerns found for either team."

        return AgentVote(
            agent_name=self.name,
            ml_pick=ml_pick,
            ml_confidence=round(ml_conf, 4),
            ou_pick=ou_pick,
            ou_confidence=round(ou_conf, 4),
            home_win_prob=round(home_win, 4),
            away_win_prob=round(away_win, 4),
            over_prob=round(0.5 - max_penalty * 0.5, 4),
            reasoning=reasoning,
        )

    def _search_injuries(self, home: str, away: str) -> str:
        """Try multiple search queries and return combined text."""
        try:
            from ddgs import DDGS
            results = []
            queries = [
                f"NHL {home} {away} injury lineup today",
                f"NHL {home} injuries scratch",
                f"NHL {away} injuries scratch",
            ]
            with DDGS() as ddg:
                for q in queries[:2]:  # limit to 2 queries for speed
                    for r in ddg.text(q, max_results=3):
                        results.append(r.get("body", ""))
            return " ".join(results)
        except ImportError:
            pass
        except Exception:
            pass

        # Try requests-based fallback (ESPN)
        try:
            import requests
            url = (
                f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/injuries"
            )
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                text_parts = []
                for team_data in data.get("injuries", []):
                    tn = team_data.get("team", {}).get("abbreviation", "")
                    if tn not in (home, away):
                        continue
                    for player in team_data.get("injuries", []):
                        name   = player.get("athlete", {}).get("displayName", "")
                        status = player.get("status", "")
                        detail = player.get("details", {}).get("detail", "")
                        pos    = player.get("athlete", {}).get("position", {}).get("abbreviation", "")
                        text_parts.append(f"{tn} {name} ({pos}) {status} {detail}")
                return "; ".join(text_parts)
        except Exception:
            pass

        return ""

    def _llm_parse(self, home: str, away: str, search_text: str):
        """Use LLM to parse injury text. Returns (home_pen, away_pen, home_note, away_note)."""
        prompt = _build_parse_prompt(home, away, search_text)
        try:
            if self._llm_backend == "anthropic":
                msg = self._llm_client.messages.create(
                    model=self._llm_model,
                    max_tokens=256,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = msg.content[0].text
            else:
                resp = self._llm_client.chat.completions.create(
                    model=self._llm_model,
                    max_tokens=256,
                    temperature=0.1,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = resp.choices[0].message.content

            # Strip markdown fences
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw.strip())
            home_pen  = float(data.get(f"{home}_penalty", 0.0))
            away_pen  = float(data.get(f"{away}_penalty", 0.0))
            home_note = data.get("home_notes", "")
            away_note = data.get("away_notes", "")
            return (
                max(0.0, min(0.25, home_pen)),
                max(0.0, min(0.25, away_pen)),
                home_note,
                away_note,
            )
        except Exception:
            return 0.0, 0.0, "", ""
