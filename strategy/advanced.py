"""
Advanced Betting Strategy - Tier-Based with Injury Analysis
"""

from typing import Dict, List, Tuple
from scipy.stats import poisson as poisson_dist


class AdvancedStrategy:
    """Tier-based betting strategy with injury analysis."""

    # Minimum games before trusting a team's win rate
    MIN_GAMES_FOR_FULL_TRUST = 20

    # Injury impact scores
    INJURY_IMPACT = {
        3: "High - Top player, significantly impacts team",
        2: "Moderate - Depth player, noticeable impact",
        1: "Low - 4th liner, minimal impact"
    }

    def __init__(self):
        pass

    def get_team_tier(self, team: str, win_rate: float = None) -> str:
        """Derive tier dynamically from win rate.

        win_rate is required for accurate classification.  Falls back to
        "bubble" (the neutral default) when unavailable.
        """
        if win_rate is None:
            return "bubble"
        if win_rate >= 0.60:
            return "elite"
        elif win_rate >= 0.50:
            return "contender"
        elif win_rate >= 0.44:
            return "bubble"
        else:
            return "struggling"
    
    def analyze_ml(self, home: str, away: str, 
                   home_stats: Dict, away_stats: Dict,
                   injuries: Dict) -> Dict:
        """Analyze moneyline bet."""

        home_wr = home_stats.get("win_rate", 0.5)
        away_wr = away_stats.get("win_rate", 0.5)

        # Bayesian shrinkage: if sample is small, regress win rate toward 0.5
        home_gp = home_stats.get("games_played", self.MIN_GAMES_FOR_FULL_TRUST)
        away_gp = away_stats.get("games_played", self.MIN_GAMES_FOR_FULL_TRUST)
        home_trust = min(1.0, home_gp / self.MIN_GAMES_FOR_FULL_TRUST)
        away_trust = min(1.0, away_gp / self.MIN_GAMES_FOR_FULL_TRUST)
        home_wr = 0.5 + (home_wr - 0.5) * home_trust
        away_wr = 0.5 + (away_wr - 0.5) * away_trust

        # Derive tiers from actual current win rates (not hardcoded lookup)
        home_tier = self.get_team_tier(home, home_wr)
        away_tier = self.get_team_tier(away, away_wr)

        # Tier advantage adds a small signal on top of the raw win-rate difference.
        # Values are conservative: a win-rate spread already captures most of the
        # matchup quality; tiers add only the structural matchup adjustment.
        tier_advantage = {
            ("elite", "struggling"): 0.08,
            ("elite", "bubble"): 0.05,
            ("elite", "contender"): 0.02,
            ("contender", "struggling"): 0.05,
            ("contender", "bubble"): 0.02,
            ("bubble", "struggling"): 0.02,
        }

        base_home = home_wr
        base_away = away_wr

        tier_key = (home_tier, away_tier)
        if tier_key in tier_advantage:
            base_home += tier_advantage[tier_key]

        # Injury impact
        home_inj_impact = self._calculate_injury_impact(home, injuries)
        away_inj_impact = self._calculate_injury_impact(away, injuries)

        base_home -= away_inj_impact * 0.02
        base_away += home_inj_impact * 0.02

        # Normalize
        total = base_home + base_away
        home_prob = base_home / total if total > 0 else 0.5
        away_prob = 1 - home_prob

        # Determine confidence
        tier_diff = self._get_tier_strength(home_tier) - self._get_tier_strength(away_tier)

        if abs(tier_diff) >= 2 and home_prob > 0.65:
            confidence = "high"
        elif home_prob > 0.55:
            confidence = "medium"
        else:
            confidence = "low"

        reasoning = self._generate_reasoning(home, away, home_tier, away_tier,
                                             home_stats, away_stats, injuries)

        return {
            "home_prob": home_prob,
            "away_prob": away_prob,
            "confidence": confidence,
            "reasoning": reasoning,
            "tier_advantage": f"{home_tier} vs {away_tier}"
        }
    
    def _calculate_injury_impact(self, team: str, injuries: Dict) -> int:
        """Calculate total injury impact for a team."""
        team_injuries = injuries.get(team, [])
        total = sum(inj.get("impact", 2) for inj in team_injuries)
        return min(total, 5)  # Cap at 5
    
    def _get_tier_strength(self, tier: str) -> int:
        """Convert tier to numeric strength."""
        return {"elite": 4, "contender": 3, "bubble": 2, "struggling": 1}.get(tier, 2)
    
    def _generate_reasoning(self, home: str, away: str, home_tier: str, away_tier: str,
                          home_stats: Dict, away_stats: Dict, injuries: Dict) -> str:
        """Generate detailed reasoning."""
        reasons = []
        
        # Tier advantage
        if home_tier == "elite" and away_tier in ["bubble", "struggling"]:
            reasons.append(f"{home} (Elite) vs {away} ({away_tier}) - strong favorite")
        elif away_tier == "elite" and home_tier in ["bubble", "struggling"]:
            reasons.append(f"{away} (Elite) vs {home} ({home_tier}) - underdog")
        
        # Form
        home_form = home_stats.get("form", 0.5) * 100
        away_form = away_stats.get("form", 0.5) * 100
        
        if home_form > 65:
            reasons.append(f"{home} hot ({home_form:.0f}%)")
        elif home_form < 35:
            reasons.append(f"{home} cold ({home_form:.0f}%)")
        
        if away_form > 65:
            reasons.append(f"{away} hot ({away_form:.0f}%)")
        elif away_form < 35:
            reasons.append(f"{away} cold ({away_form:.0f}%)")
        
        # Injuries
        home_inj = injuries.get(home, [])
        away_inj = injuries.get(away, [])
        
        if len(home_inj) >= 2:
            reasons.append(f"{home} missing {len(home_inj)} players")
        if len(away_inj) >= 2:
            reasons.append(f"{away} missing {len(away_inj)} players")
        
        # Home ice
        home_wr = home_stats.get("home_win_rate", 0.5) * 100
        if home_wr > 60:
            reasons.append(f"{home} dominant at home ({home_wr:.0f}%)")
        
        return " | ".join(reasons) if reasons else "No strong factors"
    
    def analyze_over_under(self, home: str, away: str,
                          home_stats: Dict, away_stats: Dict,
                          injuries: Dict) -> Dict:
        """Analyze over/under bet."""
        
        # Calculate expected goals
        home_gf = home_stats.get("goals_for_avg", 2.8)
        away_gf = away_stats.get("goals_for_avg", 2.8)
        home_ga = home_stats.get("goals_against_avg", 2.8)
        away_ga = away_stats.get("goals_against_avg", 2.8)

        # Blend attack vs opponent defence for each side
        pred_home_goals = round((home_gf + away_ga) / 2, 1)
        pred_away_goals = round((away_gf + home_ga) / 2, 1)

        expected_total = pred_home_goals + pred_away_goals
        
        # Adjust for injuries to high-scoring players
        home_inj = injuries.get(home, [])
        away_inj = injuries.get(away, [])
        
        # If key scorers injured, reduce expected goals
        for inj in home_inj:
            if inj.get("impact", 2) >= 3:
                expected_total -= 0.3
        
        for inj in away_inj:
            if inj.get("impact", 2) >= 3:
                expected_total -= 0.3
        
        # Over/Under line is typically 6.5 for NHL
        line = 6.5

        # Use Poisson CDF: P(total goals > line) where total ~ Poisson(expected_total).
        # poisson_dist.cdf(k, mu) = P(X <= k), so P(X > line) = 1 - P(X <= floor(line)).
        expected_total = max(0.1, expected_total)
        over_prob = 1.0 - poisson_dist.cdf(int(line), expected_total)
        under_prob = 1.0 - over_prob

        # Confidence based on how far expected total is from the line
        diff = abs(expected_total - line)

        if diff > 1.0:
            confidence = "high"
        elif diff > 0.5:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "expected": expected_total,
            "line": line,
            "over_prob": over_prob,
            "under_prob": under_prob,
            "predicted_total": round(expected_total, 1),
            "home_goals": pred_home_goals,
            "away_goals": pred_away_goals,
            "score_pred": f"{pred_home_goals} - {pred_away_goals}",
            "confidence": confidence,
            "reasoning": f"Projected {pred_home_goals} - {pred_away_goals} ({expected_total:.1f} total) vs line {line}",
        }


def create_strategy() -> AdvancedStrategy:
    """Create advanced strategy instance."""
    return AdvancedStrategy()
