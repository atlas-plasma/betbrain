"""
BetBrain Analysis Pipeline — research-grade edition.

Per game:
  1.  Fetch base team stats (NHL standings API — real season data)
  2.  Enrich with advanced stats: goalie quality, PDO, back-to-back,
      home/away true splits, L10 form, Pythagorean expectation
  3.  Fetch live odds (TheOddsAPI or deterministic fallback)
  4.  Run all 5 agents → vote
  5.  Weighted consensus → final pick + Kelly stake
  6.  Return opportunity dicts for the dashboard
"""

import os
from datetime import datetime
from typing import List, Dict

from data.nhl import NHLDataFetcher
from data.nhl_advanced import NHLAdvancedStats
from odds.odds_api import OddsAPIFetcher
from agents.statistical import StatisticalAgent
from agents.elo import ELOAgent
from agents.form import FormAgent
from agents.research import ResearchAgent
from agents.claude_agent import ClaudeAgent
from agents.consensus import ConsensusAggregator, INITIAL_BANKROLL

_OU_LINES = [4.5, 5.5, 6.5, 7.5]


def _snap_ou(expected: float) -> float:
    return min(_OU_LINES, key=lambda x: abs(x - expected))


def _devig(odds_a: float, odds_b: float):
    raw_a, raw_b = 1.0 / odds_a, 1.0 / odds_b
    total = raw_a + raw_b
    return raw_a / total, raw_b / total


def _ev(model_prob: float, odds: float) -> float:
    return model_prob * (odds - 1) - (1 - model_prob)


def _conf_label(conf: float) -> str:
    if conf >= 0.60:
        return "high"
    elif conf >= 0.44:
        return "medium"
    return "low"


