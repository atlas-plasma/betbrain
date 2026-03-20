"""
AI Reasoning Agent — supports Anthropic Claude AND any OpenAI-compatible endpoint
(OpenClaw, Ollama, OpenRouter, LM Studio, etc.)

Priority order:
  1. ANTHROPIC_API_KEY   → uses Anthropic SDK (Claude models)
  2. OPENAI_API_KEY      → uses openai SDK (OpenAI / OpenClaw / OpenRouter)
  3. OLLAMA_BASE_URL     → uses openai SDK pointed at local Ollama server
  4. No key configured   → agent gracefully abstains

Environment variables:
  ANTHROPIC_API_KEY     Anthropic key
  OPENAI_API_KEY        OpenAI / OpenClaw / OpenRouter key
  OPENAI_BASE_URL       Override base URL (e.g. http://localhost:11434/v1 for Ollama
                        or http://localhost:18789/v1 for OpenClaw gateway)
  OPENAI_MODEL          Model name to use (default: gpt-4o-mini / llama3 for Ollama)
  OLLAMA_BASE_URL       Shorthand for local Ollama (sets base URL automatically)
  OLLAMA_MODEL          Model for Ollama (default: llama3.2)
"""

import os
import json
from .base import BaseAgent, AgentVote


def _build_prompt(home, away, home_stats, away_stats, ou_line):
    def fmt(team, stats, side):
        return (
            f"  {team} ({side}): GP={stats.get('games_played','?')}, "
            f"W%={stats.get('win_rate',0.5):.1%}, "
            f"GF/G={stats.get('goals_for_avg',3.0):.2f}, "
            f"GA/G={stats.get('goals_against_avg',3.0):.2f}, "
            f"PP={stats.get('powerplay_pct',20)}%, "
            f"PK={stats.get('penalty_kill_pct',80)}%, "
            f"SV%={stats.get('save_pct',0.910):.3f}"
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
- ml_confidence / ou_confidence: 0.5 = coin flip, only >0.75 if very confident
- home_win_prob + away_win_prob must sum to ~1.0
- Be concise and specific in reasoning"""


def _parse_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _make_vote(name, data) -> AgentVote:
    ml_pick = data.get("ml_pick", "skip")
    ml_conf = float(data.get("ml_confidence", 0.5))
    ou_pick = data.get("ou_pick", "skip")
    ou_conf = float(data.get("ou_confidence", 0.5))
    home_win = float(data.get("home_win_prob", 0.5))
    away_win = float(data.get("away_win_prob", 0.5))
    over_prob = float(data.get("over_prob", 0.5))
    reasoning = data.get("reasoning", "")

    total = home_win + away_win
    if total > 0:
        home_win /= total
        away_win /= total

    return AgentVote(
        agent_name=name,
        ml_pick=ml_pick,
        ml_confidence=round(max(0.0, min(1.0, ml_conf)), 4),
        ou_pick=ou_pick,
        ou_confidence=round(max(0.0, min(1.0, ou_conf)), 4),
        home_win_prob=round(home_win, 4),
        away_win_prob=round(away_win, 4),
        over_prob=round(max(0.0, min(1.0, over_prob)), 4),
        reasoning=reasoning,
    )


def _abstain(name, reason) -> AgentVote:
    return AgentVote(
        agent_name=name,
        ml_pick="skip", ml_confidence=0.5,
        ou_pick="skip", ou_confidence=0.5,
        home_win_prob=0.5, away_win_prob=0.5, over_prob=0.5,
        reasoning=reason,
    )


class ClaudeAgent(BaseAgent):
    """
    AI reasoning agent. Tries Anthropic first, then any OpenAI-compatible
    provider (OpenClaw, Ollama, OpenRouter, LM Studio, etc.).
    """

    name = "AI Analyst"

    def __init__(self):
        self._backend = None   # "anthropic" | "openai" | None
        self._client = None
        self._model = None
        self._agent_label = "AI Analyst"

        # 1. Anthropic
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        if anthropic_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=anthropic_key)
                self._model = "claude-haiku-4-5-20251001"
                self._backend = "anthropic"
                self._agent_label = "Claude AI"
                return
            except ImportError:
                pass

        # 2. OpenAI-compatible (OpenClaw / OpenRouter / OpenAI)
        openai_key = os.getenv("OPENAI_API_KEY", "")
        openai_base = os.getenv("OPENAI_BASE_URL", "")
        ollama_base = os.getenv("OLLAMA_BASE_URL", "")

        if openai_key or openai_base or ollama_base:
            try:
                from openai import OpenAI

                if ollama_base:
                    # Local Ollama
                    base_url = ollama_base.rstrip("/") + "/v1"
                    self._model = os.getenv("OLLAMA_MODEL", "llama3.2")
                    self._client = OpenAI(base_url=base_url, api_key="ollama")
                    self._agent_label = f"Ollama ({self._model})"
                else:
                    # OpenClaw / OpenRouter / OpenAI
                    kwargs = {"api_key": openai_key or "none"}
                    if openai_base:
                        kwargs["base_url"] = openai_base
                    self._client = OpenAI(**kwargs)
                    self._model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
                    self._agent_label = f"AI ({self._model})"

                self._backend = "openai"
                self.name = self._agent_label
            except ImportError:
                pass

    def analyze(self, home, away, home_stats, away_stats, ou_line=6.5) -> AgentVote:
        self.name = self._agent_label  # keep name in sync

        if not self._client:
            return _abstain(
                self._agent_label,
                "No AI key configured. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or OLLAMA_BASE_URL."
            )

        prompt = _build_prompt(home, away, home_stats, away_stats, ou_line)

        try:
            if self._backend == "anthropic":
                msg = self._client.messages.create(
                    model=self._model,
                    max_tokens=512,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = msg.content[0].text

            else:  # openai-compatible
                resp = self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=512,
                    temperature=0.2,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = resp.choices[0].message.content

            data = _parse_response(raw)
            vote = _make_vote(self._agent_label, data)
            return vote

        except Exception as e:
            return _abstain(self._agent_label, f"API error: {str(e)[:80]}")
