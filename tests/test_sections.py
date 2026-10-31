import unittest

from newsfeed import sections, stories
from newsfeed.filters import is_off_topic, is_roundup
from tests.helpers import NOW, art


class ClassifyTests(unittest.TestCase):
    def check(self, section, *titles):
        for title in titles:
            self.assertEqual(sections.classify(title), section, title)

    def test_topics(self):
        self.check(sections.DEALS, "CD&R pursues buyout of Global Payments",
                   "OPay prices IPO at $19 per share", "Apollo to buy nearly 10% stake in Mubadala Capital",
                   "DoorDash strikes $17 billion deal for US rival Instacart")
        self.check(sections.EARNINGS, "Exxon, Chevron profits beat forecasts",
                   "Illumina Raises Full-Year Outlook on Solid Q3 Performance")
        self.check(sections.MACRO, "Fed needs at least two more rate hikes, Logan says",
                   "Third-quarter U.S. GDP increases 3.4%", "German inflation slows in October",
                   "Euro zone economy slows to 0.4% growth in Q3")
        self.check(sections.TECH, "$6.3 billion Binance hack is largest crypto theft on record")
        self.check(sections.STOCKS, "U.S. stocks slide as tech sells off")

    def test_not_fooled_by_ordinary_words(self):
        self.assertNotEqual(sections.classify("Microsoft offers buyouts to around 60,000 employees"),
                            sections.DEALS)
        self.assertNotEqual(sections.classify("Analysts say buy the dip: how to buy shares"),
                            sections.DEALS)
        self.assertIsNone(sections.classify("Well-fed cattle fetch more at auction"))

    def test_deals_blocklist_still_applies(self):
        self.assertNotEqual(sections.classify("Trump merger comment rattles bankers"), sections.DEALS)

    def test_real_estate_trade_press_stays_home(self):
        self.assertEqual(sections.assign_section("Blackstone Mortgage Trust Reports Q3 Net Loss",
                                                 sections.REAL_ESTATE, list(sections.FEEDS)),
                         sections.REAL_ESTATE)

    def test_unclear_story_stays_home(self):
        self.assertEqual(sections.assign_section("Vail Resorts investor backs company", sections.STOCKS,
                                                 list(sections.FEEDS)), sections.STOCKS)


class SelectionTests(unittest.TestCase):
    def test_story_moves_to_its_topic_and_color(self):
        raw = {sections.STOCKS: [art("CD&R pursues buyout of Global Payments", "Reuters", section=sections.STOCKS)],
               sections.DEALS: []}
        _, picked = stories.select_stories(raw, 12, NOW, 36, by_coverage=False)
        self.assertEqual(picked[sections.STOCKS], [])
        moved = picked[sections.DEALS][0]
        self.assertEqual(moved["section"], sections.DEALS)
        self.assertEqual(moved["color"], sections.FEEDS[sections.DEALS]["color"])

    def test_recap_is_never_a_top_story(self):
        recap = art("The hawkish pause and the Anthropic IPO bombshell: The financial week in five charts", "Reuters")
        news = [art("Anthropic IPO bombshell shakes the financial week", s) for s in ("CNBC", "AP")]
        top, _ = stories.select_stories({sections.STOCKS: [recap, *news]}, 12, NOW, 36, by_coverage=False)
        self.assertNotIn(recap["title"], [a["title"] for a in top])

    def test_reposted_press_release_counts_once(self):
        title = "PhotonPay Raises $40M Series C to Scale Its Stablecoin-Centric Financial OS"
        arts = [art(title, f"Local Paper {i}") for i in range(20)]
        stories.cluster_articles(arts)
        self.assertEqual(arts[0]["coverage"], 1)

    def test_press_release_cannot_be_a_top_story(self):
        arts = [art(f"PhotonPay raises $40M Series C version {i}", f"Local Paper {i}") for i in range(5)]
        top, _ = stories.select_stories({sections.STOCKS: arts}, 12, NOW, 36, by_coverage=False)
        self.assertEqual(top, [])

    def test_company_limit_covers_the_page(self):
        raw = {sections.TECH: [art(f"Binance angle {w} unrelated wording {i}", f"Outlet {i}", hours_ago=i / 10,
                                   section=sections.TECH)
                               for i, w in enumerate(("hackers", "wallets", "regulators", "reserves", "customers"))]}
        _, picked = stories.select_stories(raw, 12, NOW, 36, by_coverage=False)
        self.assertLessEqual(len(picked[sections.TECH]), stories.MAX_PER_COMPANY)

    def test_prefers_card_with_summary(self):
        bare = art("Starbucks wins back customers as profit rebounds", "Reuters")
        full = art("Starbucks wins back customers as profit rebounds strongly", "CNBC", summary="Sales rose 4%.")
        stories.cluster_articles([bare, full])
        self.assertGreater(stories._display_rank(full), stories._display_rank(bare))

    def test_video_is_not_the_headline(self):
        video = art("No One Wanted These Amazon Earnings", "Bloomberg", link="https://bloomberg.com/news/videos/x")
        self.assertFalse(stories._is_real_headline(video))


class FilterTests(unittest.TestCase):
    def test_recaps_detected(self):
        for t in ("NEWSLETTER: Should you invest in Anthropic?", "Opinion | An AI Halloween Market Scare",
                  "Fiverr: New Products Aren't Preventing Clients From Defecting (Downgrade)",
                  "This Week in Explainers: How Jio rewrote Indian IPO history"):
            self.assertTrue(is_roundup(t), t)
        self.assertFalse(is_roundup("Fitch downgrades France's outlook"))

    def test_crime_and_sports_filtered(self):
        self.assertTrue(is_off_topic("Suspect in killings of Oberlin professor held on $3 million bond", True))
        self.assertTrue(is_off_topic("Panthers fire defensive coordinator following 27-19 loss to the Packers", True))


if __name__ == "__main__":
    unittest.main()
