"""
Sports Betting Analysis System Configuration
"""

import os

# API Keys (set via environment or leave empty for free tier)
API_KEYS = {
    "football_data_org": os.getenv("FOOTBALL_DATA_KEY", ""),  # football-data.org
    "balldontlie": os.getenv("BALLDONTLIE_KEY", ""),  # balldontlie.io
    "api_football": os.getenv("API_FOOTBALL_KEY", ""),  # api-football.com
}

# Sport configurations
SPORTS = {
    "nhl": {
        "name": "NHL Hockey",
        "leagues": ["NHL"],
        "markets": ["ml", "ou", "pp"],  # Moneyline, Over/Under, Period
        "api_base": "https://api-web.nhle.com",
    },
    "nba": {
        "name": "NBA Basketball",
        "leagues": ["NBA"],
        "markets": ["ml", "ou", "spread"],
        "api_base": "https://api.balldontlie.io",
    },
    "soccer": {
        "name": "Soccer",
        "leagues": ["EPL", "LaLiga", "Bundesliga", "SerieA", "Ligue1"],
        "markets": ["ml", "ou", "btts"],
        "api_base": "https://api.football-data.org",
    },
    "tennis": {
        "name": "Tennis",
        "leagues": ["ATP", "WTA"],
        "markets": ["ml", "ou"],  # Match winner, Over/Under games
        "api_base": "https://api.tennislive.net",
    },
}

# Model configurations
MODELS = {
    "default": "logistic",  # logistic, poisson, xgboost
    "xgboost": {
        "n_estimators": 100,
        "max_depth": 5,
        "learning_rate": 0.1,
    }
}

# Betting strategies
STRATEGIES = {
    "value": {
        "min_edge": 0.03,  # 3% minimum edge
        "min_ev": 0.05,    # 5% minimum expected value
    },
    "conservative": {
        "min_probability": 0.60,
        "max_edge": 0.20,
    },
    "aggressive": {
        "min_edge": 0.05,
        "kelly_fraction": 0.25,
    }
}

# Bankroll management
BANKROLL = {
    "initial": 1000,
    "kelly_fraction": 0.25,  # Fractional Kelly
    "max_bet_pct": 0.05,     # Max 5% of bankroll per bet
}

# Output settings
OUTPUT = {
    "format": "table",  # table, json, html
    "top_n": 5,         # Number of recommendations
    "include_reasoning": True,
}
