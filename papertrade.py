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
        """Place a paper bet.

        ``odds`` is recorded as the opening odds.  When settling, pass the
        closing odds so we can compute Closing Line Value (CLV).
        """

        if stake > self.bankroll:
            return {"error": "Insufficient bankroll"}

        self.bankroll -= stake

        bet = {
            "id": len(self.bets) + 1,
            "timestamp": datetime.now().isoformat(),
            "match": match,
            "market": market,
            "opening_odds": odds,   # odds at bet placement
            "odds": odds,
            "stake": stake,
            "prediction": prediction,
            "reasoning": reasoning,
            "status": "pending",    # pending, won, lost
            "profit": 0,
            "closing_odds": None,   # filled in at settlement
            "clv": None,            # closing line value (>1 = beat the close)
        }

        self.bets.append(bet)
        self._save_history()

        return bet

    def settle_bet(self, bet_id: int, won: bool, closing_odds: float = None):
        """Settle a bet after game result.

        Args:
            bet_id:       ID of the bet to settle.
            won:          Whether the bet won.
            closing_odds: Final market odds just before game start.  When
                          provided, CLV = opening_odds / closing_odds.  A value
                          >1 means we got better than closing price (positive CLV).
        """

        for bet in self.bets:
            if bet["id"] == bet_id and bet["status"] == "pending":
                if won:
                    profit = bet["stake"] * (bet["odds"] - 1)
                    self.bankroll += bet["stake"] + profit
                    bet["profit"] = profit
                else:
                    bet["profit"] = -bet["stake"]

                bet["status"] = "won" if won else "lost"

                if closing_odds and closing_odds > 1:
                    bet["closing_odds"] = closing_odds
                    bet["clv"] = round(bet["opening_odds"] / closing_odds, 4)

                self._save_history()
                return bet

        return {"error": "Bet not found"}
    
    def get_status(self) -> Dict:
        """Get current paper trading status including Closing Line Value (CLV).

        CLV > 1 on average means bets were placed at better-than-closing odds,
        which is the strongest leading indicator of long-term profitability.
        """

        settled = [b for b in self.bets if b["status"] != "pending"]
        won = sum(1 for b in settled if b["status"] == "won")
        lost = sum(1 for b in settled if b["status"] == "lost")

        total_profit = sum(b.get("profit", 0) for b in self.bets)

        clv_values = [b["clv"] for b in self.bets if b.get("clv") is not None]
        avg_clv = round(sum(clv_values) / len(clv_values), 4) if clv_values else None

        return {
            "bankroll": self.bankroll,
            "initial_bankroll": self.initial_bankroll,
            "total_profit": total_profit,
            "profit_pct": (total_profit / self.initial_bankroll) * 100,
            "total_bets": len(self.bets),
            "pending_bets": sum(1 for b in self.bets if b["status"] == "pending"),
            "won": won,
            "lost": lost,
            "win_rate": won / len(settled) if settled else 0,
            "avg_clv": avg_clv,
            "clv_sample_size": len(clv_values),
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
