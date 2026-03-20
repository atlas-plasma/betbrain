# BetBrain 🏆

Sports betting analysis system with real-time NHL data, multiple strategies, backtesting, and paper trading.

## Features

- **Real-time NHL Analysis** - Fetches actual games from NHL API
- **Multiple Strategies** - Value, Conservative, Aggressive, Tier-Based, Model Plus
- **Backtesting** - Test strategies against historical data
- **Paper Trading** - Simulate bets without risking real money
- **Web Dashboard** - Beautiful Flask UI

## Quick Start

```bash
cd ~/.openclaw/workspace/sports-betting

# Install dependencies
pip install requests flask pandas numpy

# Run dashboard
PYTHONPATH=. python3 -m dashboard.app
```

## Dashboard

- **Local:** http://localhost:5556
- **Public:** Use localtunnel (`lt --port 5556`)

## Strategies

| Strategy | Description | Threshold |
|----------|-------------|-----------|
| Value | Positive edge only | >3% edge |
| Conservative | High probability | >55% win |
| Aggressive | Higher edge | >5% edge |
| Tier-Based | Claude's methodology | Multiple factors |
| Model Plus | Multiple signals | Convergence |

## Columns

- **Time** - Match start time (SA timezone)
- **Match** - Away @ Home
- **Pick** - Win pick (team or OVER/UNDER)
- **Market** - Bet type (ML, Over/Under)
- **Odds** - Decimal odds
- **Win %** - Model probability
- **Edge** - Model % minus implied %
- **Goals** - Projected total goals

## Project Structure

```
sports-betting/
├── main.py           # Main analysis engine
├── config.py         # Configuration
├── backtest.py       # Backtesting engine
├── data/
│   └── nhl.py       # NHL API fetcher
├── models/
│   └── predictor.py # ML models
├── strategy/
│   ├── selector.py   # Strategy selector
│   └── advanced.py   # Advanced strategies
├── research_agent/
│   └── agent.py      # Web research
└── dashboard/
    ├── app.py        # Flask app
    └── templates/    # HTML templates
```

## Backtesting

Go to `/backtest` to test strategies:
- Select strategy
- Pick date range
- View ROI, win rate, bankroll

## API

- `/` - Main analysis page
- `/backtest` - Backtesting page
- `/paper` - Paper trading

## Notes

- Analysis only - no real bets placed
- Uses free NHL API
- Times in SA timezone (GMT+2)
