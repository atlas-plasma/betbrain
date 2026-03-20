"""
BetBrain - Sports Betting Analysis System
Main entry point for the betting bot
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

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
            
            # Generate reasoning based on stats
            reasoning = self._generate_reasoning(home, away, home_stats, away_stats)
            
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
            
            # Update reasoning for each opportunity
            for opp in opps:
                opp.reasoning = reasoning
            
            opportunities.extend(opps)
        
        return opportunities
    
    def _generate_reasoning(self, home: str, away: str, home_stats: Dict, away_stats: Dict) -> str:
        """Generate detailed reasoning for the bet."""
        
        reasons = []
        
        # Win rate comparison
        home_wr = home_stats.get("win_rate", 0.5) * 100
        away_wr = away_stats.get("win_rate", 0.5) * 100
        
        if home_wr > away_wr + 5:
            reasons.append(f"{home} has better win rate ({home_wr:.0f}% vs {away_wr:.0f}%)")
        elif away_wr > home_wr + 5:
            reasons.append(f"{away} has better win rate ({away_wr:.0f}% vs {home_wr:.0f}%)")
        
        # Home/Away advantage
        home_home = home_stats.get("home_win_rate", 0.5) * 100
        away_away = away_stats.get("away_win_rate", 0.5) * 100
        
        if home_home > 55:
            reasons.append(f"{home} strong at home ({home_home:.0f}%)")
        if away_away > 50:
            reasons.append(f"{away} solid on road ({away_away:.0f}%)")
        
        # Form
        home_form = home_stats.get("form", 0.5) * 100
        away_form = away_stats.get("form", 0.5) * 100
        
        if home_form > 60:
            reasons.append(f"{home} in great form ({home_form:.0f}%)")
        elif home_form < 40:
            reasons.append(f"{home} struggling ({home_form:.0f}%)")
        
        if away_form > 60:
            reasons.append(f"{away} in great form ({away_form:.0f}%)")
        elif away_form < 40:
            reasons.append(f"{away} struggling ({away_form:.0f}%)")
        
        # Rest days
        home_rest = home_stats.get("rest", 2)
        away_rest = away_stats.get("rest", 2)
        
        if home_rest >= 3:
            reasons.append(f"{home} well rested ({home_rest} days)")
        elif home_rest == 1:
            reasons.append(f"{home} playing on 1 day rest (fatigue risk)")
        
        # Injuries
        home_inj = home_stats.get("injuries", 0)
        away_inj = away_stats.get("injuries", 0)
        
        if home_inj >= 2:
            reasons.append(f"{home} has {home_inj} injuries")
        if away_inj >= 2:
            reasons.append(f"{away} has {away_inj} injuries")
        
        # Goals analysis
        home_gf = home_stats.get("goals_for_avg", 2.5)
        away_gf = away_stats.get("goals_for_avg", 2.5)
        
        if home_gf > 3.0:
            reasons.append(f"High scoring {home} ({home_gf:.1f} goals/game)")
        if away_gf > 3.0:
            reasons.append(f"High scoring {away} ({away_gf:.1f} goals/game)")
        
        if not reasons:
            return "No strong factors identified"
        
        return " | ".join(reasons[:3])  # Limit to top 3
    
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
