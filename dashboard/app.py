"""
BetBrain Dashboard with Strategy Selector
"""

from flask import Flask, render_template, jsonify, request
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from main import BetBrain
from papertrade import get_paper_trader
from backtest import run_backtest
from strategy.selector import StrategySelector

app = Flask(__name__)

# Strategy list for dropdown
STRATEGIES = {
    "value": "Value Betting - Positive edge only (>3%)",
    "conservative": "Conservative - High probability (>55%)",
    "aggressive": "Aggressive - Higher edge (>5%)",
    "tier_based": "Tier-Based - Claude's methodology",
    "model_plus": "Model Plus - Multiple converging signals"
}

@app.route('/')
def index():
    sport = request.args.get('sport', 'nhl')
    strategy = request.args.get('strategy', 'value')
    
    bot = BetBrain(sport=sport)
    opportunities = bot.analyze(days=3)
    
    # Apply strategy filter
    selector = StrategySelector(strategy)
    filtered = [o for o in opportunities if selector.should_bet(o)]
    
    bets = [o for o in filtered if o.get("recommendation") == "BET"]
    others = [o for o in opportunities if o.get("recommendation") == "SKIP"][:10]
    
    return render_template('index.html', 
                         bets=bets[:5], 
                         others=others,
                         sport=sport,
                         strategy=strategy,
                         strategies=STRATEGIES,
                         generated=datetime.now().strftime('%Y-%m-%d %H:%M'))

@app.route('/backtest')
def backtest_page():
    sport = request.args.get('sport', 'nhl')
    strategy = request.args.get('strategy', 'value')
    start = request.args.get('start', '2024-01-01')
    end = request.args.get('end', '2024-12-31')
    
    results = run_backtest(sport, start, end, strategy)
    
    return render_template('backtest.html',
                         results=results,
                         sport=sport,
                         strategy=strategy,
                         strategies=STRATEGIES,
                         start=start,
                         end=end)

@app.route('/paper')
def paper_trading():
    trader = get_paper_trader()
    status = trader.get_status()
    pending = trader.get_pending_bets()
    history = trader.get_history()
    
    return render_template('paper.html',
                         status=status,
                         pending=pending,
                         history=history)

# API endpoints
@app.route('/api/analyze')
def api_analyze():
    sport = request.args.get('sport', 'nhl')
    strategy = request.args.get('strategy', 'value')
    
    bot = BetBrain(sport=sport)
    opportunities = bot.analyze(days=3)
    
    # Apply strategy filter
    selector = StrategySelector(strategy)
    filtered = [o for o in opportunities if selector.should_bet(o)]
    
    return jsonify(filtered)

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
        reasoning=data.get('reasoning', '')
    )
    
    return jsonify(bet)

@app.route('/api/paper/settle', methods=['POST'])
def api_paper_settle():
    data = request.json
    trader = get_paper_trader()
    
    result = trader.settle_bet(
        bet_id=int(data.get('bet_id')),
        won=bool(data.get('won'))
    )
    
    return jsonify(result)

if __name__ == '__main__':
    print("🏆 Starting BetBrain Dashboard...")
    print("   URL: http://localhost:5556")
    app.run(host='0.0.0.0', port=5556, debug=True)
