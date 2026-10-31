import json
import types
import unittest

from newsfeed import ai, stories
from tests.helpers import art


def fake_response(payload, stop="end_turn"):
    return types.SimpleNamespace(
        stop_reason=stop, usage=types.SimpleNamespace(input_tokens=1000, output_tokens=200),
        content=[types.SimpleNamespace(type="text", text=json.dumps(payload))])


def make_ai(responder):
    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=responder))
    obj = ai.AI.__new__(ai.AI)
    obj.client, obj.log = client, {"model": ai.AI_MODEL, "calls": [], "errors": []}
    return obj


LONG = ("Bank of America reported third-quarter profit of $5.1 billion, hurt by a $1.2 billion "
        "settlement with regulators, while trading revenue missed analyst estimates.")


class AISafetyTests(unittest.TestCase):
    def test_internal_metadata_removed_from_brief(self):
        self.assertEqual(ai._clean_detail("Anthropic has filed for a record IPO, a story covered "
                                          "by 24 outlets, according to Fox Business."),
                         "Anthropic has filed for a record IPO.")
        self.assertEqual(ai._clean_detail("Intel fell 29% on a weak outlook."),
                         "Intel fell 29% on a weak outlook.")

    def test_ungrounded_numbers_rejected(self):
        a = art("Bank of America profit hurt by fine", summary=LONG)
        b = art("Another bank story", summary=LONG)
        bot = make_ai(lambda **kw: fake_response({"summaries": [
            {"id": 0, "summary": "Profit fell to $5.1 billion after a $1.2 billion settlement."},
            {"id": 1, "summary": "Shares jumped 999% on the news."}]}))
        bot.condense_summaries([a, b])
        self.assertIn("summary_short", a)
        self.assertNotIn("summary_short", b)
        self.assertEqual(bot.log["summaries"]["rejected_ungrounded"], 1)

    def test_invalid_and_duplicate_brief_ids_dropped(self):
        arts = [art(t) for t in ["Oil climbs as supply tightens", "Apple unveils smart home hub",
                                 "Fed's Bowman sees no urgency on rates", "Kroger to cut 3,000 jobs",
                                 "Shinhan to acquire Lotte insurer", "Gold slips after two-day rally"]]
        clusters = stories.cluster_articles(arts)
        ids = [c["id"] for c in clusters]
        brief = [{"headline": "h", "detail": "d", "story_id": i} for i in (ids[0], 99999, ids[0], ids[1])]
        bot = make_ai(lambda **kw: fake_response({"duplicate_groups": [[ids[2], 424242], [ids[3], ids[4]]],
                                                   "brief": brief}))
        groups, items = bot.merge_and_brief(clusters, lambda a: a["pub"])
        self.assertEqual(groups, [[ids[3], ids[4]]])
        self.assertEqual(len(items), 2)

    def test_failures_are_non_fatal(self):
        for responder in (lambda **kw: (_ for _ in ()).throw(ConnectionError("down")),
                          lambda **kw: fake_response({}, stop="refusal")):
            bot = make_ai(responder)
            self.assertEqual(bot.merge_and_brief(stories.cluster_articles([art("x y z")]), lambda a: a["pub"]),
                             ([], []))
            self.assertTrue(bot.log["errors"])

    def test_no_key_disables(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(ai.AI().enabled)


if __name__ == "__main__":
    unittest.main()
