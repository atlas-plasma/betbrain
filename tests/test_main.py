from main import BetBrain


def test_analyze_outputs_consistent_keys():
    bot = BetBrain()
    opportunities = bot.analyze(days=1)

    assert isinstance(opportunities, list)
    if opportunities:
        opp = opportunities[0]
        assert "market" in opp
        assert "edge" in opp
        assert opp["market"] in ["ML (Home)", "ML (Away)", "Over 6.5"] or opp["market"].startswith("Over")
        assert isinstance(opp["edge"], float)
