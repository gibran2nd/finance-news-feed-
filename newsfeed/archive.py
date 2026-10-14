"""Article archive: every article the site has seen, one JSON file per ISO week.

RSS feeds only hold their latest 10–100 items, so without this the weekly page and recaps
could only see roughly the last day. Files live in data/archive/<YYYY-Www>.json with one
article per line (small git diffs). Articles are keyed by (section, link).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .companies import find_companies
from .config import ARCHIVE_DIR, ARCHIVE_KEEP_WEEKS, FEEDS
from .fetch import add_display_fields
from .recaps import get_week_key

STORED_FIELDS = ("section", "pub", "source", "feed", "title", "summary", "link")


def _path(week_key: str):
    return ARCHIVE_DIR / f"{week_key}.json"


def _read(week_key: str) -> list[dict]:
    try:
        return json.loads(_path(week_key).read_text(encoding="utf-8"))
    except Exception:
        return []


def _write(week_key: str, records: list[dict]) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    records.sort(key=lambda r: (r["pub"], r["section"], r["link"]))
    lines = ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records)
    _path(week_key).write_text(f"[\n{lines}\n]\n", encoding="utf-8")


def update_archive(articles: list[dict], now: datetime) -> int:
    """Add newly fetched articles to their week's file. Returns how many were new."""
    by_week: dict[str, list[dict]] = {}
    for a in articles:
        by_week.setdefault(get_week_key(a["pub"]), []).append(a)
    added = 0
    for week, arts in by_week.items():
        records = _read(week)
        seen = {(r["section"], r["link"]) for r in records}
        for a in arts:
            if (a["section"], a["link"]) in seen:
                continue
            rec = {k: a[k] for k in STORED_FIELDS}
            rec["pub"] = a["pub"].isoformat(timespec="seconds")
            records.append(rec)
            seen.add((a["section"], a["link"]))
            added += 1
        _write(week, records)
    # prune old weeks
    keep = {get_week_key(now - timedelta(weeks=i)) for i in range(ARCHIVE_KEEP_WEEKS)}
    for f in ARCHIVE_DIR.glob("*.json"):
        if f.stem not in keep:
            f.unlink()
    return added


def load_archive(since: datetime, now: datetime) -> dict[str, list[dict]]:
    """Archived articles published in [since, now], as article dicts grouped by section."""
    out: dict[str, list[dict]] = {name: [] for name in FEEDS}
    day, weeks = since, []
    while day <= now + timedelta(days=7):
        if get_week_key(day) not in weeks:
            weeks.append(get_week_key(day))
        day += timedelta(days=1)
    for week in weeks:
        for rec in _read(week):
            if rec["section"] not in FEEDS:
                continue                       # section renamed/removed since archiving
            pub = datetime.fromisoformat(rec["pub"]).astimezone(timezone.utc)
            if not since <= pub <= now + timedelta(hours=1):
                continue
            art = dict(rec, pub=pub, companies=find_companies(rec["title"]))
            out[rec["section"]].append(add_display_fields(art, FEEDS[rec["section"]]["color"], now))
    return out
