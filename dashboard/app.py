"""
BetBrain Dashboard — multi-agent pipeline
"""

from flask import Flask, render_template, jsonify, request, redirect
import sys, os, threading
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env if present
_env = PROJECT_ROOT / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from core.pipeline import BetBrainPipeline
from papertrade import get_paper_trader
from backtest import run_backtest
from strategy.selector import StrategySelector
import cache.backtest_cache as backtest_cache
from auto_trade import place_todays_bets, settle_pending_bets, check_and_place_due_bets
from cache.inference_log import get_recent as get_inference_log
import cache.system_log as syslog

app = Flask(__name__)
app.jinja_env.globals['enumerate'] = enumerate

# ---- Background scheduler ------------------------------------------------
# Runs settle at 08:00 and place bets at 17:00 every day (server local time).
# Uses a single daemon thread so it shuts down cleanly with the process.

_scheduler_started = False

def _run_scheduler():
    import time
    last_settle = None
    while True:
        now  = datetime.now()
        date = now.strftime("%Y-%m-%d")
        hour = now.hour

        # 08:00 — settle any pending bets whose games are now finished
        if hour == 8 and last_settle != date:
            try:
                settle_pending_bets()
            except Exception as e:
                syslog.error("scheduler", f"settle error: {e}", e)
                print(f"[scheduler] settle error: {e}")
            last_settle = date
            syslog.info("scheduler", f"Daily settlement run complete for {date}")

        # Every minute — check if any game's bet window just opened
        # (90 min before each game's scheduled start time)
        try:
            check_and_place_due_bets()
        except Exception as e:
            syslog.error("scheduler", f"place error: {e}", e)
            print(f"[scheduler] place error: {e}")

        time.sleep(60)  # tick every minute

def _start_scheduler():
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    t = threading.Thread(target=_run_scheduler, daemon=True, name="auto-trader")
    t.start()
    print("[scheduler] Auto-trader started — settle@08:00, bets placed 90min before each game")

_start_scheduler()
# --------------------------------------------------------------------------

STRATEGIES = {
    "value":       "Value Betting — edge >3%, medium+ confidence",
    "pdo_fade":    "PDO Regression — fade lucky teams (PDO>102), back unlucky (PDO<98)",
    "b2b_exploit": "Back-to-Back — exploit tired road B2B teams",
    "goalie_edge": "Goalie Edge — elite vs weak goalie matchup",
    "kelly":       "Kelly Optimal — bet whenever Kelly stake ≥1%",
}


@app.route('/')
def index():
    return redirect('/paper')


@app.route('/backtest')
def backtest_page():
    sport = request.args.get('sport', 'nhl')
    strategy = request.args.get('strategy', 'value')
    start = request.args.get('start', '2021-10-12')
    end = request.args.get('end', '2022-11-27')

    force_rerun = request.args.get('rerun') == '1'
    results = None
    if request.args.get('strategy'):  # only run if form was submitted
        results = run_backtest(sport, start, end, strategy, force_rerun=force_rerun)

    cached_runs = backtest_cache.list_runs()

    return render_template('backtest.html',
                           results=results,
                           sport=sport,
                           strategy=strategy,
                           strategies=STRATEGIES,
                           start=start,
                           end=end,
                           cached_runs=cached_runs)


