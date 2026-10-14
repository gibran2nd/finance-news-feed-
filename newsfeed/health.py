"""Per-feed health tracking and GitHub Actions reporting."""
from __future__ import annotations

import json
import os
from datetime import datetime

from .config import HEALTH_ALERT_RUNS, HEALTH_FILE


def update_feed_health(feed_stats: list[dict], now: datetime) -> tuple[dict, list[dict]]:
    """Record each source's status in HEALTH_FILE. Returns (health, sources needing attention).

    A source "fails" a run when it errors or has no articles from the past week.
    """
    try:
        old = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
    except Exception:
        old = {}
    health, alerts = {}, []
    for st in feed_stats:
        key    = f"{st['section']} | {st['label']}"
        prev   = old.get(key, {})
        failed = bool(st["error"]) or st["fresh"] == 0
        rec = {
            "section": st["section"], "label": st["label"], "url": st["url"],
            "status": st["error"] or ("empty" if failed else "ok"),
            "fresh": st["fresh"], "kept": st["kept"], "junk": st["junk"],
            "off_topic": st["off_topic"], "last_run": now.isoformat(timespec="minutes"),
            "consecutive_failures": prev.get("consecutive_failures", 0) + 1 if failed else 0,
            "last_success": (prev.get("last_success") if failed
                             else now.isoformat(timespec="minutes")),
        }
        health[key] = rec          # sources removed from FEEDS drop out automatically
        if rec["consecutive_failures"] >= HEALTH_ALERT_RUNS:
            alerts.append(rec)
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_FILE.write_text(json.dumps(health, indent=2), encoding="utf-8")
    return health, alerts


def report_feed_health(health: dict, alerts: list[dict]) -> None:
    """Print a summary; on GitHub Actions also add warnings and a job-summary table."""
    live = sum(r["status"] == "ok" for r in health.values())
    print(f"  → {live}/{len(health)} feeds live, {len(alerts)} need attention")
    for r in alerts:
        msg = (f"{r['label']} ({r['section']}) has failed {r['consecutive_failures']} runs in a row "
               f"[{r['status']}], last success: {r['last_success'] or 'never'}")
        print(f"  ⚠ {msg}")
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::warning title=Feed needs attention::{msg}")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        rows = "\n".join(
            f"| {'✅' if r['status'] == 'ok' else '❌'} | {r['section']} | {r['label']} | {r['status']} "
            f"| {r['kept']} | {r['junk'] + r['off_topic']} | {r['consecutive_failures']} |"
            for r in sorted(health.values(), key=lambda r: (r["status"] == "ok", r["section"])))
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(f"### Feed health — {live}/{len(health)} live\n\n"
                     "| | Section | Source | Status | Kept | Filtered | Failed runs |\n"
                     f"|---|---|---|---|---|---|---|\n{rows}\n")
