# BetBrain

NHL sports betting analysis system with real-time data, multi-agent modelling, automated paper trading, and backtesting.

## What it does

1. Fetches today's NHL games from the official NHL API
2. Pulls live Betway odds from TheOddsAPI
3. Runs multiple statistical agents to compute win probabilities
4. Compares model probability vs market-implied probability to find edges
5. Automatically places paper bets 90 minutes before each game (no real money)
6. Settles bets each morning at 08:00 SA time using NHL results

---

## Running the app

### Recommended — Docker (persistent, auto-restarts)

```bash
cd ~/code/betbrain
docker compose up -d --build
```

Open: http://localhost:5556

The container runs 24/7 with `restart: unless-stopped`. Data (paper trades, backtest cache) persists in a Docker volume at `/data/betbrain.db`.

**Common commands:**
```bash
docker compose ps           # check status
docker compose logs -f      # live logs
docker compose down         # stop
docker compose up -d --build  # rebuild after code changes
```

### Development — run locally

```bash
cd ~/code/betbrain
pip install -r requirements.txt
python3 dashboard/app.py
```

---

## Environment variables (.env)

```
ODDS_API_KEY=your_key        # TheOddsAPI key (required for real Betway odds)
ANTHROPIC_API_KEY=your_key   # Optional — enables Claude research agent
AUTO_STRATEGY=value          # Strategy for auto-trader (default: value)
AUTO_STAKE=50                # Paper bet stake in dollars (default: 50)
AUTO_MINS_BEFORE=90          # Minutes before puck drop to place bets (default: 90)
TZ=Africa/Johannesburg       # Timezone (set in docker-compose.yml)
```

---

## Dashboard pages

| Page | URL | Description |
|------|-----|-------------|
| Analysis | `/` | Today's upcoming games with model predictions and BET/SKIP signals |
| Backtest | `/backtest` | Test a strategy against historical NHL seasons |
| Paper Trade | `/paper` | Live paper trading status, bet history, upcoming game schedule |

---

## Agents and how predictions are made

Every game runs through 5 agents. Each agent receives the same inputs: team stats (win rate, goals for/against, L10 form, PDO, back-to-back flag, goalie SV%, Pythagorean win%), the bookmaker O/U line, and the game date. Each agent outputs a ML pick (home/away/skip), a confidence score, an O/U pick, and a reasoning string.

| Agent | What it does |
|-------|-------------|
| **Statistical** | Poisson goal model. Calculates attack/defence lambdas from goals scored/allowed. Simulates ~10k games to estimate win probability and expected total. The mathematical backbone. |
| **ELO** | Maintains ELO ratings for every team, updated after each game result. Converts ELO gap → win probability via a logistic curve. Home advantage = +50 ELO points. |
| **Form** | Looks at L10 win rate, current win/loss streak, PDO (shooting% + save% × 100 — above 102 means lucky, expect regression), and back-to-back fatigue. Adjusts base win probability up or down. |
| **ResearchAgent** | Searches DuckDuckGo for injury/lineup news for both teams and hits the ESPN injury API. With `ANTHROPIC_API_KEY` set, uses Claude Haiku to read the text and decide if news is good or bad for each team. Without the key, falls back to keyword heuristics (words like "out", "doubtful", "scratch"). |
| **ClaudeAgent** | Receives all stats plus the other agents' votes, then writes a narrative reasoning and outputs its own pick. Acts as a tiebreaker and sanity check. Requires `ANTHROPIC_API_KEY`. |

### How the final decision is made

The `ConsensusAggregator` combines all 5 votes using a weighted average:

| Agent | Weight |
|-------|--------|
| Statistical | 40% |
| ResearchAgent | 25% |
| Form | 20% |
| ELO | 15% |
| ClaudeAgent | +20% bonus if it agrees with the majority |

From the weighted home win probability, it then:

1. **Devig** — removes the bookmaker's vig from the raw odds to get the true implied probability
2. **Edge** = model probability − true implied probability
3. **Bet threshold**: edge ≥ 3% and consensus confidence ≥ 45%
4. **Kelly stake**: fractional Kelly (25%) on the edge to size the bet
5. **Tier**: high (≥60% conf), medium (44–60%), low (<44%)

