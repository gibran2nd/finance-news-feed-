import unittest

from newsfeed.filters import is_junk, is_off_topic, is_stale_summary, normalize_publisher


class JunkTests(unittest.TestCase):
    def test_real_news_kept(self):
        for title in ["Japan's Omron to buy US industrial PC firm Onlogic for $675 million",
                      "Société Générale profit beats estimates",
                      "Wells Fargo beats profit estimates, but net interest income falls short",
                      "Current account deficit widens to record",
                      "Director of the Fed's markets desk sells view on rates"]:
            self.assertFalse(is_junk(title, "Reuters"), title)

    def test_junk_dropped(self):
        cases = [("Fastenal Q3 2026 Earnings Preview", "Seeking Alpha"),
                 ("매일경제 뉴스", "매일경제"),
                 ("REG - Glenstone REIT PLC - Acceptance Level Update", "London South East"),
                 ("Insider buys $2M of shares", "https://x.in/"),
                 ("Dexus Industria REIT Buys Back 59,259 Securities", "Kalkine"),
                 ("Here's where Jim Cramer stands on this AI stock", "CNBC"),
                 ("We're upgrading our rating on Wells Fargo", "CNBC"),
                 ("Current Home Equity Loan Rates", "WSJ"),
                 ("Best high-yield savings accounts of October 2026", "CNBC"),
                 ("PODCAST: Cashing in chips", "Reuters")]
        for title, pub in cases:
            self.assertTrue(is_junk(title, pub), title)

    def test_publisher_aliases(self):
        self.assertEqual(normalize_publisher("Bloomberg.com"), "Bloomberg")
        self.assertEqual(normalize_publisher("Financial Times"), "FT")
        self.assertEqual(normalize_publisher("Investing.com Nigeria"), "Investing.com")


class RelevanceTests(unittest.TestCase):
    def test_finance_kept_on_filtered_feeds(self):
        for title in ["CVS agrees to pay $315 million to settle Justice Department case",
                      "Nokia sells Enterprise Campus Edge business to Aurelius",
                      "Boeing deliveries tick up to 57 jets in September",
                      "Stellantis Q3 shipments fall 1%",
                      "Kroger to lay off 3,000 corporate employees over 3 years",
                      "Micron sinks, other memory-linked names dip for a second day",
                      "US-China trade talks resume as tariffs loom",
                      "Character.ai Maker Files for Chapter 11 Bankruptcy"]:
            self.assertFalse(is_off_topic(title, True), title)

    def test_off_topic_dropped(self):
        for title in ["Pope Leo XIV diagnosed with lung cancer after surgery",
                      "WNBA Finals Games 3 and 4 move to State Farm Arena in Atlanta",
                      "A list of US roller coaster fatalities dating back to 2003",
                      "Science Corporation implants its vision-restoring chip in its first patient",
                      "Judge orders OpenAI to turn over hiring records in Apple trade secrets case",
                      "Judge says Musk engaged in intimidation of ex-FEMA CFO Mary Comans"]:
            self.assertTrue(is_off_topic(title, True), title)

    def test_advice_columns_dropped_everywhere(self):
        self.assertTrue(is_off_topic(
            "My wife says we can’t afford to retire, yet she wants a trip to Italy", False))

    def test_unfiltered_feeds_keep_everything_else(self):
        self.assertFalse(is_off_topic("Pope Leo XIV diagnosed with lung cancer", False))


class StaleSummaryTests(unittest.TestCase):
    def test_results_headline_with_preview_blurb(self):
        self.assertTrue(is_stale_summary("Morgan Stanley tops estimates",
                                         "Morgan Stanley is expected to benefit from trading"))
        self.assertFalse(is_stale_summary("UnitedHealth tops estimates",
                                          "UnitedHealth said it expects 2026 earnings of $20.50"))
        self.assertFalse(is_stale_summary("Morgan Stanley to report Q3 earnings",
                                          "Morgan Stanley is expected to benefit"))


if __name__ == "__main__":
    unittest.main()