@app.route('/paper')
def paper_trading():
    from datetime import timedelta
    from data.nhl import NHLDataFetcher

    trader  = get_paper_trader()
    status  = trader.get_status()
    pending = trader.get_pending_bets()
    history = trader.get_history()

    # Build upcoming game schedule with bet-window info
    MINS_BEFORE = int(os.environ.get("AUTO_MINS_BEFORE", "90"))
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # Collect matches that already have a pending bet
    pending_matches = {(b["match"], b["market"]) for b in pending}
    bet_placed_matches = {b["match"] for b in pending}

    # Collect matches already analysed today (logged in inference_log)
    from cache.inference_log import get_recent as get_inf_recent
    today_inf = get_inf_recent(hours=48, limit=500)
    # Use the most recent odds_source per match (earlier runs may have had real odds)
    from collections import defaultdict
    _latest: dict = {}  # match -> most recent entry
    for e in today_inf:
        m = e["match"]
        if m not in _latest or e.get("logged_at", "") > _latest[m].get("logged_at", ""):
            _latest[m] = e
    failed_matches   = {m for m, e in _latest.items()
                        if e.get("odds_source", "fallback") in ("fallback", "", None)}
    analysed_matches = {e["match"] for e in today_inf} - failed_matches

    schedule_cards = []
    try:
        nhl = NHLDataFetcher()
        games = nhl.get_schedule(days_forward=10)
        for g in games:
            gdate = g.get("date", "")
            start_str = g.get("start_time", "TBD")
            home = g.get("home_team", "")
            away = g.get("away_team", "")
            match = f"{away} @ {home}"

            bet_at = None
            minutes_until_bet = None
            status_label = "scheduled"

            if start_str and start_str != "TBD":
                try:
                    game_dt  = datetime.strptime(f"{gdate} {start_str}", "%Y-%m-%d %H:%M")
                    bet_dt   = game_dt - timedelta(minutes=MINS_BEFORE)
                    bet_at   = bet_dt.strftime("%H:%M")
                    diff     = (bet_dt - now).total_seconds()
                    minutes_until_bet = int(diff / 60)

                    if now > game_dt + timedelta(hours=10):
                        continue  # hide after 10h (well past any game ending)
                    elif match in bet_placed_matches:
                        status_label = "bet_placed"
                    elif match in failed_matches:
                        status_label = "failed"        # no real odds available
                    elif match in analysed_matches:
                        status_label = "skipped"       # real odds, no edge found
                    elif now > game_dt:
                        status_label = "started"       # started but never analysed (rare)
                    elif diff < 0:
                        status_label = "window_open"   # window open, not yet analysed
                    elif diff < 30 * 60:
                        status_label = "soon"          # < 30 min until bet window
                    else:
                        status_label = "scheduled"
                except ValueError:
                    pass

            schedule_cards.append({
                "date":              gdate,
                "home":              home,
                "away":              away,
                "match":             match,
                "start_time":        start_str,
                "bet_at":            bet_at,
                "minutes_until_bet": minutes_until_bet,
                "status":            status_label,
                "is_today":          gdate == today,
            })
    except Exception:
        pass

    # Build match → start_time lookup so bet rows can show game time
    start_time_map = {c["match"]: c["start_time"] for c in schedule_cards}
    for b in pending:
        b["start_time"] = start_time_map.get(b["match"], "")
    for b in history:
        b["start_time"] = start_time_map.get(b["match"], "")

    # --- Model accuracy / calibration stats ---
    settled = [b for b in history if b.get("status") in ("won", "lost")]
    model_stats = {"total": 0, "wins": 0, "pl": 0.0, "staked": 0.0,
                   "roi": 0.0, "win_rate": 0.0, "by_market": {}, "calibration": []}
    if settled:
        wins   = sum(1 for b in settled if b["status"] == "won")
        pl     = sum(b.get("profit", 0) for b in settled)
        staked = sum(b.get("stake", 50) for b in settled)
        # by market
        by_mkt = {}
        for b in settled:
            mkt = "Moneyline" if b["market"] == "Moneyline" else "Over/Under"
            by_mkt.setdefault(mkt, {"bets": 0, "wins": 0, "pl": 0.0, "staked": 0.0})
            by_mkt[mkt]["bets"]   += 1
            by_mkt[mkt]["wins"]   += 1 if b["status"] == "won" else 0
            by_mkt[mkt]["pl"]     += b.get("profit", 0)
            by_mkt[mkt]["staked"] += b.get("stake", 50)
        for mkt, d in by_mkt.items():
            d["win_rate"] = round(d["wins"] / d["bets"] * 100, 1)
            d["roi"]      = round(d["pl"] / d["staked"] * 100, 1)
        # calibration buckets
        buckets = {}
        for b in settled:
            p = b.get("prediction", 0.5)
            bucket = round(int(p * 10) / 10, 1)
            buckets.setdefault(bucket, []).append(b["status"] == "won")
        calibration = []
        for k in sorted(buckets):
            vals   = buckets[k]
            actual = sum(vals) / len(vals) * 100
            calibration.append({
                "label":    f"{int(k*100)}-{int(k*100)+9}%",
                "bets":     len(vals),
                "expected": round(k * 100, 0),
                "actual":   round(actual, 1),
                "diff":     round(actual - k * 100, 1),
            })
        model_stats = {
            "total":     len(settled),
            "wins":      wins,
            "pl":        round(pl, 2),
            "staked":    round(staked, 2),
            "roi":       round(pl / staked * 100, 1),
            "win_rate":  round(wins / len(settled) * 100, 1),
            "by_market": by_mkt,
            "calibration": calibration,
        }

    return render_template('paper.html',
                           status=status,
                           pending=pending,
                           history=history,
                           schedule=schedule_cards,
                           mins_before=MINS_BEFORE,
                           now_str=now.strftime("%H:%M"),
                           model_stats=model_stats,
                           failed_matches=failed_matches)


