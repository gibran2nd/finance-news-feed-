import unittest
from unittest import mock

from newsfeed import markets


def yahoo_payload(price, closes):
    return {"chart": {"result": [{"meta": {"regularMarketPrice": price, "chartPreviousClose": 1.0},
                                  "indicators": {"quote": [{"close": closes}]}}]}}


class MarketTests(unittest.TestCase):
    def test_daily_change_uses_prior_session_not_window_start(self):
        # chartPreviousClose (1.0) is the close before the 5-day window and must be ignored
        with mock.patch.object(markets, "_get_json",
                               return_value=yahoo_payload(7805.45, [7801.77, 7765.36, None, 7807.24, 7805.45])):
            snap = markets.fetch_market_snapshot()
        spx = next(m for m in snap if m["key"] == "spx")
        self.assertAlmostEqual(spx["change"], 7805.45 - 7807.24, places=6)
        self.assertEqual(len(spx["spark"]), 4)          # None values dropped

    def test_all_sources_down_returns_none(self):
        with mock.patch.object(markets, "_get_json", side_effect=OSError("blocked")):
            self.assertIsNone(markets.fetch_market_snapshot())

    def test_cnbc_fallback(self):
        def fake(url):
            if "yahoo" in url:
                raise OSError("blocked")
            return {"FormattedQuoteResult": {"FormattedQuote": [
                {"symbol": ".SPX", "last": "7,805.45", "change": "-1.79"},
                {"symbol": "US10Y", "last": "5.321%", "change": "+0.104"}]}}
        with mock.patch.object(markets, "_get_json", side_effect=fake):
            snap = {m["key"]: m for m in markets.fetch_market_snapshot()}
        self.assertAlmostEqual(snap["spx"]["change"], -1.79, places=6)
        self.assertAlmostEqual(snap["us10"]["price"], 5.321, places=6)


if __name__ == "__main__":
    unittest.main()
