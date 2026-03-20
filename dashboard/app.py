"""
BetBrain Dashboard
Flask web app for betting analysis
"""

from flask import Flask, render_template, jsonify, request
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from main import BetBrain
from papertrade import get_paper_trader
from backtest import run_backtest

app = Flask(__name__)

# Pages
@app.route('/')
def index():
    """Home page with current analysis."""
    sport = request.args.get('sport', 'nhl')
    bot = BetBrain(sport=sport)
    opportunities = bot.analyze(days=3)
    
    # Separate bets and non-bets
    bets = [o for o in opportunities if o.recommendation == "BET"]
    others = [o for o in opportunities if o.recommendation == "SKIP"]
    
    return render_template('index.html', 
                         bets=bets[:5], 
                         others=others[:10],
                         sport=sport,
                         generated=datetime.now().strftime('%Y-%m-%d %H:%M'))

@app.route('/backtest')
def backtest_page():
    """Backtest results page."""
    sport = request.args.get('sport', 'nhl')
    strategy = request.args.get('strategy', 'value')
    start = request.args.get('start', '2024-01-01')
    end = request.args.get('end', '2024-12-31')
    
    results = run_backtest(sport, start, end, strategy)
    
    return render_template('backtest.html',
                         results=results,
                         sport=sport,
                         strategy=strategy,
                         start=start,
                         end=end)

@app.route('/paper')
def paper_trading():
    """Paper trading page."""
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
    """API: Run analysis."""
    sport = request.args.get('sport', 'nhl')
    bot = BetBrain(sport=sport)
    opportunities = bot.analyze(days=3)
    
    return jsonify([{
        "match": o.match,
        "market": o.market,
        "odds": o.odds,
        "model_prob": o.model_prob,
        "implied_prob": o.implied_prob,
        "edge": o.edge,
        "ev": o.ev,
        "recommendation": o.recommendation,
        "confidence": o.confidence,
        "reasoning": o.reasoning
    } for o in opportunities])

@app.route('/api/paper/status')
def api_paper_status():
    """API: Get paper trading status."""
    trader = get_paper_trader()
    return jsonify(trader.get_status())

@app.route('/api/paper/bet', methods=['POST'])
def api_paper_bet():
    """API: Place paper bet."""
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
    """API: Settle paper bet."""
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
