"""
Feature Engineering for Sports Predictions
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class FeatureEngineer:
    """Create features for betting models."""
    
    def __init__(self, sport: str):
        self.sport = sport
    
    def create_features(self, games: List[Dict], team_stats: Dict) -> pd.DataFrame:
        """Create feature matrix from game data."""
        
        features = []
        
        for game in games:
            home = game.get("home_team")
            away = game.get("away_team")
            
            # Get team data
            home_stats = team_stats.get(home, {})
            away_stats = team_stats.get(away, {})
            
            feat = {
                # Basic info
                "home_team": home,
                "away_team": away,
                "date": game.get("date"),
                
                # Rolling averages (would come from historical data)
                "home_goals_avg": home_stats.get("goals_for_avg", 2.5),
                "away_goals_avg": away_stats.get("goals_for_avg", 2.5),
                "home_goals_conceded_avg": home_stats.get("goals_against_avg", 2.8),
                "away_goals_conceded_avg": away_stats.get("goals_against_avg", 2.8),
                
                # Win rates
                "home_win_rate": home_stats.get("win_rate", 0.5),
                "away_win_rate": away_stats.get("win_rate", 0.5),
                
                # Home/Away specific
                "home_home_win_rate": home_stats.get("home_win_rate", 0.55),
                "away_away_win_rate": away_stats.get("away_win_rate", 0.45),
                
                # Form (last 5 games)
                "home_form": home_stats.get("form", 0),
                "away_form": away_stats.get("form", 0),
                
                # Head to head (simplified)
                "h2h_home_wins": 0,
                "h2h_away_wins": 0,
                
                # Rest days
                "home_rest_days": game.get("home_rest", 2),
                "away_rest_days": game.get("away_rest", 2),
                
                # Fatigue indicator
                "home_games_last_14": home_stats.get("games_14d", 4),
                "away_games_last_14": away_stats.get("games_14d", 4),
                
                # Injuries (simplified)
                "home_key_players_out": home_stats.get("injuries", 0),
                "away_key_players_out": away_stats.get("injuries", 0),
            }
            
            # Derived features
            feat["goal_differential_home"] = feat["home_goals_avg"] - feat["away_goals_conceded_avg"]
            feat["goal_differential_away"] = feat["away_goals_avg"] - feat["home_goals_conceded_avg"]
            feat["combined_goals_expected"] = (feat["home_goals_avg"] + feat["away_goals_avg"]) / 2
            
            features.append(feat)
        
        return pd.DataFrame(features)
    
    def normalize_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize features for model input."""
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        numeric_cols = [c for c in numeric_cols if c not in ["date"]]
        
        # Simple min-max normalization
        for col in numeric_cols:
            min_val = df[col].min()
            max_val = df[col].max()
            if max_val > min_val:
                df[col] = (df[col] - min_val) / (max_val - min_val)
        
        return df
    
    def calculate_momentum(self, recent_results: List[str]) -> float:
        """Calculate momentum from recent results (W=2, L=-1, O=0)."""
        if not recent_results:
            return 0
        
        scores = {"W": 2, "L": -1, "O": 0, "OT": -0.5}
        return sum(scores.get(r, 0) for r in recent_results) / len(recent_results)


class NHLEngineer(FeatureEngineer):
    """NHL-specific feature engineering."""
    
    def __init__(self):
        super().__init__("nhl")
    
    def create_nhl_features(self, home_team: str, away_team: str, 
                          home_data: Dict, away_data: Dict) -> Dict:
        """Create NHL-specific features."""
        
        # Power play efficiency
        home_pp = home_data.get("powerplay_pct", 20) / 100
        away_pk = away_data.get("penalty_kill_pct", 80) / 100
        home_pp_advantage = home_pp * (1 - away_pk)
        
        away_pp = away_data.get("powerplay_pct", 20) / 100
        home_pk = home_data.get("penalty_kill_pct", 80) / 100
        away_pp_advantage = away_pp * (1 - home_pk)
        
        # Goalie stats
        home_save_pct = home_data.get("save_pct", 0.910)
        away_save_pct = away_data.get("save_pct", 0.910)
        
        # Shots per game
        home_spg = home_data.get("shots_per_game", 30)
        away_spg = away_data.get("shots_per_game", 30)
        
        return {
            "home_pp_advantage": home_pp_advantage,
            "away_pp_advantage": away_pp_advantage,
            "home_save_pct": home_save_pct,
            "away_save_pct": away_save_pct,
            "home_spg": home_spg,
            "away_spg": away_spg,
            "expected_home_goals": home_spg * home_save_pct,
            "expected_away_goals": away_spg * away_save_pct,
        }


def create_features(sport: str, games: List[Dict], team_stats: Dict) -> pd.DataFrame:
    """Factory function to create features."""
    
    engineer = FeatureEngineer(sport)
    df = engineer.create_features(games, team_stats)
    df = engineer.normalize_features(df)
    
    return df
