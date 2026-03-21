"""
Strategy selector — filters opportunities using the signals from the
advanced model (PDO, goalie quality, B2B, edge, Kelly).
"""

from typing import Dict


class StrategySelector:

    def __init__(self, strategy_name: str = "value"):
        self.strategy_name = strategy_name

    def should_bet(self, opportunity: Dict) -> bool:
        edge       = opportunity.get("edge", 0)
        model_prob = opportunity.get("model_prob", 0)
        confidence = opportunity.get("confidence", "low")
        kelly      = opportunity.get("kelly", 0)
        home_pdo   = opportunity.get("home_pdo", 100)
        away_pdo   = opportunity.get("away_pdo", 100)
        home_b2b   = opportunity.get("home_b2b", False)
        away_b2b   = opportunity.get("away_b2b", False)
        home_sv    = opportunity.get("home_goalie_sv", 90.8)
        away_sv    = opportunity.get("away_goalie_sv", 90.8)
        market     = opportunity.get("market", "")

        s = self.strategy_name

        if s == "value":
            # Basic value: positive edge with at least medium confidence
            return edge > 0.03 and confidence in ("medium", "high")

        elif s == "pdo_fade":
            # Only bet when one team has PDO > 102 (regression signal).
            # Fade the lucky team — back whoever is playing against them.
            # Also allow backing genuinely unlucky teams (PDO < 98).
            win_pick = opportunity.get("win_pick", "")
            home     = opportunity.get("home_team", "")
            away     = opportunity.get("away_team", "")
            if edge <= 0.02:
                return False
            opp_is_away = (win_pick == away)
            opp_is_home = (win_pick == home)
            # Fading lucky home team → backing away
            if home_pdo >= 102 and opp_is_away:
                return True
            # Fading lucky away team → backing home
            if away_pdo >= 102 and opp_is_home:
                return True
            # Backing unlucky team (PDO < 98)
            if home_pdo <= 98 and opp_is_home:
                return True
            if away_pdo <= 98 and opp_is_away:
                return True
            return False

        elif s == "b2b_exploit":
            # Only bet when there's a back-to-back disadvantage to exploit.
            # Road B2B is the strongest signal (~8% win-rate drop).
            if edge <= 0.02:
                return False
            win_pick = opportunity.get("win_pick", "")
            away     = opportunity.get("away_team", "")
            home     = opportunity.get("home_team", "")
            # Best signal: away team on B2B, bet on home
            if away_b2b and win_pick == home:
                return True
            # Home team on B2B, bet on away
            if home_b2b and win_pick == away:
                return True
            # Under when B2B team is playing (fatigue reduces scoring)
            if (home_b2b or away_b2b) and "Under" in market:
                return edge > 0.02
            return False

        elif s == "goalie_edge":
            # Only bet when goalie quality creates a meaningful advantage.
            # Elite goalie (sv% > 91.8%) vs average or weak opponent goalie.
            if edge <= 0.02:
                return False
            win_pick = opportunity.get("win_pick", "")
            home     = opportunity.get("home_team", "")
            away     = opportunity.get("away_team", "")
            # Elite home goalie vs weak away goalie
            if home_sv >= 91.5 and away_sv < 90.5 and win_pick == home:
                return True
            # Elite away goalie vs weak home goalie
            if away_sv >= 91.5 and home_sv < 90.5 and win_pick == away:
                return True
            # Strong under signal when both goalies are elite
            if home_sv >= 91.5 and away_sv >= 91.5 and "Under" in market:
                return edge > 0.02
            return False

        elif s == "kelly":
            # Kelly criterion: bet whenever Kelly stake > 1% of bankroll
            # and edge is positive. This is mathematically optimal sizing.
            return kelly >= 0.01 and edge > 0.01

        # fallback
        return edge > 0.03

    def describe(self) -> str:
        descriptions = {
            "value":       "Value Betting — edge >3%, medium+ confidence",
            "pdo_fade":    "PDO Regression — fade lucky teams (PDO>102), back unlucky (PDO<98)",
            "b2b_exploit": "Back-to-Back — exploit tired road B2B teams",
            "goalie_edge": "Goalie Edge — bet when elite goalie vs weak opponent",
            "kelly":       "Kelly Optimal — bet whenever Kelly stake ≥1%",
        }
        return descriptions.get(self.strategy_name, self.strategy_name)
