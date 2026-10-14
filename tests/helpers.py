"""Shared test helpers: build article dicts like parse_section produces."""
from datetime import datetime, timedelta, timezone

from newsfeed.companies import find_companies

NOW = datetime(2026, 10, 14, 13, 0, tzinfo=timezone.utc)


def art(title, source="Reuters", hours_ago=1.0, summary="", section="Stock Market & Equities",
        link=None):
    return {
        "title": title, "summary": summary, "source": source, "feed": source,
        "section": section, "pub": NOW - timedelta(hours=hours_ago),
        "link": link or f"https://example.com/{abs(hash((title, source)))}",
        "companies": find_companies(title), "color": "#fff", "is_new": False,
        "age_class": "age-fresh",
    }