# -- API endpoints --

_analysis_cache = {"opportunities": None, "fetched_at": None}
_CACHE_TTL_MINUTES = 30

@app.route('/api/analyze')
def api_analyze():
    strategy = request.args.get('strategy', 'value')
    force = request.args.get('refresh') == '1'

    cache = _analysis_cache
    age = (datetime.now() - cache["fetched_at"]).total_seconds() / 60 if cache["fetched_at"] else None

    if force or cache["opportunities"] is None or age is None or age > _CACHE_TTL_MINUTES:
        pipeline = BetBrainPipeline()
        cache["opportunities"] = pipeline.run(days=3)
        cache["fetched_at"] = datetime.now()

    import copy
    from datetime import timedelta
    now = datetime.now()
    opportunities = copy.deepcopy(cache["opportunities"])

    # Filter out games that have already started (game datetime in the past)
    def game_started(o):
        date = o.get("date", "")
        start = o.get("start_time", "")
        if not date or not start or start == "TBD":
            return False
        try:
            return datetime.strptime(f"{date} {start}", "%Y-%m-%d %H:%M") < now
        except ValueError:
            return False

    opportunities = [o for o in opportunities if not game_started(o)]

    selector = StrategySelector(strategy)
    for o in opportunities:
        o["should_bet"] = selector.should_bet(o)
    return jsonify(opportunities)


@app.route('/api/strategies')
def api_strategies():
    return jsonify(STRATEGIES)


@app.route('/api/paper/status')
def api_paper_status():
    trader = get_paper_trader()
    return jsonify(trader.get_status())


@app.route('/api/paper/bet', methods=['POST'])
def api_paper_bet():
    data = request.json
    trader = get_paper_trader()
    bet = trader.place_bet(
        match=data.get('match'),
        market=data.get('market'),
        odds=float(data.get('odds')),
        stake=float(data.get('stake')),
        prediction=float(data.get('prediction')),
        reasoning=data.get('reasoning', ''),
    )
    return jsonify(bet)


@app.route('/api/paper/settle', methods=['POST'])
def api_paper_settle():
    data = request.json
    trader = get_paper_trader()
    result = trader.settle_bet(
        bet_id=int(data.get('bet_id')),
        won=bool(data.get('won')),
    )
    return jsonify(result)


@app.route('/api/auto/place', methods=['POST'])
def api_auto_place():
    """Manually trigger today's bet placement (same logic as the 17:00 scheduler)."""
    bets = place_todays_bets()
    return jsonify({"placed": len(bets), "bets": bets})


@app.route('/api/auto/settle', methods=['POST'])
def api_auto_settle():
    """Manually trigger settlement of yesterday's pending bets."""
    settled = settle_pending_bets()
    return jsonify({"settled": len(settled), "bets": settled})



@app.route('/api/inference/recent')
def api_inference_recent():
    hours = int(request.args.get('hours', 720))   # default 30 days so retro entries show
    limit = int(request.args.get('limit', 50))
    return jsonify(get_inference_log(hours=hours, limit=limit))


@app.route('/logs')
def logs_page():
    from cache.system_log import get_recent as get_sys_log
    hours = int(request.args.get('hours', 48))
    entries = get_sys_log(hours=hours)
    return render_template('logs.html', entries=entries, hours=hours)


@app.route('/api/logs/recent')
def api_logs_recent():
    from cache.system_log import get_recent as get_sys_log
    hours = int(request.args.get('hours', 24))
    return jsonify(get_sys_log(hours=hours))


if __name__ == '__main__':
    print("🏆 Starting BetBrain Dashboard...")
    print("   URL: http://localhost:5556")
    app.run(host='0.0.0.0', port=5556, debug=True)
