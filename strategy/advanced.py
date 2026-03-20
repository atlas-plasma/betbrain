"""
Advanced Betting Strategy - Tier-Based with Injury Analysis
Based on Claude's strategy methodology
"""

from typing import Dict, List, Tuple
import random


class AdvancedStrategy:
    """Tier-based betting strategy with injury analysis."""
    
    # Team tiers based on win rate
    TIERS = {
        "elite": 0.60,      # 60%+ win rate
        "contender": 0.50,  # 50-59%
        "bubble": 0.44,     # 44-50%
        "struggling": 0.44  # <44%
    }
    
    # Injury impact scores
    INJURY_IMPACT = {
        3: "High - Top player, significantly impacts team",
        2: "Moderate - Depth player, noticeable impact",
        1: "Low - 4th liner, minimal impact"
    }
    
    def __init__(self):
        self.teams = self._load_team_tiers()
    
    def _load_team_tiers(self) -> Dict[str, str]:
        """Assign tiers to teams."""
        # Based on typical NHL standings - would be dynamic in production
        return {
            # Elite (60%+)
            "COL": "elite", "CAR": "elite", "DAL": "elite", 
            "TBL": "elite", "WSH": "elite", "NJ": "elite",
            # Contender (50-59%)
            "MIN": "contender", "NYI": "contender", "PIT": "contender",
            "OTT": "contender", "EDM": "contender", "BOS": "contender",
            "MTL": "contender", "DET": "contender", "VGK": "contender",
            # Bubble (44-50%)
            "NSH": "bubble", "SEA": "bubble", "UTA": "bubble",
            "SJS": "bubble", "PHI": "bubble", "CBJ": "bubble",
            "BUF": "bubble", "STL": "bubble", "LAK": "bubble",
            # Struggling (<44%)
            "CHI": "struggling", "WPG": "struggling", "CGY": "struggling",
            "VAN": "struggling", "ANA": "struggling", "ARI": "struggling",
            "FLA": "contender",  # Florida is strong
        }
    
    def get_team_tier(self, team: str) -> str:
        """Get team's tier."""
        return self.teams.get(team, "bubble")
    
    def analyze_ml(self, home: str, away: str, 
                   home_stats: Dict, away_stats: Dict,
                   injuries: Dict) -> Dict:
        """Analyze moneyline bet."""
        
        home_tier = self.get_team_tier(home)
        away_tier = self.get_team_tier(away)
        
        home_wr = home_stats.get("win_rate", 0.5)
        away_wr = away_stats.get("win_rate", 0.5)
        
        # Calculate base probability from tiers
        tier_advantage = {
            ("elite", "struggling"): 0.15,
            ("elite", "bubble"): 0.10,
            ("elite", "contender"): 0.05,
            ("contender", "struggling"): 0.10,
            ("contender", "bubble"): 0.05,
            ("bubble", "struggling"): 0.05,
        }
        
        # Base probability from win rate
        base_home = home_wr
        base_away = away_wr
        
        # Add tier adjustment
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
        
        # Generate reasoning
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
        
        expected_total = home_gf + away_gf
        
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
        over_prob = 1 / (1 + (line / expected_total))
        
        # Confidence based on deviation from line
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
            "confidence": confidence,
            "reasoning": f"Expected {expected_total:.1f} goals vs line {line}"
        }


def create_strategy() -> AdvancedStrategy:
    """Create advanced strategy instance."""
    return AdvancedStrategy()
