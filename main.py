"""
Sports Betting Analysis System - Main Entry Point

Usage:
    python main.py --sport nhl --date today
    python main.py --sport nba --report
    python main.py --sport soccer --model poisson
"""

import argparse
import sys
from datetime import datetime, timedelta
from typing import List, Dict

# Add project root to path
sys.path.insert(0, __file__.rsplit("/", 1)[0])

import config
from data.nhl import NHLDataFetcher
from features.engineer import create_features
from models.predictor import get_model, LogisticModel, PoissonModel
from odds.scanner import OddsProcessor, StrategyManager


class BettingAnalyzer:
    """Main analysis engine."""
    
    def __init__(self, sport: str = "nhl"):
        self.sport = sport
        self.model = get_model("logistic")
        self.odds_processor = OddsProcessor(
            min_edge=config.STRATEGIES["value"]["min_edge"],
            min_ev=config.STRATEGIES["value"]["min_ev"]
        )
        self.strategy_manager = StrategyManager(
            bankroll=config.BANKROLL["initial"],
            kelly_fraction=config.BANKROLL["kelly_fraction"]
        )
        
        # Initialize data fetcher
        if sport == "nhl":
            self.data_fetcher = NHLDataFetcher()
        else:
            self.data_fetcher = None
    
    def get_upcoming_games(self, days: int = 3) -> List[Dict]:
        """Get upcoming games."""
        
        if self.sport == "nhl":
            return self.data_fetcher.get_schedule(days)
        
        # Placeholder for other sports
        return []
    
    def analyze_games(self, games: List[Dict]) -> List:
        """Analyze all games."""
        
        opportunities = []
        
        for game in games:
            home = game.get("home_team", "")
            away = game.get("away_team", "")
            
            # Create mock data for demonstration
            # In production, would fetch real stats
            team_stats = {
                home: {
                    "goals_for_avg": 2.8,
                    "goals_against_avg": 2.9,
                    "win_rate": 0.52,
                    "home_win_rate": 0.58,
                    "form": 0.6,
                    "rest": 2,
                    "games_14d": 4,
                    "injuries": 1,
                },
                away: {
                    "goals_for_avg": 2.6,
                    "goals_against_avg": 3.0,
                    "win_rate": 0.48,
                    "away_win_rate": 0.42,
                    "form": 0.4,
                    "rest": 1,
                    "games_14d": 5,
                    "injuries": 2,
                }
            }
            
            # Create features
            features = create_features(self.sport, [game], team_stats)
            
            # Generate prediction
            predictions = self.model.predict_from_features(features)
            
            if predictions:
                pred = predictions[0]
                
                # Simulated odds (in production, fetch from API)
                odds_home = 1.85
                odds_away = 2.10
                odds_over = 1.90
                odds_under = 1.90
                
                # Analyze for opportunities
                opps = self.odds_processor.analyze_match(
                    home, away, pred,
                    odds_home=odds_home,
                    odds_away=odds_away,
                    odds_over=odds_over,
                    odds_under=odds_under
                )
                
                opportunities.extend(opps)
        
        return opportunities
    
    def generate_report(self, opportunities: List) -> str:
        """Generate analysis report."""
        
        bets = [o for o in opportunities if o.recommendation == "BET"]
        
        report = []
        report.append("=" * 70)
        report.append(f"🏆 SPORTS BETTING ANALYSIS - {self.sport.upper()}")
        report.append(f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        report.append("=" * 70)
        
        if not bets:
            report.append("\n❌ No value bets found today.")
            report.append("\nAll opportunities:")
        else:
            report.append(f"\n✅ Found {len(bets)} value bet(s)!")
        
        # Table header
        report.append("\n" + "-" * 70)
        report.append(f"{'Match':<25} {'Market':<10} {'Odds':<6} {'Model%':<8} {'Edge':<8} {'EV':<8} {'Conf':<6}")
        report.append("-" * 70)
        
        for opp in opportunities:
            edge_str = f"{opp.edge*100:+.1f}%" if opp.edge else "N/A"
            ev_str = f"{opp.ev*100:+.1f}%" if opp.ev else "N/A"
            model_str = f"{opp.model_prob*100:.1f}%"
            
            symbol = "✅" if opp.recommendation == "BET" else "❌"
            
            report.append(f"{symbol} {opp.match:<23} {opp.market:<10} {opp.odds:<6.2f} {model_str:<8} {edge_str:<8} {ev_str:<8} {opp.confidence:<6}")
        
        report.append("-" * 70)
        
        # Top picks
        value_picks, safety_picks = self.strategy_manager.get_top_picks(opportunities, 3)
        
        if value_picks:
            report.append("\n🎯 TOP VALUE BETS:")
            for i, pick in enumerate(value_picks, 1):
                report.append(f"   {i}. {pick.match} {pick.market} @ {pick.odds} ({pick.edge*100:+.1f}% edge)")
        
        if safety_picks:
            report.append("\n🛡️ SAFEST PICKS (highest confidence):")
            for i, pick in enumerate(safety_picks, 1):
                report.append(f"   {i}. {pick.match} {pick.market} @ {pick.odds} ({pick.confidence})")
        
        # Reasoning for top pick
        if value_picks:
            top = value_picks[0]
            report.append(f"\n💡 Top Pick Analysis:")
            report.append(f"   {top.reasoning}")
        
        report.append("\n" + "=" * 70)
        report.append("⚠️  DISCLAIMER: This is analysis only. No bets placed automatically.")
        report.append("   Always gamble responsibly. Past performance doesn't guarantee future results.")
        report.append("=" * 70)
        
        return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description="Sports Betting Analysis System")
    parser.add_argument("--sport", default="nhl", choices=["nhl", "nba", "soccer", "tennis"],
                      help="Sport to analyze")
    parser.add_argument("--date", default="today", help="Date (YYYY-MM-DD or 'today')")
    parser.add_argument("--model", default="logistic", choices=["logistic", "poisson", "xgboost"],
                      help="Prediction model")
    parser.add_argument("--days", type=int, default=3, help="Days ahead to analyze")
    parser.add_argument("--report", action="store_true", help="Generate full report")
    
    args = parser.parse_args()
    
    print(f"\n🏒 Initializing {args.sport.upper()} analysis...")
    
    # Create analyzer
    analyzer = BettingAnalyzer(sport=args.sport)
    
    # Get games
    print(f"📊 Fetching upcoming games...")
    games = analyzer.get_upcoming_games(args.days)
    
    if not games:
        print("❌ No games found.")
        return
    
    print(f"   Found {len(games)} games")
    
    # Analyze
    print("🔍 Analyzing matchups...")
    opportunities = analyzer.analyze_games(games)
    
    # Generate report
    report = analyzer.generate_report(opportunities)
    print("\n" + report)


if __name__ == "__main__":
    main()
