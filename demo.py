"""
Demo mode for testing the betting analysis system
"""

import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])

from datetime import datetime
from models.predictor import get_model, LogisticModel, PoissonModel
from odds.scanner import OddsProcessor, StrategyManager
import config


def run_demo():
    """Run demo with mock data."""
    
    print("=" * 70)
    print("🏆 SPORTS BETTING ANALYSIS - DEMO MODE")
    print(f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    
    # Initialize
    model = LogisticModel()
    odds_proc = OddsProcessor(min_edge=0.03, min_ev=0.05)
    strategy_mgr = StrategyManager()
    
    # Mock games (simulating NHL)
    games = [
        {
            "home": "MTL",
            "away": "TOR",
            "home_stats": {"goals_for": 2.8, "goals_against": 2.9, "win_rate": 0.45, "home_win": 0.52, "form": 0.4, "rest": 2},
            "away_stats": {"goals_for": 3.2, "goals_against": 2.6, "win_rate": 0.62, "away_win": 0.55, "form": 0.7, "rest": 1}
        },
        {
            "home": "EDM",
            "away": "CGY",
            "home_stats": {"goals_for": 3.4, "goals_against": 2.8, "win_rate": 0.58, "home_win": 0.65, "form": 0.8, "rest": 3},
            "away_stats": {"goals_for": 2.5, "goals_against": 3.0, "win_rate": 0.40, "away_win": 0.38, "form": 0.3, "rest": 1}
        },
        {
            "home": "BOS",
            "away": "NYR",
            "home_stats": {"goals_for": 3.0, "goals_against": 2.5, "win_rate": 0.55, "home_win": 0.60, "form": 0.6, "rest": 2},
            "away_stats": {"goals_for": 2.9, "goals_against": 2.7, "win_rate": 0.52, "away_win": 0.48, "form": 0.5, "rest": 2}
        },
        {
            "home": "FLA",
            "away": "TBL",
            "home_stats": {"goals_for": 3.3, "goals_against": 2.6, "win_rate": 0.60, "home_win": 0.65, "form": 0.75, "rest": 2},
            "away_stats": {"goals_for": 2.8, "goals_against": 2.9, "win_rate": 0.48, "away_win": 0.45, "form": 0.45, "rest": 1}
        },
    ]
    
    opportunities = []
    
    for game in games:
        # Simplified prediction
        home = game["home_stats"]
        away = game["away_stats"]
        
        # Calculate simple strength
        home_strength = (home["win_rate"] * 0.4 + home["home_win"] * 0.3 + 
                        home["form"] * 0.2 + home["rest"] / 5 * 0.1)
        away_strength = (away["win_rate"] * 0.4 + away["away_win"] * 0.3 + 
                        away["form"] * 0.2 + away["rest"] / 5 * 0.1)
        
        import numpy as np
        prob_diff = home_strength - away_strength
        home_win_prob = 1 / (1 + np.exp(-4 * prob_diff))
        
        expected_goals = (home["goals_for"] + away["goals_for"]) / 2
        over_prob = 1 / (1 + np.exp(-2 * (expected_goals - 3.5)))
        
        # Simulated odds (would come from bookmakers)
        odds_home = 1.85 if home_win_prob > 0.5 else 2.20
        odds_away = 2.10 if home_win_prob <= 0.5 else 1.75
        odds_over = 1.90
        odds_under = 1.90
        
        # Analyze
        from odds.scanner import BettingOpportunity
        
        edge_home, ev_home = odds_proc.calculate_edge(home_win_prob, odds_home)
        edge_away, ev_away = odds_proc.calculate_edge(1 - home_win_prob, odds_away)
        edge_over, ev_over = odds_proc.calculate_edge(over_prob, odds_over)
        
        # Confidence
        if abs(home_win_prob - 0.5) > 0.25:
            conf = "high"
        elif abs(home_win_prob - 0.5) > 0.15:
            conf = "medium"
        else:
            conf = "low"
        
        # Create opportunities
        rec_home = "BET" if edge_home > 0.03 and ev_home > 0.05 else "SKIP"
        rec_away = "BET" if edge_away > 0.03 and ev_away > 0.05 else "SKIP"
        
        opportunities.append(BettingOpportunity(
            match=f"{game['home']} vs {game['away']}",
            market="ML (Home)",
            odds=odds_home,
            model_prob=home_win_prob,
            implied_prob=1/odds_home,
            edge=edge_home,
            ev=ev_home,
            recommendation=rec_home,
            confidence=conf,
            reasoning=f"Home team has {home['win_rate']*100:.0f}% win rate, {home['form']*100:.0f}% form"
        ))
        
        opportunities.append(BettingOpportunity(
            match=f"{game['home']} vs {game['away']}",
            market="ML (Away)",
            odds=odds_away,
            model_prob=1-home_win_prob,
            implied_prob=1/odds_away,
            edge=edge_away,
            ev=ev_away,
            recommendation=rec_away,
            confidence=conf,
            reasoning=f"Away team has {away['win_rate']*100:.0f}% win rate, {away['form']*100:.0f}% form"
        ))
        
        opportunities.append(BettingOpportunity(
            match=f"{game['home']} vs {game['away']}",
            market="Over 5.5",
            odds=odds_over,
            model_prob=over_prob,
            implied_prob=1/odds_over,
            edge=edge_over,
            ev=ev_over,
            recommendation="BET" if edge_over > 0.03 else "SKIP",
            confidence=conf,
            reasoning=f"Expected {expected_goals:.1f} goals"
        ))
    
    # Generate report
    print("\n" + "-" * 70)
    print(f"{'Match':<22} {'Market':<10} {'Odds':<6} {'Model%':<8} {'Edge':<8} {'EV':<8} {'Conf':<6}")
    print("-" * 70)
    
    for opp in opportunities:
        edge_str = f"{opp.edge*100:+.1f}%"
        ev_str = f"{opp.ev*100:+.1f}%"
        model_str = f"{opp.model_prob*100:.1f}%"
        
        symbol = "✅" if opp.recommendation == "BET" else "❌"
        print(f"{symbol} {opp.match:<20} {opp.market:<10} {opp.odds:<6.2f} {model_str:<8} {edge_str:<8} {ev_str:<8} {opp.confidence:<6}")
    
    # Top picks
    bets = [o for o in opportunities if o.recommendation == "BET"]
    
    print("\n" + "=" * 70)
    print(f"✅ FOUND {len(bets)} VALUE BETS")
    print("=" * 70)
    
    if bets:
        # Sort by edge
        bets_sorted = sorted(bets, key=lambda x: x.edge, reverse=True)
        
        print("\n🎯 TOP VALUE BETS:")
        for i, pick in enumerate(bets_sorted[:3], 1):
            print(f"   {i}. {pick.match} {pick.market} @ {pick.odds}")
            print(f"      Edge: {pick.edge*100:+.1f}% | EV: {pick.ev*100:+.1f}%")
            print(f"      {pick.reasoning}")
        
        # Safety picks
        conf_order = {"high": 3, "medium": 2, "low": 1}
        safety_sorted = sorted(bets, key=lambda x: (conf_order.get(x.confidence, 0), x.model_prob), reverse=True)
        
        print("\n🛡️ SAFEST PICKS (highest confidence):")
        for i, pick in enumerate(safety_sorted[:3], 1):
            print(f"   {i}. {pick.match} {pick.market} @ {pick.odds} ({pick.confidence})")
    
    print("\n" + "=" * 70)
    print("⚠️  DISCLAIMER: Demo output only. No real bets.")
    print("   System would need real odds API for actual analysis.")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()
