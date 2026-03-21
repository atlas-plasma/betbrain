from strategy.selector import StrategySelector


def test_strategy_selector_value():
    s = StrategySelector("value")
    assert s.should_bet({"edge": 0.04, "model_prob": 0.6}) is True
    assert s.should_bet({"edge": 0.02, "model_prob": 0.6}) is False


def test_strategy_selector_conservative():
    s = StrategySelector("conservative")
    assert s.should_bet({"edge": 0.01, "model_prob": 0.56}) is True
    assert s.should_bet({"edge": 0.02, "model_prob": 0.52}) is False
