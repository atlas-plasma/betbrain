"""
Paper Trading module for BetBrain
Simulates betting without real money
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


class PaperTrader:
    """Simulate betting without real money."""
    
    def __init__(self, initial_bankroll: float = 1000):
        self.bankroll = initial_bankroll
        self.initial_bankroll = initial_bankroll
        self.bets = []
        self.record_file = Path(__file__).parent / "paper_trade_history.json"
        self._load_history()
    
    def _load_history(self):
        """Load previous paper trades."""
        if self.record_file.exists():
            with open(self.record_file) as f:
                data = json.load(f)
                self.bankroll = data.get("bankroll", self.initial_bankroll)
                self.bets = data.get("bets", [])
    
    def _save_history(self):
        """Save paper trade history."""
        with open(self.record_file, "w") as f:
            json.dump({
                "bankroll": self.bankroll,
                "bets": self.bets,
                "updated": datetime.now().isoformat()
            }, f, indent=2)
    
    def place_bet(self, match: str, market: str, odds: float, stake: float, 
                  prediction: float, reasoning: str = "") -> Dict:
        """Place a paper bet."""
        
        if stake > self.bankroll:
            return {"error": "Insufficient bankroll"}
        
        # Deduct stake
        self.bankroll -= stake
        
        bet = {
            "id": len(self.bets) + 1,
            "timestamp": datetime.now().isoformat(),
            "match": match,
            "market": market,
            "odds": odds,
            "stake": stake,
            "prediction": prediction,
            "reasoning": reasoning,
            "status": "pending",  # pending, won, lost
            "profit": 0
        }
        
        self.bets.append(bet)
        self._save_history()
        
        return bet
    
    def settle_bet(self, bet_id: int, won: bool):
        """Settle a bet after game result."""
        
        for bet in self.bets:
            if bet["id"] == bet_id and bet["status"] == "pending":
                if won:
                    # Win: get stake * odds
                    profit = bet["stake"] * (bet["odds"] - 1)
                    self.bankroll += bet["stake"] + profit
                    bet["profit"] = profit
                else:
                    # Loss: lose stake
                    bet["profit"] = -bet["stake"]
                
                bet["status"] = "won" if won else "lost"
                self._save_history()
                return bet
        
        return {"error": "Bet not found"}
    
    def get_status(self) -> Dict:
        """Get current paper trading status."""
        
        settled = [b for b in self.bets if b["status"] != "pending"]
        won = sum(1 for b in settled if b["status"] == "won")
        lost = sum(1 for b in settled if b["status"] == "lost")
        
        total_profit = sum(b.get("profit", 0) for b in self.bets)
        
        return {
            "bankroll": self.bankroll,
            "initial_bankroll": self.initial_bankroll,
            "total_profit": total_profit,
            "profit_pct": (total_profit / self.initial_bankroll) * 100,
            "total_bets": len(self.bets),
            "pending_bets": sum(1 for b in self.bets if b["status"] == "pending"),
            "won": won,
            "lost": lost,
            "win_rate": won / len(settled) if settled else 0
        }
    
    def get_pending_bets(self) -> List[Dict]:
        """Get all pending bets."""
        return [b for b in self.bets if b["status"] == "pending"]
    
    def get_history(self, limit: int = 20) -> List[Dict]:
        """Get bet history."""
        return sorted(self.bets, key=lambda x: x["timestamp"], reverse=True)[:limit]
    
    def reset(self):
        """Reset paper trading."""
        self.bankroll = self.initial_bankroll
        self.bets = []
        self._save_history()


def get_paper_trader():
    """Get singleton paper trader."""
    return PaperTrader()


if __name__ == "__main__":
    # Demo
    trader = PaperTrader()
    
    # Place some demo bets
    trader.place_bet(
        "EDM vs CGY", "ML (Home)", 1.85, 50, 0.65,
        "Edmonton strong home record, Calgary struggling away"
    )
    
    trader.place_bet(
        "MTL vs TOR", "ML (Away)", 2.10, 30, 0.55,
        "Toronto hot streak, Montreal injured key players"
    )
    
    print("Paper Trading Status:")
    print(json.dumps(trader.get_status(), indent=2))
    
    print("\nPending Bets:")
    for bet in trader.get_pending_bets():
        print(f"  {bet['match']} {bet['market']} @ {bet['odds']}")