A bet is only flagged if the model collectively thinks the bookmaker is underpricing the team by at least 3 percentage points and the agents broadly agree on direction.

---

## Strategies

Strategies are filters on top of the model output. The model always runs the same agents — the strategy just controls which opportunities to act on.

| Strategy | Key | Logic |
|----------|-----|-------|
| Value Betting | `value` | Edge >3%, medium+ confidence |
| PDO Regression | `pdo_fade` | Fade lucky teams (PDO >102), back unlucky (PDO <98) |
| Back-to-Back | `b2b_exploit` | Exploit fatigued road B2B teams |
| Goalie Edge | `goalie_edge` | Elite vs weak goalie matchup |
| Kelly Optimal | `kelly` | Kelly stake ≥1% of bankroll |

---

## Project structure

```
betbrain/
├── dashboard/
│   ├── app.py              # Flask web app, API endpoints, background scheduler
│   └── templates/          # HTML templates (index, backtest, paper)
├── core/
│   ├── pipeline.py         # Main pipeline: fetches games, runs agents, returns opportunities
│   └── entities.py         # Dataclasses
├── agents/
│   ├── base.py             # BaseAgent class
│   ├── statistical.py      # Win probability from standings stats
│   ├── form.py             # L10 form and streak signals
│   ├── elo.py              # Elo rating model
│   ├── research.py         # Injury/news research agent
│   ├── claude_agent.py     # Claude LLM agent (needs ANTHROPIC_API_KEY)
│   └── consensus.py        # Aggregates all agent votes into final probability
├── strategy/
│   └── selector.py         # Strategy filter (should_bet logic per strategy)
├── data/
│   ├── nhl.py              # NHL schedule, standings, team stats
│   ├── nhl_advanced.py     # PDO, B2B detection, goalie stats (historical-safe)
│   └── historical.py       # Historical game results for backtesting/settlement
├── odds/
│   └── odds_api.py         # TheOddsAPI — fetches live Betway odds
├── cache/
│   └── backtest_cache.py   # SQLite cache for backtest results
├── auto_trade.py           # Automated bet placement and settlement logic
├── papertrade.py           # PaperTrader class — stores bets in SQLite (betbrain.db)
├── backtest.py             # Backtesting engine
├── Dockerfile              # Docker image definition
└── docker-compose.yml      # Docker Compose with volume and timezone config
```

---

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/analyze?strategy=value` | All opportunities with should_bet flag |
| GET | `/api/analyze?refresh=1` | Force recompute (bypass server cache) |
| GET | `/api/strategies` | List of available strategies |
| GET | `/api/paper/status` | Paper trading stats (bankroll, ROI, win rate) |
| POST | `/api/paper/bet` | Manually place a paper bet |
| POST | `/api/paper/settle` | Manually settle a bet by ID |
| POST | `/api/auto/place` | Trigger today's bet placement immediately |
| POST | `/api/auto/settle` | Trigger settlement of pending bets immediately |

---

## Auto-trader

The background scheduler runs inside the Flask process (daemon thread):

- **Every minute**: checks if any game's bet window (90 min before puck drop) just opened. If yes, runs the pipeline for that game and places bets.
- **08:00 SA time daily**: fetches NHL results for all dates with pending bets and settles them.

Bets are only placed when:
- Real Betway odds are available (not fallback/estimated)
- The strategy filter passes (e.g. edge >3% for `value` strategy)

---

## Backtesting notes

- Historical data uses NHL API `/v1/standings/{date}` for point-in-time standings
- B2B detection uses `/v1/schedule/{date}` (historical-safe, not current season)
- Backtest results are cached in SQLite to avoid rerunning (~150 API calls per run)
- Gunicorn timeout is set to 600s to handle long backtest runs

---

## Data sources

| Source | What it provides | Auth required |
|--------|-----------------|---------------|
| api-web.nhle.com | Schedule, standings, game results | No |
| api.the-odds-api.com | Live Betway odds | Yes (ODDS_API_KEY) |
| Anthropic API | Claude research agent | Yes (ANTHROPIC_API_KEY) |
