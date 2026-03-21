from backtest import RealBacktester


def test_backtest_returns_metrics():
    backtester = RealBacktester(strategy="value")
    result = backtester.run("2024-01-01", "2024-01-03")

    assert "metrics" in result
    assert result["metrics"]["total_bets"] >= 0
    assert result["metrics"]["final_bankroll"] >= 0
