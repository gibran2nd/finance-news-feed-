"""Machine-readable copies of each page (output/data.json, output/week-data.json).

Lets the front end filter, search and track "new since last visit" without a server.
Story ids are stable across runs (hash of the link), so a browser can remember what it saw.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from .config import FEEDS, PAYWALLED_PUBLISHERS


def story_id(article: dict) -> str:
    return hashlib.sha1(article["link"].encode("utf-8")).hexdigest()[:12]


def _story(a: dict) -> dict:
    return {
        "id":        story_id(a),
        "title":     a["title"],
        "summary":   a.get("summary_short") or a["summary"],
        "link":      a["link"],
        "source":    a["source"],
        "paywalled": a["source"] in PAYWALLED_PUBLISHERS,
        "section":   a["section"],
        "published": a["pub"].isoformat(timespec="seconds"),
        "outlets":   a.get("coverage", 1),
        "companies": a.get("companies", []),
    }


def write_page_data(path: Path, generated: datetime, top: list[dict],
                    sections: dict[str, list[dict]], *, markets=None, brief=None,
                    trending=None) -> None:
    data = {
        "generated":   generated.isoformat(timespec="seconds"),
        "top_stories": [_story(a) for a in top],
        "sections":    [{"name": name, "icon": FEEDS[name]["icon"], "color": FEEDS[name]["color"],
                         "stories": [_story(a) for a in arts]} for name, arts in sections.items()],
    }
    if markets is not None:
        data["markets"] = [{k: m[k] for k in ("key", "label", "kind", "price", "change",
                                               "change_pct", "spark")} for m in markets]
    if brief is not None:
        data["brief"] = [{"headline": b["headline"], "detail": b["detail"],
                          "story": _story(b["article"])} for b in brief]
    if trending is not None:
        data["trending"] = [{"company": name, "stories_on_page": n} for name, n in trending]
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
