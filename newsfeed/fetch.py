"""Downloading feeds and turning entries into article dicts."""
from __future__ import annotations

import re
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

from .config import FEEDS, NEW_THRESHOLD_H
from .filters import is_junk, is_off_topic, normalize_publisher


def parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    for ent, ch in [
        ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " "),
    ]:
        text = text.replace(ent, ch)
    return " ".join(text.split())


def fetch_fear_greed() -> dict | None:
    """Fetch CNN Fear & Greed Index (unofficial public endpoint)."""
    try:
        req = urllib.request.Request(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={"User-Agent": "Mozilla/5.0 FinanceNewsBot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        fg     = data.get("fear_and_greed", {})
        score  = round(float(fg.get("score", 0)))
        rating = str(fg.get("rating", "")).replace("_", " ").title()
        try:
            prev_pts = data["fear_and_greed_historical"]["data"]
            prev = round(float(prev_pts[1]["y"])) if len(prev_pts) > 1 else None
        except (KeyError, IndexError, TypeError):
            prev = None
        return {"score": score, "rating": rating, "prev": prev}
    except Exception as e:
        print(f"  Fear & Greed fetch failed: {e}")
        return None


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


USER_AGENT    = "Mozilla/5.0 (compatible; FinanceNewsFeed/2.0; +https://gibran2nd.github.io/finance-news-feed-/)"
FETCH_TIMEOUT = 15


def iter_sources(config: dict):
    """Yield (publisher, url, opts) for every source in a section config."""
    for src in config["sources"]:
        publisher, url = src[0], src[1]
        opts = src[2] if len(src) > 2 else {}
        yield publisher, url, opts


def fetch_feed(url: str):
    """Download and parse one feed. Returns (feedparser result | None, error string | None)."""
    import feedparser
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            body = resp.read()
        return feedparser.parse(body), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, type(e).__name__


def fetch_all(now: datetime) -> dict[str, dict]:
    """Fetch every feed in parallel. Returns {url: {"feed", "error", "secs"}}."""
    from concurrent.futures import ThreadPoolExecutor
    urls = sorted({url for cfg in FEEDS.values() for _, url, _ in iter_sources(cfg)})

    def timed(url):
        t = time.monotonic()
        feed, err = fetch_feed(url)
        return url, {"feed": feed, "error": err, "secs": time.monotonic() - t}

    with ThreadPoolExecutor(max_workers=12) as pool:
        return dict(pool.map(timed, urls))


def parse_section(name: str, config: dict, fetched: dict, cutoff: datetime,
                  now: datetime) -> tuple[list[dict], list[dict]]:
    """Turn fetched feeds into article dicts. Returns (articles, per-source stats)."""
    blocklist  = [kw.lower() for kw in config.get("blocklist", [])]
    new_cutoff = now - timedelta(hours=NEW_THRESHOLD_H)
    max_future = now + timedelta(hours=1)
    color      = config["color"]

    articles, stats = [], []
    for publisher, url, opts in iter_sources(config):
        label  = opts.get("label", publisher)
        result = fetched[url]
        feed   = result["feed"]
        stat   = {"section": name, "label": label, "url": url, "error": result["error"],
                  "entries": 0, "fresh": 0, "kept": 0, "junk": 0, "off_topic": 0, "secs": round(result["secs"], 1)}
        stats.append(stat)
        if feed is None:
            continue
        stat["entries"] = len(feed.entries)
        for entry in feed.entries:
            pub = parse_date(entry)
            if pub and pub > max_future:      # bad/mis-parsed dates (seen on Finextra)
                continue
            if not pub or pub < cutoff:
                continue
            stat["fresh"] += 1
            title   = strip_tags(getattr(entry, "title", ""))
            summary = strip_tags(
                getattr(entry, "summary", "") or getattr(entry, "description", "")
            )
            if len(summary) > 300:
                summary = summary[:297] + "…"
            link = getattr(entry, "link", "") or "#"
            if not title:
                continue
            art_publisher = publisher
            if publisher == "Google News":
                # Google appends " - Publisher" to titles; its summary just repeats the title
                src_title = (entry.get("source") or {}).get("title", "")
                if src_title and title.endswith(" - " + src_title):
                    title = title[: -len(src_title) - 3].rstrip()
                art_publisher = normalize_publisher(src_title) if src_title else publisher
                summary = ""
            if summary and _norm(summary).startswith(_norm(title)[:60]):
                summary = ""
            if is_junk(title, art_publisher):
                stat["junk"] += 1
                continue
            if is_off_topic(title, opts.get("filter", False)):
                stat["off_topic"] += 1
                continue
            if any(kw in title.lower() for kw in blocklist):
                continue
            age_h     = (now - pub).total_seconds() / 3600
            age_class = "age-fresh" if age_h < 2 else "age-recent" if age_h < 12 else "age-old"
            articles.append({
                "title":     title,
                "summary":   summary,
                "link":      link,
                "source":    art_publisher,
                "feed":      label,
                "section":   name,
                "pub":       pub,
                "is_new":    pub >= new_cutoff,
                "color":     color,
                "age_class": age_class,
            })
            stat["kept"] += 1
    return articles, stats