class BetBrainPipeline:

    def __init__(self):
        self.nhl     = NHLDataFetcher()
        self.advanced = NHLAdvancedStats()
        self.odds_api = OddsAPIFetcher()
        self.agents   = [
            StatisticalAgent(),
            ELOAgent(),
            FormAgent(),
            ResearchAgent(),
            ClaudeAgent(),
        ]
        self.aggregator = ConsensusAggregator()

    def run(self, days: int = 3) -> List[Dict]:
        games = self.nhl.get_schedule(days_forward=days * 10)
        if not games:
            return []

        # Load standings once for all teams
        standings = self.nhl._load_standings()

        # Batch odds if API available
        live_odds_map = self._fetch_live_odds_map()

        stats_cache: Dict[str, Dict] = {}
        opportunities = []
        seen = set()

        for game in games:
            home = game.get("home_team")
            away = game.get("away_team")
            if not home or not away:
                continue

            key = (home, away, game.get("date", ""))
            if key in seen:
                continue
            seen.add(key)

            if len(opportunities) >= days * 12:
                break

            game_date = game.get("date", datetime.now().strftime("%Y-%m-%d"))

            # Get and enrich stats
            if home not in stats_cache:
                base = self.nhl.get_team_stats(home)
                stats_cache[home] = self.advanced.enrich(home, game_date, standings)
                # Fill any gaps from base
                for k, v in base.items():
                    if k not in stats_cache[home]:
                        stats_cache[home][k] = v
            if away not in stats_cache:
                base = self.nhl.get_team_stats(away)
                stats_cache[away] = self.advanced.enrich(away, game_date, standings)
                for k, v in base.items():
                    if k not in stats_cache[away]:
                        stats_cache[away][k] = v

            home_stats = stats_cache[home]
            away_stats = stats_cache[away]

            # Odds
            live = live_odds_map.get((home, away)) or live_odds_map.get((away, home))
            if live:
                home_ml = live.get("home_ml", 2.0)
                away_ml = live.get("away_ml", 2.0)
                ou_line = live.get("ou_line", 6.5)
                over_odds  = live.get("over", 1.909)
                under_odds = live.get("under", 1.909)
                odds_source = "theoddsapi"
            else:
                fb = self.odds_api.get_fallback_odds(
                    home_stats.get("win_rate", 0.5),
                    away_stats.get("win_rate", 0.5),
                )
                home_ml = fb["home_ml"]
                away_ml = fb["away_ml"]
                stat_vote_preview = StatisticalAgent().analyze(
                    home, away, home_stats, away_stats
                )
                exp_total = (
                    stat_vote_preview.extra.get("home_lambda", 3.0) +
                    stat_vote_preview.extra.get("away_lambda", 3.0)
                )
                ou_line = _snap_ou(exp_total)
                over_odds  = 1.909
                under_odds = 1.909
                odds_source = "fallback"

            # Agent votes
            votes = [
                a.analyze(home, away, home_stats, away_stats, ou_line)
                for a in self.agents
            ]

            consensus = self.aggregator.aggregate(
                home, away, votes,
                home_ml_odds=home_ml,
                away_ml_odds=away_ml,
                ou_odds=1.909,
            )

            # Devig implied probs
            true_home_impl, true_away_impl = _devig(home_ml, away_ml)
            true_over_impl, true_under_impl = _devig(over_odds, under_odds)

            # ML metrics
            if consensus.ml_pick == "home":
                ml_model_p = consensus.home_win_prob
                ml_impl_p  = true_home_impl
                ml_odds_v  = home_ml
                ml_pick_label = home
            elif consensus.ml_pick == "away":
                ml_model_p = consensus.away_win_prob
                ml_impl_p  = true_away_impl
                ml_odds_v  = away_ml
                ml_pick_label = away
            else:
                # Still show best side even for skip
                if consensus.home_win_prob - true_home_impl >= consensus.away_win_prob - true_away_impl:
                    ml_model_p, ml_impl_p, ml_odds_v, ml_pick_label = (
                        consensus.home_win_prob, true_home_impl, home_ml, home)
                else:
                    ml_model_p, ml_impl_p, ml_odds_v, ml_pick_label = (
                        consensus.away_win_prob, true_away_impl, away_ml, away)

            ml_edge = ml_model_p - ml_impl_p
            ml_ev   = _ev(ml_model_p, ml_odds_v)

            # O/U metrics
            over_edge  = consensus.over_prob - true_over_impl
            under_edge = (1 - consensus.over_prob) - true_under_impl
            over_ev    = _ev(consensus.over_prob, over_odds)
            under_ev   = _ev(1 - consensus.over_prob, under_odds)

            # Stat agent lambdas for score prediction
            stat_v = next((v for v in votes if v.agent_name == "Statistical"), None)
            h_lam  = stat_v.extra.get("home_lambda", 3.0) if stat_v else 3.0
            a_lam  = stat_v.extra.get("away_lambda", 3.0) if stat_v else 3.0

            # B2B and PDO signals for display
            home_b2b = home_stats.get("back_to_back", False)
            away_b2b = away_stats.get("back_to_back", False)
            home_pdo = home_stats.get("pdo", 100)
            away_pdo = away_stats.get("pdo", 100)
            home_goalie = home_stats.get("goalie_name", "")
            away_goalie = away_stats.get("goalie_name", "")

            # Should-bet thresholds
            should_bet_ml = (
                ml_edge >= 0.03
                and consensus.ml_confidence >= 0.45
                and consensus.ml_pick != "skip"
            )
            should_bet_over = (
                over_edge >= 0.03
                and consensus.ou_confidence >= 0.45
                and consensus.ou_pick == "over"
            )
            should_bet_under = (
                under_edge >= 0.03
                and consensus.ou_confidence >= 0.45
                and consensus.ou_pick == "under"
            )

            base = {
                "match":       f"{away} @ {home}",
                "home_team":   home,
                "away_team":   away,
                "start_time":  game.get("start_time", "TBD"),
                "date":        game_date,
                "odds_source": odds_source,
                "score_pred":  f"{h_lam:.1f} - {a_lam:.1f}",
                "pred_total":  round(h_lam + a_lam, 1),
                "ou_line":     ou_line,
                "over_prob":   round(consensus.over_prob * 100, 1),
                "under_prob":  round((1 - consensus.over_prob) * 100, 1),
                "confidence":  consensus.tier,
                "ml_vote_tally": consensus.ml_vote_tally,
                "ou_vote_tally": consensus.ou_vote_tally,
                # Advanced signals
                "home_pdo":    home_pdo,
                "away_pdo":    away_pdo,
                "home_pdo_label": home_stats.get("pdo_label", "neutral"),
                "away_pdo_label": away_stats.get("pdo_label", "neutral"),
                "home_goalie": home_goalie,
                "away_goalie": away_goalie,
                "home_goalie_sv": round(home_stats.get("goalie_sv_pct", 0.908) * 100, 1),
                "away_goalie_sv": round(away_stats.get("goalie_sv_pct", 0.908) * 100, 1),
                "home_b2b":    home_b2b,
                "away_b2b":    away_b2b,
                "home_pyth":   round(home_stats.get("pyth_win_pct", 0.5) * 100, 1),
                "away_pyth":   round(away_stats.get("pyth_win_pct", 0.5) * 100, 1),
                "agent_votes": [
                    {
                        "agent":    v.agent_name,
                        "ml":       v.ml_pick,
                        "ml_conf":  round(v.ml_confidence * 100, 1),
                        "ou":       v.ou_pick,
                        "ou_conf":  round(v.ou_confidence * 100, 1),
                        "reasoning": v.reasoning,
                    }
                    for v in votes
                ],
                "vote_summary": self._vote_summary(consensus),
                "reasoning": consensus.reasoning,
            }

            # Moneyline row
            opportunities.append({
                **base,
                "market":       "Moneyline",
                "win_pick":     ml_pick_label,
                "odds":         round(ml_odds_v, 2),
                "model_prob":   round(ml_model_p, 4),
                "implied_prob": round(ml_impl_p, 4),
                "edge":         round(ml_edge, 4),
                "ev":           round(ml_ev, 4),
                "kelly":        consensus.kelly_ml,
                "should_bet":   should_bet_ml,
            })

            # Over row
            opportunities.append({
                **base,
                "market":       f"Over {ou_line}",
                "win_pick":     f"Over {ou_line}",
                "odds":         round(over_odds, 2),
                "model_prob":   round(consensus.over_prob, 4),
                "implied_prob": round(true_over_impl, 4),
                "edge":         round(over_edge, 4),
                "ev":           round(over_ev, 4),
                "kelly":        consensus.kelly_ou,
                "should_bet":   should_bet_over,
            })

            # Under row
            opportunities.append({
                **base,
                "market":       f"Under {ou_line}",
                "win_pick":     f"Under {ou_line}",
                "odds":         round(under_odds, 2),
                "model_prob":   round(1 - consensus.over_prob, 4),
                "implied_prob": round(true_under_impl, 4),
                "edge":         round(under_edge, 4),
                "ev":           round(under_ev, 4),
                "kelly":        consensus.kelly_ou,
                "should_bet":   should_bet_under,
            })

        opportunities.sort(key=lambda x: x.get("edge", 0), reverse=True)
        return opportunities

    def _fetch_live_odds_map(self) -> Dict:
        odds_map = {}
        if not self.odds_api.has_api():
            return odds_map
        try:
            games = self.odds_api.get_market_odds(
                sport="icehockey_nhl", market="h2h,totals"
            )
            for game in games:
                home = game.get("home_team", "")
                away = game.get("away_team", "")
                home_ml = away_ml = over = under = ou_line = None
                for site in game.get("bookmakers", [])[:3]:
                    for mkt in site.get("markets", []):
                        k = mkt.get("key")
                        outs = {o["name"]: o["price"] for o in mkt.get("outcomes", [])}
                        if k == "h2h":
                            home_ml = home_ml or outs.get(home)
                            away_ml = away_ml or outs.get(away)
                        elif k == "totals":
                            over  = over  or outs.get("Over")
                            under = under or outs.get("Under")
                            for o in mkt.get("outcomes", []):
                                if o.get("name") == "Over" and not ou_line:
                                    ou_line = o.get("point")
                if home_ml and away_ml:
                    odds_map[(home, away)] = {
                        "home_ml": home_ml,
                        "away_ml": away_ml,
                        "over":    over    or 1.909,
                        "under":   under   or 1.909,
                        "ou_line": ou_line or 6.5,
                    }
        except Exception as e:
            print(f"  [odds] {e}")
        return odds_map

    def _vote_summary(self, consensus) -> str:
        ml = ", ".join(f"{k}:{v:.2f}" for k, v in consensus.ml_vote_tally.items())
        ou = ", ".join(f"{k}:{v:.2f}" for k, v in consensus.ou_vote_tally.items())
        return f"ML [{ml}] O/U [{ou}]"
