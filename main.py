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
from research_agent.agent import ResearchAgent
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
        self.researcher = ResearchAgent()  # For web research
    
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
            start_time = game.get("start_time", "")
            
            if not home or not away:
                continue
            
            home_stats = self.data_fetcher.get_team_stats(home)
            away_stats = self.data_fetcher.get_team_stats(away)
            
            print(f"Analyzing: {away} @ {home}")
            
            # Use advanced tier-based analysis
            ml_analysis = self.strategy.analyze_ml(home, away, home_stats, away_stats, injuries)
            ou_analysis = self.strategy.analyze_over_under(home, away, home_stats, away_stats, injuries)
            
            # Get odds
            odds = self._get_odds(home, away, home_stats, away_stats)
            
            # Devig implied probabilities before computing edge
            raw_home = 1.0 / odds["home_ml"]
            raw_away = 1.0 / odds["away_ml"]
            ml_total = raw_home + raw_away
            true_implied_home = raw_home / ml_total
            true_implied_away = raw_away / ml_total

            raw_over = 1.0 / odds["over"]
            raw_under = 1.0 / odds["under"]
            ou_total = raw_over + raw_under
            true_implied_over = raw_over / ou_total

            # Calculate edges against devigged implied probabilities
            home_edge, home_ev = self.odds_processor.calculate_edge(ml_analysis["home_prob"], true_implied_home, odds["home_ml"])
            away_edge, away_ev = self.odds_processor.calculate_edge(ml_analysis["away_prob"], true_implied_away, odds["away_ml"])
            over_edge, over_ev = self.odds_processor.calculate_edge(ou_analysis["over_prob"], true_implied_over, odds["over"])

            home_rec = "BET" if home_edge > 0.03 else "SKIP"
            away_rec = "BET" if away_edge > 0.03 else "SKIP"
            over_rec = "BET" if over_edge > 0.03 else "SKIP"

            pred_total = ou_analysis.get("predicted_total", 5.5)
            score_pred = ou_analysis.get("score_pred", f"{ou_analysis.get('home_goals', 2.8)} - {ou_analysis.get('away_goals', 2.8)}")

            # Shared fields across all three rows for this game
            base = {
                "match": f"{home} vs {away}",
                "start_time": start_time,
                "score_pred": score_pred,
                "pred_total": pred_total,
                "ou_line": ou_analysis["line"],
                "over_prob": round(ou_analysis["over_prob"] * 100, 1),
                "under_prob": round(ou_analysis.get("under_prob", 1 - ou_analysis["over_prob"]) * 100, 1),
            }

            opportunities.extend([
                {
                    **base,
                    "market": "ML (Home)",
                    "win_pick": home,
                    "odds": odds["home_ml"],
                    "model_prob": ml_analysis["home_prob"],
                    "implied_prob": true_implied_home,
                    "edge": home_edge,
                    "ev": home_ev,
                    "recommendation": home_rec,
                    "confidence": ml_analysis["confidence"],
                    "reasoning": ml_analysis["reasoning"],
                },
                {
                    **base,
                    "market": "ML (Away)",
                    "win_pick": away,
                    "odds": odds["away_ml"],
                    "model_prob": ml_analysis["away_prob"],
                    "implied_prob": true_implied_away,
                    "edge": away_edge,
                    "ev": away_ev,
                    "recommendation": away_rec,
                    "confidence": ml_analysis["confidence"],
                    "reasoning": ml_analysis["reasoning"],
                },
                {
                    **base,
                    "market": f"O/U {ou_analysis['line']}",
                    "win_pick": "UNDER" if ou_analysis.get("under_prob", 0.5) > ou_analysis["over_prob"] else "OVER",
                    "odds": odds["over"],
                    "model_prob": ou_analysis["over_prob"],
                    "implied_prob": true_implied_over,
                    "edge": over_edge,
                    "ev": over_ev,
                    "recommendation": over_rec,
                    "confidence": ou_analysis["confidence"],
                    "reasoning": ou_analysis["reasoning"],
                }
            ])
        
        return opportunities
    
    def _get_odds(self, home: str, away: str, home_stats: dict, away_stats: dict) -> dict:
        """Get odds: real API if available, otherwise strength-based fallback."""
        from odds.odds_api import OddsAPIFetcher
        fetcher = OddsAPIFetcher()
        if fetcher.has_api():
            try:
                result = fetcher.get_best_game_odds(home, away)
                if result.get("source") == "theoddsapi":
                    return result
            except Exception:
                pass
        home_strength = home_stats.get("win_rate", 0.5)
        away_strength = away_stats.get("win_rate", 0.5)
        return fetcher.get_fallback_odds(home_strength, away_strength)
    
    def _get_injuries(self) -> dict:
        """Get injury data using research agent."""
        return self.researcher.get_team_news("NHL")


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(description="Run BetBrain analysis")
    parser.add_argument("--days", type=int, default=3, help="Days ahead to analyze")
    parser.add_argument("--strategy", type=str, default="tier_based", choices=["value", "conservative", "aggressive", "tier_based", "model_plus"], help="Strategy for backtesting")
    parser.add_argument("--min-edge", type=float, default=0.03, help="Min edge threshold for bet recommendation")

    return parser.parse_args()


def main():
    args = parse_args()
    bot = BetBrain()
    opportunities = bot.analyze(days=args.days)
    bets = [o for o in opportunities if o["recommendation"] == "BET" and o["edge"] >= args.min_edge]

    print(f"\n🏆 BetBrain - NHL Analysis")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 50)

    if bets:
        print(f"\n✅ Found {len(bets)} value bets!\n")
        for i, bet in enumerate(bets, 1):
            print(f"{i}. {bet['match']} {bet['market']}")
            print(f"   Odds: {bet['odds']} | Edge: {bet['edge']*100:+.1f}% | EV: {bet['ev']*100:+.1f}%")
            print(f"   {bet.get('reasoning', '')}")
    else:
        print("\n❌ No value bets found.")


if __name__ == "__main__":
    main()
