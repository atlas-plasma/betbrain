"""
BetBrain Dashboard — multi-agent pipeline
"""

from flask import Flask, render_template, jsonify, request
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
    sport = request.args.get('sport', 'nhl')
    strategy = request.args.get('strategy', 'value')

    # Render the page shell immediately — data loads async via /api/analyze
    return render_template('index.html',
                           sport=sport,
                           strategy=strategy,
                           strategies=STRATEGIES,
                           generated=datetime.now().strftime('%Y-%m-%d %H:%M'))


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

                    if now > game_dt + timedelta(hours=3):
                        continue  # game is finished, skip it
                    elif match in bet_placed_matches:
                        status_label = "bet_placed"
                    elif now > game_dt:
                        status_label = "started"
                    elif diff < 0:
                        status_label = "window_open"  # bet window open but no bet yet
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

    return render_template('paper.html',
                           status=status,
                           pending=pending,
                           history=history,
                           schedule=schedule_cards,
                           mins_before=MINS_BEFORE,
                           now_str=now.strftime("%H:%M"))


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


@app.route('/audit')
def audit():
    from cache.inference_log import get_for_date
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    entries = get_for_date(date)
    trader = get_paper_trader()
    all_bets = trader.get_history(limit=500)
    date_bets = [b for b in all_bets if b.get('timestamp', '').startswith(date)]
    return render_template('audit.html', date=date, entries=entries, bets=date_bets)


@app.route('/api/inference/recent')
def api_inference_recent():
    hours = int(request.args.get('hours', 24))
    return jsonify(get_inference_log(hours=hours))


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
