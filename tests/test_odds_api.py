from odds.odds_api import OddsAPIFetcher


def test_odds_api_fallback():
    fetcher = OddsAPIFetcher(api_key="")
    odds = fetcher.get_fallback_odds(0.55, 0.45)

    assert odds["home_ml"] >= 1.01
    assert odds["away_ml"] >= 1.01
    assert "fallback" in odds["source"]
