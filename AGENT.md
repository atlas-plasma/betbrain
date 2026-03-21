# BetBrain — Agent Reference

This file is for LLM agents (Claude, GPT, etc.) to understand the BetBrain codebase and know how to operate it.

---

## What this repo is

BetBrain is an automated NHL sports betting analysis and paper trading system. It:
- Fetches live NHL game schedules and team statistics
- Pulls real Betway odds from TheOddsAPI
- Runs multi-agent statistical models to compute win probabilities
- Compares model probability vs bookmaker-implied probability to find edges
- Automatically places and settles paper bets (no real money)
- Serves a web dashboard at http://localhost:5556

---

## How to start the app

### Preferred (persistent, Docker):
```bash
cd ~/code/betbrain
docker compose up -d --build
```

### Dev mode (local Python):
```bash
cd ~/code/betbrain
python3 dashboard/app.py
```

App runs on port 5556.

---

## Key skills / actions you can perform

### Run analysis for today's games
```bash
# Via API (returns JSON)
curl "http://localhost:5556/api/analyze?strategy=value"

# With force refresh (bypass cache)
curl "http://localhost:5556/api/analyze?strategy=value&refresh=1"
```
Returns a list of opportunity objects with: `match`, `date`, `start_time`, `market`, `win_pick`, `odds`, `model_prob`, `implied_prob`, `edge`, `ev`, `kelly`, `confidence`, `should_bet`, `home_team`, `away_team`, `home_b2b`, `away_b2b`, `home_pdo`, `away_pdo`.

### Place a paper bet manually
```bash
curl -X POST http://localhost:5556/api/paper/bet \
  -H "Content-Type: application/json" \
  -d '{"match": "TOR @ MTL", "market": "Moneyline", "odds": 1.85, "stake": 50, "prediction": 0.62, "reasoning": "Strong home form"}'
```

### Settle a pending bet manually
```bash
curl -X POST http://localhost:5556/api/paper/settle \
  -H "Content-Type: application/json" \
  -d '{"bet_id": 1, "won": true}'
```

### Trigger bet placement now (all today's games)
```bash
curl -X POST http://localhost:5556/api/auto/place
```

### Trigger settlement now
```bash
curl -X POST http://localhost:5556/api/auto/settle
```

### Check paper trading status
```bash
curl "http://localhost:5556/api/paper/status"
```
Returns: `bankroll`, `total_profit`, `profit_pct`, `win_rate`, `total_bets`, `pending_bets`, `won`, `lost`, `avg_clv`.

### List available strategies
```bash
curl "http://localhost:5556/api/strategies"
```

---

## Running a backtest from Python

```python
from backtest import run_backtest

results = run_backtest(
    sport="nhl",
    start_date="2021-10-12",
    end_date="2022-04-29",
    strategy="value",
    force_rerun=False   # True to bypass cache
)
# results keys: total_bets, won, lost, win_rate, total_profit, roi, bankroll, bets[]
```

---

## Running analysis from Python

```python
from core.pipeline import BetBrainPipeline
from strategy.selector import StrategySelector

pipeline = BetBrainPipeline()
opportunities = pipeline.run(days=3)  # next 3 days of games

selector = StrategySelector("value")  # or: pdo_fade, b2b_exploit, goalie_edge, kelly
bets = [o for o in opportunities if selector.should_bet(o)]
```

---

## Paper trading from Python

```python
from papertrade import get_paper_trader

trader = get_paper_trader()

# Place a bet
bet = trader.place_bet(
    match="TOR @ MTL",
    market="Moneyline",
    odds=1.85,
    stake=50,
    prediction=0.62,
    pick="MTL",
    reasoning="Strong home form"
)

# Settle a bet
trader.settle_bet(bet_id=1, won=True)

# Get status
status = trader.get_status()
# keys: bankroll, total_profit, win_rate, won, lost, pending_bets, avg_clv

# Get pending bets
pending = trader.get_pending_bets()

# Get history
history = trader.get_history(limit=20)
```

---

## Auto-trader from Python

```python
from auto_trade import place_todays_bets, settle_pending_bets

# Place bets for all of today's value opportunities immediately
placed = place_todays_bets()

# Settle all pending bets (fetches NHL results)
settled = settle_pending_bets()
```

---

## Opportunity object fields

