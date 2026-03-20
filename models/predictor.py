"""
Prediction Models for Sports Betting
"""

import math
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import pandas as pd


@dataclass
class Prediction:
    """Prediction result."""
    home_win_prob: float
    draw_prob: float  # 0 for NHL/NBA
    away_win_prob: float
    over_prob: float  # Over/Under
    under_prob: float
    expected_home_goals: float
    expected_away_goals: float
    confidence: str  # high, medium, low


class PoissonModel:
    """Poisson model for goal scoring (soccer, hockey)."""
    
    def __init__(self, home_advantage: float = 0.1):
        self.home_advantage = home_advantage
    
    def predict(self, home_goals_avg: float, away_goals_avg: float) -> Prediction:
        """Generate Poisson-based predictions."""
        
        # Apply home advantage
        lambda_home = home_goals_avg * (1 + self.home_advantage)
        lambda_away = away_goals_avg
        
        # Calculate goal probabilities using Poisson
        max_goals = 10
        
        home_probs = self._poisson_probs(lambda_home, max_goals)
        away_probs = self._poisson_probs(lambda_away, max_goals)
        
        # Win/Draw/Loss
        home_win = sum(home_probs[i] * sum(away_probs[:i]) for i in range(1, max_goals))
        away_win = sum(away_probs[i] * sum(home_probs[:i]) for i in range(1, max_goals))
        draw = sum(home_probs[i] * away_probs[i] for i in range(max_goals))
        
        # Normalize
        total = home_win + away_win + draw
        home_win /= total
        away_win /= total
        draw /= total
        
        # Over/Under (default line 5.5 for NHL)
        over_prob = sum(home_probs[i] * away_probs[j] for i in range(max_goals) 
                       for j in range(max_goals) if i + j > 5.5)
        under_prob = 1 - over_prob
        
        # Confidence based on spread
        confidence = self._calculate_confidence(home_win, away_win)
        
        return Prediction(
            home_win_prob=home_win,
            draw_prob=draw,
            away_win_prob=away_win,
            over_prob=over_prob,
            under_prob=under_prob,
            expected_home_goals=lambda_home,
            expected_away_goals=lambda_away,
            confidence=confidence
        )
    
    def _poisson_probs(self, lambda_: float, max_goals: int) -> np.ndarray:
        """Calculate Poisson probability mass function up to max_goals.

        Do NOT normalize: the raw PMF values are needed for accurate win/draw
        and over/under probability calculations.  For typical NHL lambdas (~3),
        P(goals >= 10) < 0.001 so truncation error is negligible.
        """
        probs = np.zeros(max_goals)
        for i in range(max_goals):
            probs[i] = (lambda_ ** i * np.exp(-lambda_)) / math.factorial(i)
        return probs
    
    def _calculate_confidence(self, home_win: float, away_win: float) -> str:
        """Determine confidence level."""
        spread = abs(home_win - away_win)
        if spread > 0.25:
            return "high"
        elif spread > 0.15:
            return "medium"
        return "low"


