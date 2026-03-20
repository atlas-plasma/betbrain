"""
Odds Processing and Value Detection
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass
import pandas as pd
from core.entities import GameOpportunity


@dataclass
class BettingOpportunity(GameOpportunity):
    """A betting opportunity with analysis."""
    pass


class OddsProcessor:
    """Process odds and find value bets."""

    def __init__(self, min_edge: float = 0.03, min_ev: float = 0.05):
        self.min_edge = min_edge
        self.min_ev = min_ev

    def odds_to_prob(self, odds: float) -> float:
        """Convert decimal odds to raw implied probability (includes vig)."""
        return 1.0 / odds

    def prob_to_odds(self, prob: float) -> float:
        """Convert probability to decimal odds."""
        return 1.0 / prob

    def devig_pair(self, odds_a: float, odds_b: float) -> Tuple[float, float]:
        """Remove bookmaker margin from a two-outcome market (multiplicative devig).

        Raw implied probs sum to >1 because of the vig.  Dividing each by the
        total gives the market's true probability estimate for each side.

        Example: home 1.90, away 1.90 → raw sum 1.053 → devigged 50/50.
        """
        raw_a = 1.0 / odds_a
        raw_b = 1.0 / odds_b
        total = raw_a + raw_b
        return raw_a / total, raw_b / total

    def calculate_edge(self, model_prob: float, true_implied_prob: float, odds: float) -> Tuple[float, float]:
        """Calculate edge and expected value against a devigged implied probability.

        Args:
            model_prob:        Our model's probability for the outcome.
            true_implied_prob: Market's probability *after* vig removal.
            odds:              Decimal odds (used to compute EV).
        """
        edge = model_prob - true_implied_prob
        ev = edge * odds
        return edge, ev

    def analyze_match(self, home_team: str, away_team: str,
                     prediction,
                     odds_home: float = None,
                     odds_away: float = None,
                     odds_over: float = None,
                     odds_under: float = None) -> List[BettingOpportunity]:
        """Analyze a match for betting opportunities."""

        opportunities = []

        # Moneyline analysis
        if odds_home and odds_away:
            # Devig both sides together so implied probs sum to 1
            true_implied_home, true_implied_away = self.devig_pair(odds_home, odds_away)

            edge_home, ev_home = self.calculate_edge(prediction.home_win_prob, true_implied_home, odds_home)
            edge_away, ev_away = self.calculate_edge(prediction.away_win_prob, true_implied_away, odds_away)

            # Home bet
            opportunities.append(BettingOpportunity(
                match=f"{home_team} vs {away_team}",
                market="ML (Home)",
                odds=odds_home,
                model_prob=prediction.home_win_prob,
                implied_prob=true_implied_home,
                edge=edge_home,
                ev=ev_home,
                recommendation="BET" if edge_home > self.min_edge and ev_home > self.min_ev else "SKIP",
                confidence=prediction.confidence,
                reasoning=self._get_reasoning(home_team, "home", edge_home, prediction)
            ))

            # Away bet
            opportunities.append(BettingOpportunity(
                match=f"{home_team} vs {away_team}",
                market="ML (Away)",
                odds=odds_away,
                model_prob=prediction.away_win_prob,
                implied_prob=true_implied_away,
                edge=edge_away,
                ev=ev_away,
                recommendation="BET" if edge_away > self.min_edge and ev_away > self.min_ev else "SKIP",
                confidence=prediction.confidence,
                reasoning=self._get_reasoning(away_team, "away", edge_away, prediction)
            ))

        # Over/Under analysis
        if odds_over and odds_under:
            true_implied_over, true_implied_under = self.devig_pair(odds_over, odds_under)
            edge_over, ev_over = self.calculate_edge(prediction.over_prob, true_implied_over, odds_over)

            opportunities.append(BettingOpportunity(
                match=f"{home_team} vs {away_team}",
                market="Over 5.5",
                odds=odds_over,
                model_prob=prediction.over_prob,
                implied_prob=true_implied_over,
                edge=edge_over,
                ev=ev_over,
                recommendation="BET" if edge_over > self.min_edge else "SKIP",
                confidence=prediction.confidence,
                reasoning=f"Expected {prediction.expected_home_goals + prediction.expected_away_goals:.1f} goals"
            ))

        return opportunities
    
    def _get_reasoning(self, team: str, side: str, edge: float, prediction) -> str:
        """Generate reasoning for bet."""
        
        if edge > 0.10:
            strength = "strong"
        elif edge > 0.05:
            strength = "moderate"
        elif edge > 0.03:
            strength = "slight"
        else:
            return "No significant edge"
        
        if side == "home":
            prob = prediction.home_win_prob * 100
        else:
            prob = prediction.away_win_prob * 100
        
        return f"{strength} edge detected. Model gives {team} {prob:.0f}% win probability."


class StrategyManager:
    """Manage betting strategies and bankroll."""
    
    def __init__(self, bankroll: float = 1000, kelly_fraction: float = 0.25):
        self.bankroll = bankroll
        self.kelly_fraction = kelly_fraction
    
    def calculate_kelly_bet(self, odds: float, prob: float) -> float:
        """Calculate Kelly Criterion bet size."""
        # Kelly formula: f* = (bp - q) / b
        # where b = odds - 1, p = probability, q = 1 - p
        b = odds - 1
        q = 1 - prob
        
        kelly = (b * prob - q) / b
        
        # Apply fraction to reduce risk
        return max(0, kelly * self.kelly_fraction)
    
    def rank_opportunities(self, opportunities: List[BettingOpportunity]) -> pd.DataFrame:
        """Rank opportunities by value."""
        
        data = []
        for opp in opportunities:
            data.append({
                "Match": opp.match,
                "Market": opp.market,
                "Odds": opp.odds,
                "Model %": f"{opp.model_prob * 100:.1f}%",
                "Implied %": f"{opp.implied_prob * 100:.1f}%",
                "Edge": f"{opp.edge * 100:.1f}%",
                "EV": f"{opp.ev * 100:.1f}%",
                "Rec": opp.recommendation,
                "Conf": opp.confidence,
                "Reasoning": opp.reasoning,
            })
        
        df = pd.DataFrame(data)
        
        # Sort by EV
        df = df.sort_values("EV", ascending=False)
        
        return df
    
    def get_top_picks(self, opportunities: List[BettingOpportunity], 
                     n: int = 3) -> Tuple[List, List]:
        """Get top value and safest picks."""
        
        bets = [o for o in opportunities if o.recommendation == "BET"]
        
        # Sort by edge for value
        by_value = sorted(bets, key=lambda x: x.edge, reverse=True)[:n]
        
        # Sort by confidence and prob for safety
        conf_order = {"high": 3, "medium": 2, "low": 1}
        by_safety = sorted(bets, 
                          key=lambda x: (conf_order.get(x.confidence, 0), x.model_prob), 
                          reverse=True)[:n]
        
        return by_value, by_safety


def process_odds(opportunities: List[BettingOpportunity]) -> pd.DataFrame:
    """Process and format opportunities for output."""
    
    manager = StrategyManager()
    return manager.rank_opportunities(opportunities)
