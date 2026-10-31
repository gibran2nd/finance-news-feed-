"""Headline wire: market-moving one-liners from FinancialJuice's public RSS feed.

The feed is a fast squawk, mostly geopolitics, with one speech split into many lines. These
stay in their own panel rather than the story sections, where they would swamp the cards.
A failed fetch just hides the panel.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from .companies import find_companies
from .fetch import fetch_feed, parse_date, strip_tags

WIRE_URL   = "https://www.financialjuice.com/feed.ashx?xy=rss"
WIRE_HOURS = 36              # long enough to keep the panel filled over a weekend
WIRE_ITEMS = 10
MAX_DATA_PRINTS = 3
MAX_PER_THEME   = 2

PREFIX_RE = re.compile(r"^FinancialJuice:\s*")
# "Chinese NBS Manufacturing PMI Actual 49.3 (Forecast 49.9, Previous 50.1)"
PRINT_RE  = re.compile(r"^(?P<name>.+?) Actual (?P<actual>\S+) \(Forecast (?P<forecast>[^,]+), "
                       r"Previous (?P<previous>[^)]+)\)$")
DROP_RE   = re.compile(r"\boption expiries\b|^week ahead\b|\bends remarks\b", re.IGNORECASE)
MARKET_RE = re.compile(r"""\b(
    oil|crude|brent|wti|opec\+?|diesel|gasoline|lng|tankers?|strait\ of\ hormuz|
    yields?|treasur(y|ies)|bonds?|refunding|fed|fomc|ecb|boe|boj|central\ bank|rate\ (cuts?|hikes?)|
    inflation|cpi|ppi|pmi|gdp|payrolls|jobless|unemployment|tariffs?|imf|
    shares|stocks?|earnings|revenue|valuation|funding|ipo|deposits|s&p|moody's|fitch
)\b""", re.IGNORECASE | re.VERBOSE)
# One running story shouldn't fill the panel
THEMES = {
    "iran":   re.compile(r"\b(iran\w*|irgc|hormuz|tehran)\b", re.IGNORECASE),
    "russia": re.compile(r"\b(russia\w*|ukrain\w*|zelenskiy|putin|lavrov)\b", re.IGNORECASE),
}


def clean_title(title: str) -> str:
    return PREFIX_RE.sub("", strip_tags(title)).strip()


def parse_print(title: str) -> dict | None:
    """Split a scheduled data release into its numbers; None for an ordinary headline."""
    m = PRINT_RE.match(title)
    if not m:
        return None
    forecast = m["forecast"].strip()
    return {"name": m["name"], "actual": m["actual"], "previous": m["previous"].strip(),
            "forecast": None if forecast == "-" else forecast}


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+\.\d+", text))


def select_wire(items: list[dict]) -> list[dict]:
    """Newest first: data prints, then one line per company and a capped share per theme."""
    prints = [i for i in items if i["print"]][:MAX_DATA_PRINTS]
    printed = {n for i in prints for n in _numbers(i["title"])}
    picked, seen_companies = list(prints), set()
    themes = {name: 0 for name in THEMES}
    for item in items:
        if len(picked) >= WIRE_ITEMS:
            break
        title = item["title"]
        if item["print"] or _numbers(title) & printed:     # a rewrite of a print we already show
            continue
        companies = set(find_companies(title))
        if not (companies or MARKET_RE.search(title)) or companies & seen_companies:
            continue
        theme = next((name for name, rx in THEMES.items() if rx.search(title)), None)
        if theme:
            if themes[theme] >= MAX_PER_THEME:
                continue
            themes[theme] += 1
        seen_companies |= companies
        picked.append(item)
    return sorted(picked, key=lambda i: i["pub"], reverse=True)


def parse_wire(feed, now: datetime) -> list[dict]:
    cutoff, items = now - timedelta(hours=WIRE_HOURS), []
    for entry in feed.entries:
        pub = parse_date(entry)
        title = clean_title(getattr(entry, "title", ""))
        if not pub or pub < cutoff or not title or DROP_RE.search(title):
            continue
        items.append({"title": title, "link": getattr(entry, "link", "") or "#", "pub": pub,
                      "print": parse_print(title)})
    return select_wire(sorted(items, key=lambda i: i["pub"], reverse=True))


def fetch_wire(now: datetime) -> list[dict]:
    feed, _ = fetch_feed(WIRE_URL)
    return parse_wire(feed, now) if feed is not None else []
