import unittest

from newsfeed import stories
from tests.helpers import NOW, art


def same(a, b, *others):
    """Cluster a, b (plus padding headlines so word rarity behaves like a real day)."""
    padding = [art(f"Filler story number {i} about markets and stocks", "Pad") for i in range(300)]
    arts = [a, b, *others, *padding]
    stories.cluster_articles(arts)
    return a["cluster"] == b["cluster"]


class ClusteringTests(unittest.TestCase):
    def test_same_story_different_outlets(self):
        self.assertTrue(same(art("Bank of America fined $1.2 billion over money laundering", "Reuters"),
                             art("US hits Bank of America with $1.2 billion fine over money laundering", "AP")))

    def test_same_company_same_event_different_wording(self):
        self.assertTrue(same(art("UnitedHealth raises profit forecast as turnaround gathers pace", "Reuters"),
                             art("UnitedHealth Group tops estimates, hikes profit outlook", "CNBC")))

    def test_curly_and_straight_apostrophes(self):
        self.assertTrue(same(art("Fed’s Collins sees another rate hike on the table before end of 2026", "Investing.com"),
                             art("Fed's Collins sees another rate hike on the table before end of 2026", "Reuters")))

    def test_same_company_different_stories(self):
        self.assertFalse(same(art("JPMorgan blocks outside AI agents from its website", "CNBC"),
                              art("JPMorgan posts rare profit miss as dealmaking slows", "Reuters")))

    def test_different_companies_never_merge(self):
        self.assertFalse(same(art("Citi shares drop even after fixed-income traders post higher revenue", "Bloomberg"),
                              art("JPMorgan posts surprise drop in fixed-income trading revenue", "Bloomberg")))

    def test_generic_wording_does_not_link(self):
        self.assertFalse(same(art("Why Wall Street is tokenizing stocks and everything else", "Barron's"),
                              art("Johnson & Johnson outlook misses Wall Street views; stock declines", "Yahoo Finance")))
        self.assertFalse(same(art("Spain's inflation rises at fastest pace in more than three years", "Reuters"),
                              art("China's factory-gate prices rise at fastest pace since 2022", "Bloomberg")))
        self.assertFalse(same(art("StateStreet shares fall 4% on revenue miss despite earnings beat", "Investing.com"),
                              art("Boeing stock is falling despite progress—4 reasons why", "Barron's")))


class SelectionTests(unittest.TestCase):
    def test_per_source_cap(self):
        arts = [art(f"Unique headline {i} about widget maker {i}", "Bloomberg", hours_ago=i / 10)
                for i in range(10)]
        picked = stories.pick_diverse(arts, 12)
        self.assertEqual(len(picked), stories.MAX_PER_SOURCE)

    def test_no_story_twice_on_page(self):
        raw = {"Stock Market & Equities": [
                   art("Bank of America fined $1.2 billion over money laundering", "Reuters"),
                   art("Gold steady ahead of inflation data", "WSJ")],
               "Earnings & Results": [
                   art("US hits Bank of America with $1.2 billion fine over money laundering", "AP",
                       section="Earnings & Results")]}
        top, sections = stories.select_stories(raw, 12, NOW, 36, by_coverage=False)
        titles = [a["title"] for a in top] + [a["title"] for v in sections.values() for a in v]
        self.assertEqual(sum("Bank of America" in t for t in titles), 1)

    def test_merge_clusters(self):
        a = art("Gold steady ahead of US inflation data", "WSJ")
        b = art("Gold steady as Fed official tempers rate-hike bets", "Bloomberg")
        clusters = stories.cluster_articles([a, b])
        self.assertNotEqual(a["cluster"], b["cluster"])
        stories.merge_clusters(clusters, [[a["cluster"], b["cluster"]]])
        self.assertEqual(a["cluster"], b["cluster"])
        self.assertEqual(a["coverage"], 2)


class BorrowSummaryTests(unittest.TestCase):
    def test_borrows_from_republished_wire_story(self):
        a = art("World stocks dip on AI spending concerns; Brent settles lower", "Reuters")
        b = art("World stocks dip on AI spending concerns; Brent settles lower", "Investing.com",
                summary="Global shares slipped as investors questioned AI spending.")
        stories.borrow_summaries(stories.cluster_articles([a, b]))
        self.assertEqual(a["summary_via"], "Investing.com")

    def test_does_not_borrow_from_related_story(self):
        a = art("Bitcoin climbs toward $84,000 after Fed's Williams sees no rate hike", "CoinDesk")
        b = art("Williams says Fed may not have to hike rates in 2027", "CNBC",
                summary="New York Fed President John Williams sees one more rate hike in 2026.")
        stories.borrow_summaries(stories.cluster_articles([a, b]))
        self.assertEqual(a["summary"], "")


if __name__ == "__main__":
    unittest.main()
