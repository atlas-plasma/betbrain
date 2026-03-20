# BetBrain - Sports Betting Analysis System

🏆 Data-driven sports betting recommendations for human execution.

## Features

- 📊 **Analysis** - Analyze upcoming games and find value bets
- 📈 **Backtesting** - Test strategies on historical data
- 🎯 **Paper Trading** - Simulate bets without real money
- 🏒 **Multi-sport** - NHL, NBA, Soccer, Tennis support

## Quick Start

```bash
# Install dependencies
pip install flask pandas numpy

# Run dashboard
cd dashboard
python app.py

# Open http://localhost:5556
```

## Project Structure

```
sports-betting/
├── config.py           # Configuration
├── main.py             # CLI entry point
├── data/
│   ├── nhl.py         # NHL data fetcher
│   ├── nba.py        # NBA data fetcher
│   └── soccer.py     # Soccer data fetcher
├── models/
│   └── predictor.py   # Prediction models
├── odds/
│   └── scanner.py    # Odds & value detection
├── backtest.py        # Backtesting engine
├── papertrade.py     # Paper trading
└── dashboard/
    ├── app.py        # Flask dashboard
    └── templates/    # HTML templates
```

## Usage

### Analysis
```bash
python main.py --sport nhl --days 3
```

### Backtest
```bash
python main.py --backtest --sport nhl --start 2024-01-01 --end 2024-12-31
```

### Dashboard
```bash
cd dashboard
python app.py
```

Then open http://localhost:5556

## Pages

- **/** - Today's value bets
- **/backtest** - Run strategy backtests
- **/paper** - Paper trading simulation

## Disclaimer

This is analysis only. No bets are placed automatically. Always gamble responsibly.