| Field | Type | Description |
|-------|------|-------------|
| `match` | str | "AWAY @ HOME" format e.g. "TOR @ MTL" |
| `date` | str | "YYYY-MM-DD" (North American game date) |
| `start_time` | str | "HH:MM" in SA timezone (Africa/Johannesburg) |
| `market` | str | "Moneyline", "Over 6.5", "Under 6.5" |
| `win_pick` | str | Team abbreviation or "OVER"/"UNDER" |
| `odds` | float | Decimal odds (e.g. 1.85) |
| `model_prob` | float | Model's estimated win probability (0-1) |
| `implied_prob` | float | Market-implied probability after vig removal (0-1) |
| `edge` | float | model_prob - implied_prob. >0.03 = value |
| `ev` | float | Expected value per $1 staked |
| `kelly` | float | Fractional Kelly stake as fraction of bankroll |
| `confidence` | str | "low", "medium", "high" |
| `should_bet` | bool | True if current strategy filter passes |
| `home_team` | str | Home team abbreviation |
| `away_team` | str | Away team abbreviation |
| `home_b2b` | bool | Home team played yesterday |
| `away_b2b` | bool | Away team played yesterday |
| `home_pdo` | float | Home team PDO (>102 = lucky, <98 = unlucky) |
| `away_pdo` | float | Away team PDO |
| `score_pred` | str | Predicted score e.g. "3.2 - 2.8" |
| `pred_total` | float | Predicted total goals |
| `ou_line` | float | Over/under line (typically 6.5) |
| `odds_source` | str | "betway", "fallback", or None |
| `agent_votes` | list | Individual agent ML/OU votes and reasoning |

---

## Strategies

| Key | Logic |
|-----|-------|
| `value` | edge > 0.03 and confidence in (medium, high) |
| `pdo_fade` | Bet against lucky teams (PDO>102) or on unlucky ones (PDO<98), edge > 0.02 |
| `b2b_exploit` | Bet against B2B road teams, or Under when B2B team playing, edge > 0.02 |
| `goalie_edge` | Elite goalie (sv%>91.5) vs weak (sv%<90.5), edge > 0.02 |
| `kelly` | kelly >= 0.01 and edge > 0.01 |

---

## Important files

| File | Purpose |
|------|---------|
| `dashboard/app.py` | Flask app, all routes, background scheduler |
| `core/pipeline.py` | Orchestrates data fetch + agent runs → list of opportunities |
| `agents/consensus.py` | Aggregates all agent votes into final model_prob |
| `strategy/selector.py` | should_bet() logic for each strategy |
| `auto_trade.py` | Automated placement and settlement |
| `papertrade.py` | PaperTrader — stores bets in paper_trade_history.json |
| `backtest.py` | Historical backtesting engine |
| `data/nhl.py` | NHL schedule, standings API |
| `data/nhl_advanced.py` | PDO, B2B, goalie stats — historical-safe |
| `data/historical.py` | Game results for settlement and backtesting |
| `odds/odds_api.py` | TheOddsAPI — live Betway odds |
| `cache/backtest_cache.py` | SQLite cache for backtest runs |

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ODDS_API_KEY` | — | TheOddsAPI key (required for real odds) |
| `ANTHROPIC_API_KEY` | — | Enables Claude research agent |
| `AUTO_STRATEGY` | `value` | Strategy used by auto-trader |
| `AUTO_STAKE` | `50` | Dollar stake per paper bet |
| `AUTO_MINS_BEFORE` | `90` | Minutes before puck drop to place bet |
| `TZ` | `Africa/Johannesburg` | Timezone for all datetime operations |

---

## Common agent tasks

**"What bets were placed today?"**
```python
from papertrade import get_paper_trader
from datetime import datetime
today = datetime.now().strftime("%Y-%m-%d")
trader = get_paper_trader()
todays = [b for b in trader.get_pending_bets() if b["timestamp"].startswith(today)]
```

**"What is the current ROI?"**
```python
from papertrade import get_paper_trader
status = get_paper_trader().get_status()
print(f"ROI: {status['profit_pct']:.1f}%  Win rate: {status['win_rate']*100:.1f}%")
```

**"Find value bets for tonight"**
```python
from core.pipeline import BetBrainPipeline
from strategy.selector import StrategySelector
from datetime import datetime

opps = BetBrainPipeline().run(days=1)
selector = StrategySelector("value")
bets = [o for o in opps if selector.should_bet(o) and o.get("date") == datetime.now().strftime("%Y-%m-%d")]
for b in bets:
    print(f"{b['match']} | {b['market']} | pick={b['win_pick']} | odds={b['odds']:.2f} | edge={b['edge']*100:.1f}%")
```
