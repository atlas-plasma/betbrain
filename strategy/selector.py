"""
Strategy selector for different betting approaches
"""

from typing import Dict, List


class StrategySelector:
    """Multiple strategies to choose from."""
    
    STRATEGIES = {
        "value": {
            "name": "Value Betting",
            "description": "Positive edge only (>3%), moderate confidence",
            "min_edge": 0.03,
            "max_confidence": "medium",  # Cap at medium for realism
        },
        "conservative": {
            "name": "Conservative",
            "description": "High probability bets (>55%), lower returns",
            "min_probability": 0.55,
            "max_confidence": "high",
        },
        "aggressive": {
            "name": "Aggressive",
            "description": "Higher edge (>5%), higher variance",
            "min_edge": 0.05,
            "max_confidence": "any",
        },
        "tier_based": {
            "name": "Tier-Based (Claude)",
            "description": "Team tiers + injuries + form analysis",
            "min_edge": 0.03,
            "max_confidence": "high",
        },
        "model_plus": {
            "name": "Model Plus",
            "description": "Win probability + injury impact + form convergence",
            "min_edge": 0.02,
            "max_confidence": "high",
        }
    }
    
    def __init__(self, strategy_name: str = "value"):
        self.strategy_name = strategy_name
        self.config = self.STRATEGIES.get(strategy_name, self.STRATEGIES["value"])
    
    def should_bet(self, opportunity: Dict) -> bool:
        """Determine if opportunity passes strategy filters."""
        
        edge = opportunity.get("edge", 0)
        prob = opportunity.get("model_prob", 0)
        confidence = opportunity.get("confidence", "low")
        
        strategy = self.strategy_name
        
        if strategy == "value":
            return edge > 0.03
        
        elif strategy == "conservative":
            return prob > 0.55
        
        elif strategy == "aggressive":
            return edge > 0.05
        
        elif strategy == "tier_based":
            return edge > 0.03
        
        elif strategy == "model_plus":
            # Require multiple converging signals
            has_edge = edge > 0.02
            has_confidence = confidence in ["medium", "high"]
            return has_edge and has_confidence
        
        return edge > 0.03
    
    def get_confidence_cap(self) -> str:
        """Get realistic confidence cap based on strategy."""
        return self.config.get("max_confidence", "medium")
    
    def get_info(self) -> Dict:
        """Get strategy info."""
        return self.config


def create_strategy(name: str) -> StrategySelector:
    """Factory function."""
    return StrategySelector(name)
