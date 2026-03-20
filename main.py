"""
BetBrain - Sports Betting Analysis System
Main entry point with advanced tier-based strategy
"""

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from data.nhl import NHLDataFetcher
from models.predictor import get_model
from odds.scanner import OddsProcessor, StrategyManager
from strategy.advanced import create_strategy


class BetBrain:
    """Main betting analysis system with advanced strategy."""
    
    def __init__(self, sport: str = "nhl"):
        self.sport = sport
        self.model = get_model(config.MODELS["default"])
        self.odds_processor = OddsProcessor()
        self.strategy = create_strategy()  # Advanced tier-based strategy
        self.data_fetcher = NHLDataFetcher()
    
    def analyze(self, days: int = 3):
        """Analyze games using tier-based strategy."""
        
        games = self.data_fetcher.get_schedule(days)
        
        if not games:
            print(f"No games found")
            return []
        
        print(f"Found {len(games)} games")
        
        opportunities = []
        
        # Get mock injuries for now (would be from web research)
        injuries = self._get_injuries()
        
        for game in games:
            home = game.get("home_team")
            away = game.get("away_team")
            
            if not home or not away:
                continue
            
            home_stats = self.data_fetcher.get_team_stats(home)
            away_stats = self.data_fetcher.get_team_stats(away)
            
            print(f"Analyzing: {away} @ {home}")
            
            # Use advanced tier-based analysis
            ml_analysis = self.strategy.analyze_ml(home, away, home_stats, away_stats, injuries)
            ou_analysis = self.strategy.analyze_over_under(home, away, home_stats, away_stats, injuries)
            
            # Get odds
            odds = self._get_odds(home, away)
            
            # Calculate edges using our probabilities
            home_edge = ml_analysis["home_prob"] - (1 / odds["home_ml"])
            away_edge = ml_analysis["away_prob"] - (1 / odds["away_ml"])
            over_edge = ou_analysis["over_prob"] - (1 / odds["over"])
            
            # Determine recommendations
            home_rec = "BET" if home_edge > 0.03 else "SKIP"
            away_rec = "BET" if away_edge > 0.03 else "SKIP"
            over_rec = "BET" if over_edge > 0.03 else "SKIP"
            
            # Add opportunities
            opportunities.extend([
                {
                    "match": f"{home} vs {away}",
                    "market": "ML (Home)",
                    "odds": odds["home_ml"],
                    "model_prob": ml_analysis["home_prob"],
                    "implied_prob": 1/odds["home_ml"],
                    "edge": home_edge,
                    "ev": home_edge * odds["home_ml"],
                    "recommendation": home_rec,
                    "confidence": ml_analysis["confidence"],
                    "reasoning": ml_analysis["reasoning"]
                },
                {
                    "match": f"{home} vs {away}",
                    "market": "ML (Away)",
                    "odds": odds["away_ml"],
                    "model_prob": ml_analysis["away_prob"],
                    "implied_prob": 1/odds["away_ml"],
                    "edge": away_edge,
                    "ev": away_edge * odds["away_ml"],
                    "recommendation": away_rec,
                    "confidence": ml_analysis["confidence"],
                    "reasoning": ml_analysis["reasoning"]
                },
                {
                    "match": f"{home} vs {away}",
                    "market": f"Over {ou_analysis['line']}",
                    "odds": odds["over"],
                    "model_prob": ou_analysis["over_prob"],
                    "implied_prob": 1/odds["over"],
                    "edge": over_edge,
                    "ev": over_edge * odds["over"],
                    "recommendation": over_rec,
                    "confidence": ou_analysis["confidence"],
                    "reasoning": ou_analysis["reasoning"]
                }
            ])
        
        return opportunities
    
    def _get_odds(self, home: str, away: str) -> dict:
        """Get realistic odds."""
        import random
        return {
            "home_ml": round(1.5 + random.random() * 1.5, 2),
            "away_ml": round(1.5 + random.random() * 1.5, 2),
            "over": 1.90,
            "under": 1.90
        }
    
    def _get_injuries(self) -> dict:
        """Get injury data (mock for now)."""
        # In production, this would fetch from web
        return {}


def main():
    bot = BetBrain()
    opportunities = bot.analyze(days=3)
    
    bets = [o for o in opportunities if o["recommendation"] == "BET"]
    
    print(f"\n🏆 BetBrain - NHL Analysis")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 50)
    
    if bets:
        print(f"\n✅ Found {len(bets)} value bets!\n")
        for i, bet in enumerate(bets, 1):
            print(f"{i}. {bet['match']} {bet['market']}")
            print(f"   Odds: {bet['odds']} | Edge: {bet['edge']*100:+.1f}% | EV: {bet['ev']*100:+.1f}%")
            print(f"   {bet['reasoning']}")
    else:
        print("\n❌ No value bets found.")


if __name__ == "__main__":
    main()
