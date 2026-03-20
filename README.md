# Sports Betting Analysis System (BetBrain)

**Purpose:** Generate data-driven betting recommendations for human execution. No automated betting.

**Sports:** Soccer, Basketball (NBA), Tennis, NHL

---

## Project Structure

```
sports-betting/
├── config.py           # API keys, sport configs
├── data/
│   ├── nhl.py         # NHL data fetcher
│   ├── nba.py         # NBA data fetcher  
│   ├── soccer.py      # Soccer data fetcher
│   └── tennis.py      # Tennis data fetcher
├── features/
│   └── engineer.py    # Feature engineering
├── models/
│   ├── poisson.py     # Poisson model (soccer)
│   ├── logistic.py    # Logistic regression
│   └── xgboost.py     # XGBoost model
├── odds/
│   └── scanner.py     # Odds comparison
├── strategies/
│   └── manager.py    # Betting strategies
├── output/
│   └── report.py     # Generate recommendations
├── main.py            # CLI entry point
└── tests/
```

---

## Core Modules

### 1. Data Ingestion

Free APIs per sport:
- **NHL:** `api-web.nhle.com` (free, no auth)
- **NBA:** `balldontlie.io` (free tier)
- **Soccer:** `api-football.com` (free tier) or `football-data.org`
- **Tennis:** `tennis-data.io` or scrape

### 2. Feature Engineering

Features per sport:
- Rolling averages (last 5-10 games)
- Home vs away performance
- Head-to-head
- Momentum/streaks
- Fatigue (games in last 7-14 days)
- Rest days between matches

### 3. Prediction Models

- **Poisson:** Goals distribution (soccer)
- **Logistic Regression:** Win probabilities
- **XGBoost:** Feature-based predictions
- **Elo:** Rating system baseline

### 4. Odds & Value

```python
def calculate_edge(model_prob, odds):
    implied_prob = 1 / odds
    edge = model_prob - implied_prob
    ev = edge * odds  # Expected value per unit bet
    return edge, ev
```

### 5. Strategies

- **Value:** Positive EV only
- **Conservative:** >60% prob, low variance
- **Aggressive:** >5% edge, higher variance
- **Kelly:** Fractional Kelly bankroll

### 6. Output

Daily recommendation table with all columns.

---

## Example Output Format

### NHL Recommendations - March 20, 2026

| Match | Market | Odds | Model % | Implied % | Edge | EV | Rec | Conf |
|-------|--------|------|---------|-----------|------|----|-----|------|
| MTL vs TOR | TOR ML | 1.85 | 58% | 54% | +4% | +7% | ✅ | Medium |
| EDM vs CGY | O5.5 | 1.90 | 52% | 53% | -1% | -2% | ❌ | Low |

### Summary
- **Top Value:** TOR ML (+7% EV)
- **Safest:** EDM vs CGY under
- **Skip:** 2 matches (negative EV)

---

## Run Commands

```bash
# Daily predictions for all sports
python main.py --sport nhl --date today

# Specific sport
python main.py --sport nba --date 2026-03-20

# Generate report
python main.py --report
```

---

## Important Notes

1. **No bet placement** — system outputs recommendations only
2. **Human executes** all bets
3. **Track performance** — accuracy, ROI over time
4. **Legal** — no ToS violation
5. **Responsible** — always gamble responsibly
