"""Weekly recap archive (data/summaries.json)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from .config import SUMMARIES_DATA_FILE


def get_week_key(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def get_week_label(dt: datetime) -> str:
    monday = dt - timedelta(days=dt.weekday())
    friday = monday + timedelta(days=4)
    if monday.month == friday.month:
        return f"Week of {monday.strftime('%B %-d')}–{friday.strftime('%-d, %Y')}"
    return f"Week of {monday.strftime('%B %-d')} – {friday.strftime('%B %-d, %Y')}"


def load_summaries() -> list:
    if SUMMARIES_DATA_FILE.exists():
        try:
            return json.loads(SUMMARIES_DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_summaries(summaries: list) -> None:
    SUMMARIES_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUMMARIES_DATA_FILE.write_text(
        json.dumps(summaries, indent=2, default=str), encoding="utf-8"
    )


def build_week_summary(top_stories_week: list[dict], sections_raw_week: dict,
                        now: datetime) -> dict:
    """Produce a summary dict for the current ISO week."""
    section_counts = {name: len(arts) for name, arts in sections_raw_week.items()}
    bullets = [
        {
            "headline": s["title"],
            "source":   s["source"],
            "section":  s.get("section", ""),
            "link":     s["link"],
        }
        for s in top_stories_week[:8]
    ]
    return {
        "week":           get_week_key(now),
        "label":          get_week_label(now),
        "generated":      now.isoformat(),
        "bullets":        bullets,
        "section_counts": section_counts,
    }
