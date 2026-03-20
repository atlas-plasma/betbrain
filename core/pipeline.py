"""
BetBrain Analysis Pipeline.

For each upcoming NHL game:
  1. Fetch team stats from NHL API
  2. Fetch live odds (TheOddsAPI or deterministic fallback)
  3. Run all agents → get votes
  4. Aggregate into ConsensusResult
  5. Calculate edge, EV, O/U metrics
  6. Return list of opportunity dicts ready for the dashboard
"""

import os
from datetime import datetime
from typing import List, Dict

from data.nhl import NHLDataFetcher
from odds.odds_api import OddsAPIFetcher
from agents.statistical import StatisticalAgent
from agents.elo import ELOAgent
from agents.form import FormAgent
from agents.claude_agent import ClaudeAgent
from agents.consensus import ConsensusAggregator


# Standard NHL O/U lines (bookmakers use half-goal increments)
_OU_LINES = [4.5, 5.5, 6.5, 7.5]


def _snap_ou_line(expected_total: float) -> float:
    """Pick the closest standard O/U line."""
    return min(_OU_LINES, key=lambda x: abs(x - expected_total))


def _devig(odds_a: float, odds_b: float):
    """Remove bookmaker margin (multiplicative devigging)."""
    raw_a = 1.0 / odds_a
    raw_b = 1.0 / odds_b
    total = raw_a + raw_b
    return raw_a / total, raw_b / total


def _calc_ev(model_prob: float, true_implied: float, odds: float):
    """Edge and expected value."""
    edge = model_prob - true_implied
    ev = model_prob * (odds - 1) - (1 - model_prob)
    return edge, ev


def _confidence_label(conf: float) -> str:
    if conf >= 0.60:
        return "high"
    elif conf >= 0.45:
        return "medium"
    return "low"