class LogisticModel:
    """Logistic regression for win probabilities."""
    
    def __init__(self):
        # Would load trained model in production
        self.weights = {}
    
    def predict(self, home_team: str, away_team: str, home_stats: Dict, away_stats: Dict) -> Prediction:
        """Predict from team stats."""
        
        # Calculate team strength
        home_strength = (
            home_stats.get("win_rate", 0.5) * 0.4 +
            home_stats.get("home_win_rate", 0.5) * 0.2 +
            home_stats.get("form", 0.5) * 0.2 +
            home_stats.get("rest", 2) / 5 * 0.1 +
            (1 - home_stats.get("injuries", 0) / 5) * 0.1
        )
        
        away_strength = (
            away_stats.get("win_rate", 0.5) * 0.4 +
            away_stats.get("away_win_rate", 0.5) * 0.2 +
            away_stats.get("form", 0.5) * 0.2 +
            away_stats.get("rest", 2) / 5 * 0.1 +
            (1 - away_stats.get("injuries", 0) / 5) * 0.1
        )
        
        # Convert to probability
        diff = home_strength - away_strength
        home_win = 1 / (1 + np.exp(-4 * diff))
        
        # Expected goals
        home_goals = home_stats.get("goals_for_avg", 2.5)
        away_goals = away_stats.get("goals_for_avg", 2.5)
        
        # Over/Under
        expected_total = (home_goals + away_goals) / 2
        over_prob = 1 / (1 + np.exp(-2 * (expected_total - 3.5)))
        
        # Confidence
        if abs(home_win - 0.5) > 0.25:
            confidence = "high"
        elif abs(home_win - 0.5) > 0.15:
            confidence = "medium"
        else:
            confidence = "low"
        
        return Prediction(
            home_win_prob=home_win,
            draw_prob=0.0,
            away_win_prob=1 - home_win,
            over_prob=over_prob,
            under_prob=1 - over_prob,
            expected_home_goals=home_goals,
            expected_away_goals=away_goals,
            confidence=confidence
        )
    
    def predict_from_features(self, features: pd.DataFrame) -> List[Prediction]:
        """Predict from feature dataframe."""
        predictions = []
        
        for _, row in features.iterrows():
            # Simplified logistic calculation
            home_strength = (
                row.get("home_win_rate", 0.5) * 0.4 +
                row.get("home_home_win_rate", 0.5) * 0.2 +
                row.get("home_form", 0) * 0.2 +
                row.get("home_rest_days", 2) * 0.05 +
                (1 - row.get("home_key_players_out", 0) / 5) * 0.15
            )
            
            away_strength = (
                row.get("away_win_rate", 0.5) * 0.4 +
                row.get("away_away_win_rate", 0.5) * 0.2 +
                row.get("away_form", 0) * 0.2 +
                row.get("away_rest_days", 2) * 0.05 +
                (1 - row.get("away_key_players_out", 0) / 5) * 0.15
            )
            
            # Convert to probabilities
            diff = home_strength - away_strength
            home_win = 1 / (1 + np.exp(-4 * diff))  # Sigmoid
            
            # Estimate over/under
            expected = (row.get("home_goals_avg", 2.5) + row.get("away_goals_avg", 2.5)) / 2
            over_prob = 1 / (1 + np.exp(-2 * (expected - 3)))
            
            predictions.append(Prediction(
                home_win_prob=home_win,
                draw_prob=0.0,  # Not applicable
                away_win_prob=1 - home_win,
                over_prob=over_prob,
                under_prob=1 - over_prob,
                expected_home_goals=row.get("home_goals_avg", 2.5),
                expected_away_goals=row.get("away_goals_avg", 2.5),
                confidence="medium"
            ))
        
        return predictions


class EloModel:
    """Simple Elo rating system."""
    
    def __init__(self, k_factor: int = 32, home_advantage: int = 100):
        self.k_factor = k_factor
        self.home_advantage = home_advantage
        self.ratings = {}
    
    def get_rating(self, team: str) -> float:
        """Get team rating."""
        return self.ratings.get(team, 1500)
    
    def predict(self, home_team: str, away_team: str) -> Tuple[float, float]:
        """Predict win probabilities from Elo."""
        home_elo = self.get_rating(home_team) + self.home_advantage
        away_elo = self.get_rating(away_team)
        
        # Elo expected score
        diff = home_elo - away_elo
        home_win_prob = 1 / (1 + 10 ** (-diff / 400))
        
        return home_win_prob, 1 - home_win_prob
    
    def update_ratings(self, winner: str, loser: str, is_draw: bool = False):
        """Update ratings after a game."""
        winner_elo = self.get_rating(winner)
        loser_elo = self.get_rating(loser)
        
        if is_draw:
            winner_expected = 0.5
            loser_expected = 0.5
        else:
            winner_expected = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
            loser_expected = 1 - winner_expected
        
        # Update
        self.ratings[winner] = winner_elo + self.k_factor * (1 - winner_expected)
        self.ratings[loser] = loser_elo + self.k_factor * (0 - loser_expected)


def get_model(model_type: str):
    """Factory function to get prediction model."""
    models = {
        "poisson": PoissonModel,
        "logistic": LogisticModel,
        "elo": EloModel,
    }
    return models.get(model_type, LogisticModel)()
