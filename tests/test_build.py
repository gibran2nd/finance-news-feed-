"""End-to-end: build the whole site from synthetic feeds in a temporary copy of the repo."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

RUNNER = textwrap.dedent('''
    import sys, datetime as dt, feedparser
    sys.path.insert(0, ".")
    from email.utils import format_datetime
    from newsfeed import build, config, fetch, fetch as f2

    NOW = dt.datetime(2026, 10, 14, 13, 0, tzinfo=dt.timezone.utc)
    class Frozen(dt.datetime):
        @classmethod
        def now(cls, tz=None): return NOW
    for mod in (build, fetch):
        mod.datetime = Frozen
    import newsfeed.archive as archive
    archive.datetime = dt.datetime

    STORIES = [
        "Bank of America fined $1.2 billion over money laundering",
        "US hits Bank of America with $1.2 billion fine over money laundering",
        "UnitedHealth raises profit forecast as turnaround gathers pace",
        "Goldman Sachs profit jumps as dealmaking rebounds",
        "Fed's Williams sees no need for rate hike in 2027",
        "Oil rises as Middle East tensions mount",
    ]
    def rss(url):
        n = abs(hash(url)) % 1000
        items = "".join(
            f"<item><title>{t}</title><link>https://ex.com/{n}/{i}</link>"
            f"<description>Summary {i} for {t}.</description>"
            f"<pubDate>{format_datetime(NOW - dt.timedelta(hours=i + 1))}</pubDate></item>"
            for i, t in enumerate(STORIES[n % 3:] + [f"Unique stock market story {n} shares"]))
        return f"<rss><channel><title>t</title>{items}</channel></rss>"
    fetch.fetch_feed = lambda url: (feedparser.parse(rss(url)), None)
    build.fetch_market_snapshot = lambda: None
    build.main()
''')


class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(REPO / "newsfeed", cls.tmp / "newsfeed")
        shutil.copy(REPO / "finance_news.py", cls.tmp)
        (cls.tmp / "data").mkdir()
        (cls.tmp / "run.py").write_text(RUNNER)
        env = {"PATH": "/usr/bin:/bin"}
        cls.proc = subprocess.run([sys.executable, "run.py"], cwd=cls.tmp, env=env,
                                  capture_output=True, text=True, timeout=120)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_build_succeeds(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stdout[-2000:] + self.proc.stderr[-2000:])

    def test_pages_and_data_written(self):
        out = self.tmp / "output"
        for name in ("index.html", "week.html", "recaps.html", "data.json", "week-data.json"):
            self.assertTrue((out / name).exists(), name)
        for name in ("summaries.json", "feed_health.json", "ai_last.json"):
            self.assertTrue((self.tmp / "data" / name).exists(), name)
        self.assertTrue(list((self.tmp / "data" / "archive").glob("*.json")))

    def test_no_story_twice_and_json_matches_html(self):
        html = (self.tmp / "output" / "index.html").read_text()
        titles = re.findall(r'class="card-title">(.*?)</p>', html)
        self.assertEqual(len(titles), len(set(titles)))
        data = json.loads((self.tmp / "output" / "data.json").read_text())
        n = len(data["top_stories"]) + sum(len(s["stories"]) for s in data["sections"])
        self.assertEqual(n, len(titles))
        self.assertEqual(sum("Bank of America" in t for t in titles), 1)


if __name__ == "__main__":
    unittest.main()
