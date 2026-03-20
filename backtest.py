"""
Backtesting module for BetBrain
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
import json


class Backtester:
    """Backtest betting strategies."""
    
    def __init__(self, sport: str, strategy: str = "value"):
        self.sport = sport
        self.strategy = strategy
        self.bankroll = 1000
        self.initial_bankroll = 1000
        
    def run(self, start_date: str, end_date: str) -> Dict:
        """Run backtest over date range."""
        
        # Load historical data (would be real data in production)
        games = self._load_historical_games(start_date, end_date)
        
        results = []
        
        for game in games:
            # Get prediction
            prediction = game.get("prediction", {})
            
            # Get actual odds
            odds = game.get("odds", {})
            
            # Check if bet meets criteria
            if self._should_bet(prediction, odds):
                stake = self._calculate_stake(prediction, odds)
                result = self._process_bet(game, stake)
                results.append(result)
                
                # Update bankroll
                self.bankroll += result.get("profit", 0)
        
        # Calculate metrics
        metrics = self._calculate_metrics(results)
        
        return metrics
    
    def _load_historical_games(self, start_date: str, end_date: str) -> List[Dict]:
        """Load historical game data."""
        # This would load real historical data
        # For now, return empty list
        return []
    
    def _should_bet(self, prediction: Dict, odds: Dict) -> bool:
        """Determine if bet meets strategy criteria."""
        
        if self.strategy == "value":
            # Value betting: positive expected value
            home_prob = prediction.get("home_prob", 0)
            home_odds = odds.get("home_ml", 2.0)
            implied_prob = 1 / home_odds
            edge = home_prob - implied_prob
            
            return edge > 0.03  # 3% minimum edge
            
        elif self.strategy == "conservative":
            # Conservative: high probability bets
            home_prob = prediction.get("home_prob", 0)
            return home_prob > 0.60
            
        elif self.strategy == "aggressive":
            # Aggressive: high edge bets
            home_prob = prediction.get("home_prob", 0)
            home_odds = odds.get("home_ml", 2.0)
            implied_prob = 1 / home_odds
            edge = home_prob - implied_prob
            
            return edge > 0.05  # 5% minimum edge
        
        return False
    
    def _calculate_stake(self, prediction: Dict, odds: Dict) -> float:
        """Calculate bet stake using Kelly criterion."""
        # Simplified Kelly
        home_prob = prediction.get("home_prob", 0.5)
        home_odds = odds.get("home_ml", 2.0)
        
        b = home_odds - 1
        q = 1 - home_prob
        kelly = (b * home_prob - q) / b
        
        # Fractional Kelly (25%)
        stake = max(0, kelly * 0.25 * self.bankroll)
        
        return min(stake, self.bankroll * 0.1)  # Max 10% of bankroll
    
    def _process_bet(self, game: Dict, stake: float) -> Dict:
        """Process a single bet."""
        # Simplified - would need actual game outcome
        return {
            "game": game.get("match"),
            "stake": stake,
            "odds": game.get("odds", {}),
            "won": False,  # Would be determined by actual result
            "profit": 0
        }
    
    def _calculate_metrics(self, results: List[Dict]) -> Dict:
        """Calculate performance metrics."""
        
        if not results:
            return {
                "total_return": 0,
                "total_bets": 0,
                "won": 0,
                "lost": 0,
                "win_rate": 0
            }
        
        wins = sum(1 for r in results if r.get("won"))
        losses = len(results) - wins
        
        total_return = (self.bankroll - self.initial_bankroll) / self.initial_bankroll
        
        # Calculate drawdown
        bankroll_peak = self.initial_bankroll
        max_drawdown = 0
        
        # Simplified metrics
        return {
            "total_return": total_return,
            "total_bets": len(results),
            "won": wins,
            "lost": losses,
            "win_rate": wins / len(results) if results else 0,
            "final_bankroll": self.bankroll,
            "sharpe": "N/A",  # Would calculate with daily returns
            "max_drawdown": max_drawdown
        }


def run_backtest(sport: str, start_date: str, end_date: str, strategy: str = "value") -> Dict:
    """Run backtest and return results."""
    
    backtester = Backtester(sport, strategy)
    results = backtester.run(start_date, end_date)
    
    return results


if __name__ == "__main__":
    # Demo backtest
    results = run_backtest("nhl", "2024-01-01", "2024-12-31", "value")
    print("Backtest Results:", results)
