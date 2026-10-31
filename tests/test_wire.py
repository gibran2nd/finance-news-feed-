import unittest
from datetime import timedelta
from types import SimpleNamespace

from newsfeed import wire
from tests.helpers import NOW


def entry(title, hours_ago=1.0):
    pub = NOW - timedelta(hours=hours_ago)
    return SimpleNamespace(title="FinancialJuice: " + title, link="https://example.com/x",
                           published_parsed=pub.timetuple()[:6])


def titles(*entries):
    return [i["title"] for i in wire.parse_wire(SimpleNamespace(entries=list(entries)), NOW)]


class WireTests(unittest.TestCase):
    def test_keeps_market_news_and_strips_prefix(self):
        self.assertEqual(titles(entry("OPEC+ agrees to maintain production targets"),
                                entry("Turnout for French protests reached 320,000")),
                         ["OPEC+ agrees to maintain production targets"])

    def test_parses_data_print_without_forecast(self):
        self.assertEqual(wire.parse_print("Chinese Composite PMI Actual 49.7 (Forecast -, Previous 50.7)"),
                         {"name": "Chinese Composite PMI", "actual": "49.7", "forecast": None,
                          "previous": "50.7"})
        self.assertIsNone(wire.parse_print("Intel shares plunge 29%"))

    def test_rewrite_of_a_print_is_dropped(self):
        got = titles(entry("Chinese NBS Manufacturing PMI Actual 49.3 (Forecast 49.9, Previous 50.1)"),
                     entry("China October official manufacturing PMI at 49.3 vs 50.1 in September", 1.1))
        self.assertEqual(len(got), 1)

    def test_one_story_cannot_fill_the_panel(self):
        got = titles(*[entry(f"Iran navy: oil tanker {i} hit", i) for i in range(1, 6)])
        self.assertEqual(len(got), wire.MAX_PER_THEME)

    def test_one_line_per_company(self):
        got = titles(entry("OpenAI aiming for $20 billion: FT"), entry("OpenAI cuts funding goal: FT", 2))
        self.assertEqual(len(got), 1)

    def test_old_and_routine_items_are_dropped(self):
        self.assertEqual(titles(entry("Oil rises", wire.WIRE_HOURS + 1), entry("Monday FX Option Expiries")), [])

    def test_failed_fetch_hides_panel(self):
        original, wire.fetch_feed = wire.fetch_feed, lambda url: (None, "HTTP 429")
        try:
            self.assertEqual(wire.fetch_wire(NOW), [])
        finally:
            wire.fetch_feed = original


if __name__ == "__main__":
    unittest.main()
