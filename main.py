"""
BetBrain - Sports Betting Analysis System
Main entry point for the betting bot
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from data.nhl import NHLDataFetcher
from models.predictor import get_model
from odds.scanner import OddsProcessor, StrategyManager


class BetBrain:
    """Main betting analysis system."""
    
    def __init__(self, sport: str = "nhl"):
        self.sport = sport
        self.model = get_model(config.MODELS["default"])
        self.odds_processor = OddsProcessor()
        self.strategy_manager = StrategyManager(
            bankroll=config.BANKROLL["initial"],
            kelly_fraction=config.BANKROLL["kelly_fraction"]
        )
        
        # Initialize data fetcher
        self.data_fetcher = NHLDataFetcher()
    
    def analyze(self, days: int = 3):
        """Analyze upcoming games and find value bets."""
        
        # Get schedule
        games = self.data_fetcher.get_schedule(days)
        
        if not games:
            print(f"No games found for {self.sport}")
            return []
        
        print(f"Found {len(games)} games")
        
        # Get team stats for each game
        opportunities = []
        
        for game in games:
            home = game.get("home_team")
            away = game.get("away_team")
            
            if not home or not away:
                continue
            
            # Get team stats
            home_stats = self.data_fetcher.get_team_stats(home)
            away_stats = self.data_fetcher.get_team_stats(away)
            
            print(f"Analyzing: {away} @ {home}")
            
            # Get prediction
            prediction = self.model.predict(home, away, home_stats, away_stats)
            
            # Get odds (simulated for now)
            odds = self._get_odds(home, away)
            
            # Find value
            opps = self.odds_processor.analyze_match(
                home, away, prediction,
                odds_home=odds.get("home_ml"),
                odds_away=odds.get("away_ml"),
                odds_over=odds.get("over"),
                odds_under=odds.get("under")
            )
            opportunities.extend(opps)
        
        return opportunities
    
    def _get_odds(self, home: str, away: str) -> dict:
        """Get odds (simulated for now - would connect to odds API)."""
        import random
        # Realistic odds between 1.5 and 3.0
        return {
            "home_ml": round(1.5 + random.random() * 1.5, 2),
            "away_ml": round(1.5 + random.random() * 1.5, 2),
            "over": 1.90,
            "under": 1.90
        }


def main():
    parser = argparse.ArgumentParser(description="BetBrain - Sports Betting Analysis")
    parser.add_argument("--sport", default="nhl", choices=["nhl", "nba", "soccer", "tennis"])
    parser.add_argument("--days", type=int, default=3, help="Days ahead to analyze")
    
    args = parser.parse_args()
    
    # Run analysis
    bot = BetBrain(sport=args.sport)
    opportunities = bot.analyze(days=args.days)
    
    # Get recommendations
    bets = [o for o in opportunities if o.recommendation == "BET"]
    
    print(f"\n🏆 BetBrain - {args.sport.upper()} Analysis")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 50)
    
    if bets:
        print(f"\n✅ Found {len(bets)} value bets!\n")
        for i, bet in enumerate(bets, 1):
            print(f"{i}. {bet.match} {bet.market}")
            print(f"   Odds: {bet.odds} | Edge: {bet.edge*100:+.1f}% | EV: {bet.ev*100:+.1f}%")
            print(f"   Reasoning: {bet.reasoning}")
    else:
        print("\n❌ No value bets found today.")


if __name__ == "__main__":
    main()
