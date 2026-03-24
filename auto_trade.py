"""
Automated paper trading runner.

Bet timing strategy:
  - Each game gets its own bet window: 90 minutes before puck drop.
  - The scheduler checks every minute and fires when the window opens.
  - This ensures we have the latest odds, lineup news, and injury reports.
  - Settlement runs at 08:00 each morning for the previous day's games.

Uses real Betway odds from TheOddsAPI.
Results come from the official NHL API.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Set

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env
_env = PROJECT_ROOT / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from core.pipeline import BetBrainPipeline
from strategy.selector import StrategySelector
from papertrade import get_paper_trader
from data.historical import HistoricalNHL
from data.nhl import NHLDataFetcher
from cache.odds_store import settle_game
from cache.inference_log import log_inference


STRATEGY        = os.environ.get("AUTO_STRATEGY", "value")
BET_STAKE       = float(os.environ.get("AUTO_STAKE", "50"))
MINUTES_BEFORE  = int(os.environ.get("AUTO_MINS_BEFORE", "90"))  # bet window before game


# ------------------------------------------------------------------ #
# Per-game bet placement
# ------------------------------------------------------------------ #

def place_bets_for_game(opp_group: List[Dict]) -> List[Dict]:
    """
    Place paper bets for one specific game's opportunities.
    opp_group = all opportunities (ML, Over, Under) for the same match.
    """
    if not opp_group:
        return []

    trader   = get_paper_trader()
    selector = StrategySelector(STRATEGY)

    # Skip if any opp uses fallback odds (no real Betway line available)
    if any(o.get("odds_source") in (None, "fallback") for o in opp_group):
        match = opp_group[0].get("match", "?")
        print(f"  [skip] {match} — no real odds available")
        return []

    placed = []
    placed_keys = set()
    seen   = set()
    for o in opp_group:
        if not selector.should_bet(o):
            continue
        key = (o["match"], o["market"])
        if key in seen:
            continue
        seen.add(key)

        bet = trader.place_bet(
            match      = o["match"],
            market     = o["market"],
            odds       = o["odds"],
            stake      = BET_STAKE,
            prediction = o.get("model_prob", 0),
            pick       = o.get("win_pick", ""),
            reasoning  = (
                f"Strategy={STRATEGY} | Edge={o.get('edge',0)*100:.1f}% | "
                f"Model={o.get('model_prob',0)*100:.1f}% vs "
                f"Market={o.get('implied_prob',0)*100:.1f}% | "
                f"Book={o.get('odds_source','?')} | "
                f"{o.get('reasoning','')[:120]}"
            ),
        )
        print(f"  [bet] {o['match']} | {o['market']} @ {o['odds']:.3f} | "
              f"pick={o.get('win_pick','?')} edge={o.get('edge',0)*100:.1f}%")
        placed_keys.add((o["match"], o["market"]))
        placed.append(bet)

    log_inference(opp_group, placed_keys)
    return placed


def place_todays_bets() -> List[Dict]:
    """
    Manual trigger: immediately place bets for ALL of today's value
    opportunities (ignores per-game timing — useful for testing or
    catching up if the scheduler missed a window).
    """
    print(f"[auto_trade] Manual place — strategy={STRATEGY}")
    now     = datetime.now()
    cutoff  = now + timedelta(hours=36)

    try:
        pipeline = BetBrainPipeline()
        opps     = pipeline.run(days=2)

        def _upcoming(o):
            start = o.get("start_time", "")
            date  = o.get("date", "")
            if not start or start == "TBD" or not date:
                return False
            try:
                game_dt = datetime.strptime(f"{date} {start}", "%Y-%m-%d %H:%M")
                return now < game_dt <= cutoff
            except ValueError:
                return False

        opps_today = [o for o in opps if _upcoming(o)]

        if not opps_today:
            print(f"[auto_trade] No upcoming games in next 36h")
            return []

        # Group by match
        by_match: Dict[str, List] = {}
        for o in opps_today:
            by_match.setdefault(o["match"], []).append(o)

        placed = []
        for match, group in by_match.items():
            placed.extend(place_bets_for_game(group))

        print(f"[auto_trade] Placed {len(placed)} bets")
        return placed

    except Exception as e:
        print(f"[auto_trade] ERROR: {e}")
        import traceback; traceback.print_exc()
        return []


# ------------------------------------------------------------------ #
# Settle yesterday's pending bets
# ------------------------------------------------------------------ #

def settle_pending_bets() -> List[Dict]:
    """
    Fetch results for any date that has pending bets and settle them.
    Runs each morning — handles games from yesterday and any older
    unsettled bets (e.g. postponed games).
    """
    trader  = get_paper_trader()
    pending = trader.get_pending_bets()

    if not pending:
        print("[auto_trade] No pending bets to settle")
        return []

    # Collect all dates that have pending bets
    dates_needed: Set[str] = set()
    for bet in pending:
        ts = bet.get("timestamp", "")[:10]   # "YYYY-MM-DD"
        if ts:
            dates_needed.add(ts)

    nhl = HistoricalNHL()
    results_map: Dict[str, Dict] = {}   # "AWAY @ HOME" -> game

    for date in sorted(dates_needed):
        results = nhl.get_games_for_range(date, date)
        for g in results:
            key = f"{g['away_team']} @ {g['home_team']}"
            results_map[key] = g

    if not results_map:
        print("[auto_trade] No results found for pending bet dates")
        return []

    settled = []
    for bet in pending:
        match  = bet.get("match", "")
        market = bet.get("market", "")
        game   = results_map.get(match)

        if not game:
            continue   # game not finished yet or date mismatch

        home_won    = game.get("home_won", False)
        total_goals = game.get("total_goals", 0)
        home_team   = game.get("home_team", "")
        away_team   = game.get("away_team", "")

        won = None

        if market == "Moneyline":
            pick = bet.get("pick", "")
            if pick == home_team:
                won = home_won
            elif pick == away_team:
                won = not home_won

        elif market.startswith("Over"):
            try:
                won = total_goals > float(market.split()[1])
            except (IndexError, ValueError):
                pass

        elif market.startswith("Under"):
            try:
                won = total_goals < float(market.split()[1])
            except (IndexError, ValueError):
                pass

        if won is None:
            print(f"  [skip] Can't determine outcome: {match} {market}")
            continue

        result  = trader.settle_bet(bet["id"], won)
        outcome = "WON ✓" if won else "LOST ✗"
        print(f"  [settle] {match} | {market} → {outcome} "
              f"(score {game['home_score']}-{game['away_score']})")
        settled.append(result)

        # Persist final score for future backtesting
        ts = bet.get("timestamp", "")[:10]
        try:
            settle_game(ts, game["home_team"], game["away_team"],
                        int(game["home_score"]), int(game["away_score"]))
        except Exception:
            pass

    print(f"[auto_trade] Settled {len(settled)} bets")
    return settled


# ------------------------------------------------------------------ #
# Per-game timing scheduler (called from the background thread)
# ------------------------------------------------------------------ #

# Tracks which (date, match) combos have already been bet so we don't
# double-bet across multiple scheduler ticks.
_already_bet: Set[tuple] = set()


def check_and_place_due_bets() -> List[Dict]:
    """
    Called every minute by the scheduler.
    Checks today's game schedule and places bets for any game whose
    window (MINUTES_BEFORE minutes before start) has opened.
    """
    now = datetime.now()

    try:
        nhl_fetcher = NHLDataFetcher()
        # Fetch enough days to cover games whose SA date is tomorrow
        schedule    = nhl_fetcher.get_schedule(days_forward=5)

        # Find games whose bet window just opened (within the last 2 minutes)
        # Use the game's own date field (already in SA local time) combined
        # with the start_time so we don't filter by "today" — games that
        # start at 01:00 SA belong to the next calendar day.
        due_games = []
        for game in schedule:
            start_str = game.get("start_time", "")
            game_date = game.get("date", "")
            if not start_str or start_str == "TBD" or not game_date:
                continue
            try:
                game_time = datetime.strptime(
                    f"{game_date} {start_str}", "%Y-%m-%d %H:%M"
                )
            except ValueError:
                continue

            bet_window = game_time - timedelta(minutes=MINUTES_BEFORE)
            key = (game_date, game["home_team"], game["away_team"])

            # Window opened in the last 2 minutes AND not already bet
            if bet_window <= now < bet_window + timedelta(minutes=2) and key not in _already_bet:
                due_games.append(game)
                _already_bet.add(key)

        if not due_games:
            return []

        # Run pipeline once and filter to due games
        pipeline = BetBrainPipeline()
        all_opps = pipeline.run(days=1)

        placed = []
        for game in due_games:
            match_key = f"{game['away_team']} @ {game['home_team']}"
            print(f"[auto_trade] Bet window open: {match_key} "
                  f"(T-{MINUTES_BEFORE}min)")
            group = [o for o in all_opps if o.get("match") == match_key
                     and o.get("date") == today]
            placed.extend(place_bets_for_game(group))

        return placed

    except Exception as e:
        print(f"[auto_trade] check_and_place error: {e}")
        return []


# ------------------------------------------------------------------ #
# CLI entrypoint
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["place", "settle", "both"],
                        nargs="?", default="both")
    args = parser.parse_args()

    if args.action in ("settle", "both"):
        settle_pending_bets()
    if args.action in ("place", "both"):
        place_todays_bets()
