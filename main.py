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
from data.nba import NBADataFetcher
from data.soccer import SoccerDataFetcher
from models.predictor import get_model
from odds.scanner import OddsProcessor, StrategyManager
from backtest import run_backtest
from papertrade import PaperTrader


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
        self.data_fetcher = self._get_fetcher(sport)
    
    def _get_fetcher(self, sport: str):
        fetchers = {
            "nhl": NHLDataFetcher,
            "nba": NBADataFetcher,
            "soccer": SoccerDataFetcher,
        }
        return fetchers.get(sport, NHLDataFetcher)()
    
    def analyze(self, days: int = 3):
        """Analyze upcoming games and find value bets."""
        
        # Get schedule
        games = self.data_fetcher.get_schedule(days)
        
        if not games:
            print(f"No games found for {self.sport}")
            return []
        
        # Get team stats
        team_stats = {}
        for game in games:
            home = game.get("home_team")
            away = game.get("away_team")
            if home not in team_stats:
                team_stats[home] = self.data_fetcher.get_team_stats(home)
            if away not in team_stats:
                team_stats[away] = self.data_fetcher.get_team_stats(away)
        
        # Analyze each game
        opportunities = []
        for game in games:
            home = game.get("home_team")
            away = game.get("away_team")
            
            # Get predictions
            prediction = self.model.predict(home, away, team_stats.get(home), team_stats.get(away))
            
            # Get odds (would need real odds API)
            # For now, use simulated odds
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
        # This would connect to an odds API in production
        # For demo, return simulated odds
        import random
        return {
            "home_ml": round(1.7 + random.random() * 0.6, 2),
            "away_ml": round(1.7 + random.random() * 0.6, 2),
            "over": 1.90,
            "under": 1.90
        }


def main():
    parser = argparse.ArgumentParser(description="BetBrain - Sports Betting Analysis")
    parser.add_argument("--sport", default="nhl", choices=["nhl", "nba", "soccer", "tennis"])
    parser.add_argument("--days", type=int, default=3, help="Days ahead to analyze")
    parser.add_argument("--backtest", action="store_true", help="Run backtest")
    parser.add_argument("--start", help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="Backtest end date (YYYY-MM-DD)")
    parser.add_argument("--strategy", default="value", help="Strategy to use")
    
    args = parser.parse_args()
    
    if args.backtest:
        # Run backtest
        results = run_backtest(
            sport=args.sport,
            start_date=args.start or "2024-01-01",
            end_date=args.end or "2024-12-31",
            strategy=args.strategy
        )
        print(f"\n📊 Backtest Results:")
        print(f"   Total Return: {results['total_return']*100:.2f}%")
        print(f"   Sharpe Ratio: {results.get('sharpe', 'N/A')}")
        print(f"   Max Drawdown: {results.get('max_drawdown', 'N/A')}")
        print(f"   Total Bets: {results.get('total_bets', 0)}")
    else:
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
        else:
            print("\n❌ No value bets found today.")


if __name__ == "__main__":
    main()
