"""Entry point: fetch → filter → select → render."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta

from .ai import AI
from .archive import load_archive, update_archive
from .config import DATA_FILE, FEEDS, WEEK_DATA_FILE, LOOKBACK_HOURS, MAX_PER_SECTION, MAX_PER_SECTION_WEEK, MIN_LIVE_RATIO, OUTPUT_DIR, OUTPUT_FILE, RECAPS_FILE, WEEK_FILE, WEEK_HOURS
from .export import write_page_data
from .fetch import fetch_all, parse_section
from .markets import fetch_market_snapshot
from .health import report_feed_health, update_feed_health
from .recaps import build_week_summary, load_summaries, save_summaries
from .render import build_html, build_recaps_html, build_week_html
from .stories import find_trending, importance_rank, select_stories


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    now         = datetime.now(timezone.utc)
    week_cutoff = now - timedelta(hours=WEEK_HOURS)
    main_cutoff = now - timedelta(hours=LOOKBACK_HOURS)

    print("\n Finance News Feed")
    print(f" {now.strftime('%Y-%m-%d %H:%M UTC')}  |  daily {LOOKBACK_HOURS}h / weekly {WEEK_HOURS}h\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[Fetching feeds]")
    fetched = fetch_all(now)
    print(f"  → {len(fetched)} feeds\n")

    feed_stats: list[dict] = []
    fetched_articles: list[dict] = []
    for name, config in FEEDS.items():
        print(f"[{config['icon']} {name}]")
        articles, stats = parse_section(name, config, fetched, week_cutoff, now)
        feed_stats.extend(stats)
        fetched_articles.extend(articles)
        for st in stats:
            status = st["error"] or f"{st['kept']:3} kept / {st['fresh']:3} fresh / {st['entries']:3} in feed"
            print(f"  {'✗' if st['error'] or not st['fresh'] else '✓'} {st['label']:28} {status}  ({st['secs']}s)")
        print()

    print("[🩺 Feed health]")
    health, alerts = update_feed_health(feed_stats, now)
    report_feed_health(health, alerts)
    live = sum(r["status"] == "ok" for r in health.values())
    if live < MIN_LIVE_RATIO * len(health):
        print(f"\n ✗ Only {live}/{len(health)} feeds returned articles — not publishing, "
              "the previous site stays up.\n")
        sys.exit(1)
    print()

    print("[🗄  Archive]")
    added = update_archive(fetched_articles, now)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0,
                                                               microsecond=0)
    archived = load_archive(min(week_cutoff, week_start), now)
    sections_raw_week = {n: [a for a in arts if a["pub"] >= week_cutoff] for n, arts in archived.items()}
    sections_raw_main = {n: [a for a in arts if a["pub"] >= main_cutoff] for n, arts in archived.items()}
    sections_iso_week = {n: [a for a in arts if a["pub"] >= week_start] for n, arts in archived.items()}
    print(f"  → {added} new articles archived; "
          f"{sum(map(len, sections_raw_week.values()))} in the last 7 days\n")

    print("[🔥 Selecting stories]")
    ai    = AI()
    brief: list[dict] = []

    def ai_merge(clusters):
        groups, items = ai.merge_and_brief(clusters, importance_rank(now))
        brief.extend(items)
        return groups

    top_stories, picked_main = select_stories(sections_raw_main, MAX_PER_SECTION, now,
                                              LOOKBACK_HOURS, by_coverage=False,
                                              cluster_hook=ai_merge)
    top_stories_week, picked_week = select_stories(sections_raw_week, MAX_PER_SECTION_WEEK, now,
                                                   WEEK_HOURS, by_coverage=True)
    sections_main = {name: (FEEDS[name], arts) for name, arts in picked_main.items()}
    sections_week = {name: (FEEDS[name], arts) for name, arts in picked_week.items()}
    print(f"  → top stories: {len(top_stories)} daily / {len(top_stories_week)} weekly")
    for name in FEEDS:
        print(f"  → {name}: {len(picked_main[name])} daily / {len(picked_week[name])} weekly")
    print()

    print("[📈 Market snapshot]")
    markets = fetch_market_snapshot()
    if markets:
        print("  → " + ", ".join(f"{m['label']} {m['change_pct']:+.2f}%" for m in markets) + "\n")
    else:
        print("  → unavailable (strip hidden)\n")
        if os.environ.get("GITHUB_ACTIONS"):
            print("::warning title=Market data unavailable::Yahoo and CNBC both failed; market strip hidden")

    print("[🔥 Trending Companies]")
    displayed = top_stories + [a for arts in picked_main.values() for a in arts]
    ai.condense_summaries(displayed)
    ai.save_log(now)
    if ai.enabled:
        print(f"  → AI: {len(brief)} brief items, {len(ai.log.get('merge_groups', []))} merges, "
              f"summaries {ai.log.get('summaries')}, cost ${ai.log['total_cost_usd']}")
    for err in ai.log["errors"]:
        print(f"  ⚠ AI: {err}")
        if ai.enabled and os.environ.get("GITHUB_ACTIONS"):
            print(f"::warning title=AI step::{err}")
    trending  = find_trending(sections_raw_main, displayed)
    print(f"  → {', '.join(f'{n} ({c})' for n, c in trending)}\n")

    print("[📋 Weekly Summaries]")
    summaries    = load_summaries()
    # Recap for the calendar week so far, from the archive (not just this run's feeds)
    week_hours   = max((now - week_start).total_seconds() / 3600, 1)
    recap_top, _ = select_stories(sections_iso_week, 1, now, week_hours, by_coverage=True)
    week_summary = build_week_summary(recap_top, sections_iso_week, now)
    # Update existing entry for this week or prepend a new one
    existing_idx = next((i for i, s in enumerate(summaries) if s["week"] == week_summary["week"]), None)
    if existing_idx is not None:
        summaries[existing_idx] = week_summary
    else:
        summaries.insert(0, week_summary)
    # Keep at most 52 weeks of history
    summaries = summaries[:52]
    save_summaries(summaries)
    print(f"  → {len(summaries)} weeks stored\n")

    # ── Generate pages ───────────────────────────────────────────────────────
    page = build_html(sections_main, top_stories, now, markets, trending, health, brief)
    OUTPUT_FILE.write_text(page, encoding="utf-8")

    week_page = build_week_html(sections_week, top_stories_week, now, markets)
    WEEK_FILE.write_text(week_page, encoding="utf-8")

    recaps_page = build_recaps_html(summaries, now, markets)
    RECAPS_FILE.write_text(recaps_page, encoding="utf-8")

    write_page_data(DATA_FILE, now, top_stories, picked_main,
                    markets=markets or [], brief=brief, trending=trending)
    write_page_data(WEEK_DATA_FILE, now, top_stories_week, picked_week)

    print(f" Saved → {OUTPUT_FILE}")
    print(f" Saved → {WEEK_FILE}")
    print(f" Saved → {RECAPS_FILE}")
    print(f" Saved → {DATA_FILE.name}, {WEEK_DATA_FILE.name}")
    print(f' Run:   open "{OUTPUT_FILE}"\n')