class BetBrainPipeline:
    """Main analysis pipeline."""

    def __init__(self):
        self.nhl = NHLDataFetcher()
        self.odds_api = OddsAPIFetcher()
        self.agents = [
            StatisticalAgent(),
            ELOAgent(),
            FormAgent(),
            ClaudeAgent(),
        ]
        self.aggregator = ConsensusAggregator()

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def run(self, days: int = 3) -> List[Dict]:
        """Analyse upcoming games and return opportunity dicts."""
        games = self.nhl.get_schedule(days_forward=days * 8)  # fetch more, trim later
        if not games:
            return []

        # Filter to the requested window
        today = datetime.now().date()
        opportunities = []

        # Batch-fetch live odds once if API is available
        live_odds_map = self._fetch_live_odds_map()

        # Cache team stats so we don't hit the API twice per team
        stats_cache: Dict[str, Dict] = {}

        seen_games = set()
        for game in games:
            home = game.get("home_team")
            away = game.get("away_team")
            if not home or not away:
                continue

            key = (home, away, game.get("date", ""))
            if key in seen_games:
                continue
            seen_games.add(key)

            # Cap at ~3 days × 8 games/day
            if len(opportunities) >= days * 10:
                break

            home_stats = stats_cache.setdefault(home, self.nhl.get_team_stats(home))
            away_stats = stats_cache.setdefault(away, self.nhl.get_team_stats(away))

            # --- Odds ---
            live = live_odds_map.get((home, away)) or live_odds_map.get((away, home))
            if live:
                home_ml_odds = live.get("home_ml", 2.0)
                away_ml_odds = live.get("away_ml", 2.0)
                ou_line = live.get("ou_line", 6.5)
                odds_source = live.get("source", "theoddsapi")
            else:
                fallback = self.odds_api.get_fallback_odds(
                    home_stats.get("win_rate", 0.5),
                    away_stats.get("win_rate", 0.5),
                )
                home_ml_odds = fallback["home_ml"]
                away_ml_odds = fallback["away_ml"]
                ou_line = 6.5
                odds_source = "fallback"

            # --- Agent votes ---
            votes = [a.analyze(home, away, home_stats, away_stats, ou_line) for a in self.agents]
            consensus = self.aggregator.aggregate(home, away, votes)

            # --- Derived metrics ---
            true_home_impl, true_away_impl = _devig(home_ml_odds, away_ml_odds)

            # ML opportunity (home)
            home_edge, home_ev = _calc_ev(consensus.home_win_prob, true_home_impl, home_ml_odds)
            # ML opportunity (away)
            away_edge, away_ev = _calc_ev(consensus.away_win_prob, true_away_impl, away_ml_odds)

            # Best ML side
            if home_edge >= away_edge:
                ml_edge, ml_ev = home_edge, home_ev
                ml_pick = home
                ml_odds = home_ml_odds
                ml_model_prob = consensus.home_win_prob
                ml_impl_prob = true_home_impl
            else:
                ml_edge, ml_ev = away_edge, away_ev
                ml_pick = away
                ml_odds = away_ml_odds
                ml_model_prob = consensus.away_win_prob
                ml_impl_prob = true_away_impl

            # O/U
            over_odds = live.get("over", 1.909) if live else 1.909
            under_odds = live.get("under", 1.909) if live else 1.909
            ou_true_over, ou_true_under = _devig(over_odds, under_odds)

            over_edge, over_ev = _calc_ev(consensus.over_prob, ou_true_over, over_odds)
            under_prob = 1 - consensus.over_prob
            under_edge, under_ev = _calc_ev(under_prob, ou_true_under, under_odds)

            # Agent vote summary string
            vote_summary = self._vote_summary(votes, consensus)

            # Score prediction from Statistical agent
            stat_vote = next((v for v in votes if v.agent_name == "Statistical"), None)
            home_lambda = stat_vote.extra.get("home_lambda", 3.0) if stat_vote else 3.0
            away_lambda = stat_vote.extra.get("away_lambda", 3.0) if stat_vote else 3.0
            score_pred = f"{home_lambda:.1f} - {away_lambda:.1f}"
            pred_total = round(home_lambda + away_lambda, 1)

            base = {
                "match": f"{away} @ {home}",
                "home_team": home,
                "away_team": away,
                "start_time": game.get("start_time", "TBD"),
                "date": game.get("date", ""),
                "odds_source": odds_source,
                "score_pred": score_pred,
                "pred_total": pred_total,
                "ou_line": ou_line,
                "over_prob": round(consensus.over_prob * 100, 1),
                "under_prob": round((1 - consensus.over_prob) * 100, 1),
                "confidence": consensus.tier,
                "ml_vote_tally": consensus.ml_vote_tally,
                "ou_vote_tally": consensus.ou_vote_tally,
                "agent_votes": [
                    {
                        "agent": v.agent_name,
                        "ml": v.ml_pick,
                        "ml_conf": round(v.ml_confidence * 100, 1),
                        "ou": v.ou_pick,
                        "ou_conf": round(v.ou_confidence * 100, 1),
                        "reasoning": v.reasoning,
                    }
                    for v in votes
                ],
                "vote_summary": vote_summary,
            }

            # --- Build individual opportunity rows ---

            # Moneyline row
            should_bet_ml = (ml_edge >= 0.03 and consensus.ml_confidence >= 0.45)
            opportunities.append({
                **base,
                "market": "Moneyline",
                "win_pick": ml_pick,
                "odds": round(ml_odds, 2),
                "model_prob": round(ml_model_prob, 4),
                "implied_prob": round(ml_impl_prob, 4),
                "edge": round(ml_edge, 4),
                "ev": round(ml_ev, 4),
                "should_bet": should_bet_ml,
                "reasoning": consensus.reasoning,
            })

            # Over row
            should_bet_over = (over_edge >= 0.03 and consensus.ou_confidence >= 0.45 and consensus.ou_pick == "over")
            opportunities.append({
                **base,
                "market": f"Over {ou_line}",
                "win_pick": f"Over {ou_line}",
                "odds": round(over_odds, 2),
                "model_prob": round(consensus.over_prob, 4),
                "implied_prob": round(ou_true_over, 4),
                "edge": round(over_edge, 4),
                "ev": round(over_ev, 4),
                "should_bet": should_bet_over,
                "reasoning": consensus.reasoning,
            })

            # Under row
            should_bet_under = (under_edge >= 0.03 and consensus.ou_confidence >= 0.45 and consensus.ou_pick == "under")
            opportunities.append({
                **base,
                "market": f"Under {ou_line}",
                "win_pick": f"Under {ou_line}",
                "odds": round(under_odds, 2),
                "model_prob": round(under_prob, 4),
                "implied_prob": round(ou_true_under, 4),
                "edge": round(under_edge, 4),
                "ev": round(under_ev, 4),
                "should_bet": should_bet_under,
                "reasoning": consensus.reasoning,
            })

        # Sort by edge descending
        opportunities.sort(key=lambda x: x.get("edge", 0), reverse=True)
        return opportunities

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _fetch_live_odds_map(self) -> Dict:
        """Fetch all live odds at once and index by (home, away) tuple."""
        odds_map = {}
        if not self.odds_api.has_api():
            return odds_map
        try:
            games = self.odds_api.get_market_odds(sport="icehockey_nhl", market="h2h,totals")
            for game in games:
                home = game.get("home_team", "")
                away = game.get("away_team", "")
                home_ml = away_ml = over = under = ou_line = None
                for site in game.get("bookmakers", [])[:3]:
                    for mkt in site.get("markets", []):
                        key = mkt.get("key")
                        outcomes = {o["name"]: o["price"] for o in mkt.get("outcomes", [])}
                        if key == "h2h":
                            home_ml = outcomes.get(home)
                            away_ml = outcomes.get(away)
                        elif key == "totals":
                            over = outcomes.get("Over")
                            under = outcomes.get("Under")
                            # Extract line from first outcome description
                            for o in mkt.get("outcomes", []):
                                if o.get("name") == "Over":
                                    ou_line = o.get("point")
                                    break
                if home_ml and away_ml:
                    odds_map[(home, away)] = {
                        "home_ml": home_ml,
                        "away_ml": away_ml,
                        "over": over or 1.909,
                        "under": under or 1.909,
                        "ou_line": ou_line or 6.5,
                        "source": "theoddsapi",
                    }
        except Exception as e:
            print(f"  [odds] Live fetch error: {e}")
        return odds_map

    def _vote_summary(self, votes, consensus) -> str:
        ml_tally = consensus.ml_vote_tally
        ou_tally = consensus.ou_vote_tally
        ml_str = ", ".join(f"{k}: {v}" for k, v in ml_tally.items())
        ou_str = ", ".join(f"{k}: {v}" for k, v in ou_tally.items())
        return f"ML votes [{ml_str}] | O/U votes [{ou_str}]"
