#!/usr/bin/env python3
"""
Finance News Feed
-----------------
Fetches finance/investment banking RSS feeds and generates a styled HTML dashboard.

Usage:
  python3 finance_news.py           # run manually
  open output/index.html            # view the page

Scheduling: see setup.sh (launchd, runs daily at 7 AM)
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
OUTPUT_DIR    = Path(__file__).parent / "output"
OUTPUT_FILE   = OUTPUT_DIR / "index.html"
MAX_FREE      = 8     # free articles shown per section
MAX_PREMIUM   = 6     # premium articles shown per section
LOOKBACK_HOURS = 36   # ignore articles older than this

# ── Feed Sources ───────────────────────────────────────────────────────────────
# Each source: (display_name, rss_url, is_premium)
FEEDS = {
    "Stock Market & Equities": {
        "icon":  "📈",
        "color": "#22c55e",
        "sources": [
            ("CNBC Markets",
             "https://www.cnbc.com/id/15839135/device/rss/rss.html",
             False),
            ("MarketWatch",
             "https://feeds.marketwatch.com/marketwatch/marketpulse/",
             False),
            ("Yahoo Finance",
             "https://finance.yahoo.com/news/rssindex",
             False),
            ("Google – Stocks",
             "https://news.google.com/rss/search?q=S%26P+500+Nasdaq+Dow+Jones+stock+market&hl=en-US&gl=US&ceid=US:en",
             False),
            ("WSJ Markets",
             "https://feeds.a.wsj.com/rss/RSSMarketsMain.xml",
             True),
        ],
    },
    "Macro & Economy": {
        "icon":  "🏛️",
        "color": "#3b82f6",
        "sources": [
            ("CNBC Economy",
             "https://www.cnbc.com/id/20910258/device/rss/rss.html",
             False),
            ("Google – Macro",
             "https://news.google.com/rss/search?q=Federal+Reserve+inflation+GDP+interest+rates+Treasury&hl=en-US&gl=US&ceid=US:en",
             False),
            ("Investopedia",
             "https://www.investopedia.com/feeds/rss.aspx",
             False),
            ("Financial Times",
             "https://www.ft.com/rss/home/us",
             True),
        ],
    },
    "Investment Banking & Deals": {
        "icon":  "🏦",
        "color": "#a78bfa",
        "blocklist": [
            "trump", "tariff", "tariffs", "opec", "oil price", "gas price",
            "inflation", "fed rate", "interest rate", "federal reserve",
            "ukraine", "russia", "china trade", "sanctions", "geopolit",
        ],
        "sources": [
            ("CNBC M&A",
             "https://www.cnbc.com/id/100003114/device/rss/rss.html",
             False),
            ("Google – Active Deals",
             "https://news.google.com/rss/search?q=%22acquires%22+OR+%22to+acquire%22+OR+%22merger+agreement%22+OR+%22buyout%22+OR+%22taken+private%22+billion&hl=en-US&gl=US&ceid=US:en",
             False),
            ("Google – IPO",
             "https://news.google.com/rss/search?q=%22IPO%22+OR+%22S-1%22+OR+%22going+public%22+OR+%22initial+public+offering%22+OR+%22direct+listing%22+2026&hl=en-US&gl=US&ceid=US:en",
             False),
            ("Google – PE / LBO",
             "https://news.google.com/rss/search?q=%22private+equity%22+%22acquisition%22+OR+%22buyout%22+OR+%22LBO%22+OR+%22portfolio+company%22+billion&hl=en-US&gl=US&ceid=US:en",
             False),
            ("Google – Advisors",
             "https://news.google.com/rss/search?q=%22Goldman+Sachs%22+OR+%22Morgan+Stanley%22+OR+%22JPMorgan%22+OR+%22Lazard%22+OR+%22Evercore%22+deal+OR+advises+OR+mandate&hl=en-US&gl=US&ceid=US:en",
             False),
            ("Crunchbase News",
             "https://news.crunchbase.com/feed/",
             False),
            ("WSJ Deals",
             "https://feeds.a.wsj.com/rss/WSJcomUSBusiness.xml",
             True),
        ],
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────
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


def time_ago(pub: datetime | None) -> str:
    if not pub:
        return ""
    diff = datetime.now(timezone.utc) - pub
    m = int(diff.total_seconds() / 60)
    if m < 60:   return f"{m}m ago"
    if m < 1440: return f"{m // 60}h ago"
    return f"{diff.days}d ago"


def fetch_section(config: dict, cutoff: datetime) -> list[dict]:
    try:
        import feedparser
    except ImportError:
        print("  ✗ feedparser not installed. Run: pip3 install feedparser")
        return []

    blocklist = [kw.lower() for kw in config.get("blocklist", [])]

    articles = []
    for source_name, url, is_premium in config["sources"]:
        print(f"  Fetching {source_name}...", end=" ", flush=True)
        try:
            feed = feedparser.parse(
                url,
                request_headers={"User-Agent": "Mozilla/5.0 FinanceNewsBot/1.0"},
            )
            count = 0
            for entry in feed.entries:
                pub = parse_date(entry)
                if pub and pub < cutoff:
                    continue
                title   = strip_tags(getattr(entry, "title", ""))
                summary = strip_tags(
                    getattr(entry, "summary", "") or getattr(entry, "description", "")
                )
                if len(summary) > 300:
                    summary = summary[:297] + "…"
                link = getattr(entry, "link", "#")
                if not title:
                    continue
                title_lower = title.lower()
                if any(kw in title_lower for kw in blocklist):
                    continue
                articles.append({
                    "title":   title,
                    "summary": summary,
                    "link":    link,
                    "source":  source_name,
                    "pub":     pub,
                    "premium": is_premium,
                })
                count += 1
            print(f"✓ {count}")
        except Exception as e:
            print(f"✗ {e}")
    return articles


def dedupe(articles: list[dict]) -> list[dict]:
    seen, out = [], []
    for a in articles:
        words = set(re.findall(r"\b\w{4,}\b", a["title"].lower()))
        if not words:
            continue
        is_dup = any(
            len(words & s) / max(len(words | s), 1) > 0.55
            for s in seen
        )
        if not is_dup:
            seen.append(words)
            out.append(a)
    return out


# ── HTML Generation ───────────────────────────────────────────────────────────
def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_card(article: dict, color: str) -> str:
    t   = esc(article["title"])
    s   = esc(article["summary"])
    lk  = article["link"]
    src = esc(article["source"])
    ts  = time_ago(article["pub"])
    is_premium = article.get("premium", False)

    badge_color  = "#f59e0b" if is_premium else color
    lock         = "🔒 " if is_premium else ""
    summary_html = f'<p class="card-summary">{s}</p>' if s else ""

    return f"""\
    <a class="card" href="{lk}" target="_blank" rel="noopener noreferrer">
      <div class="card-meta">
        <span class="badge" style="border-color:{badge_color};color:{badge_color}">{lock}{src}</span>
        <span class="ts">{ts}</span>
      </div>
      <p class="card-title">{t}</p>
      {summary_html}
    </a>"""


def build_html(sections: dict, generated: datetime) -> str:
    date_str = generated.strftime("%A, %B %-d, %Y")
    time_str = generated.strftime("%-I:%M %p UTC")

    sections_html = ""
    for name, (config, free_articles, premium_articles) in sections.items():
        color = config["color"]
        icon  = config["icon"]
        count = len(free_articles) + len(premium_articles)

        if free_articles:
            free_cards = "\n".join(render_card(a, color) for a in free_articles)
            free_grid  = f'<div class="grid">\n{free_cards}\n    </div>'
        else:
            free_grid  = '<p class="empty">No free articles found for this period.</p>'

        if premium_articles:
            premium_cards = "\n".join(render_card(a, color) for a in premium_articles)
            premium_block = f"""\
    <div class="tier-divider"><span>Premium Sources</span></div>
    <div class="grid">
{premium_cards}
    </div>"""
        else:
            premium_block = ""

        sections_html += f"""\
  <section class="section">
    <h2 class="section-heading" style="color:{color}">
      {icon} {name} <span class="pill">{count}</span>
    </h2>
    {free_grid}
    {premium_block}
  </section>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="3600">
  <title>Finance News — {date_str}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:       #0b0e14;
      --surface:  #111520;
      --border:   #1c2332;
      --text:     #dde4f0;
      --muted:    #5a6a85;
      --hover:    #161d2e;
    }}

    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      font-size: 15px;
      line-height: 1.55;
    }}

    /* ── Header ── */
    header {{
      position: sticky;
      top: 0;
      z-index: 20;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 18px 40px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .logo {{ font-size: 1.2rem; font-weight: 700; letter-spacing: -.02em; }}
    .logo em {{ color: #22c55e; font-style: normal; }}
    .header-meta {{ text-align: right; }}
    .header-meta .date {{ font-size: .95rem; font-weight: 600; }}
    .header-meta .updated {{ font-size: .78rem; color: var(--muted); margin-top: 2px; }}

    /* ── Layout ── */
    main {{ max-width: 1440px; margin: 0 auto; padding: 36px 28px 60px; }}

    .section {{ margin-bottom: 52px; }}

    .section-heading {{
      font-size: 1rem;
      font-weight: 700;
      letter-spacing: .02em;
      text-transform: uppercase;
      margin-bottom: 18px;
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .pill {{
      background: var(--border);
      color: var(--muted);
      font-size: .7rem;
      font-weight: 600;
      padding: 2px 9px;
      border-radius: 99px;
      letter-spacing: .04em;
    }}

    /* ── Tier Divider ── */
    .tier-divider {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin: 22px 0 14px;
      color: #f59e0b;
      font-size: .68rem;
      font-weight: 700;
      letter-spacing: .1em;
      text-transform: uppercase;
    }}
    .tier-divider::before,
    .tier-divider::after {{
      content: '';
      flex: 1;
      height: 1px;
      background: #2a2010;
    }}

    /* ── Cards ── */
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 12px;
    }}

    .card {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px 18px;
      text-decoration: none;
      color: inherit;
      transition: background .15s, border-color .15s, transform .1s;
    }}

    .card:hover {{
      background: var(--hover);
      border-color: #2a3550;
      transform: translateY(-1px);
    }}

    .card-meta {{
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    .badge {{
      font-size: .65rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .06em;
      padding: 2px 7px;
      border-radius: 4px;
      border: 1px solid;
    }}

    .ts {{ font-size: .72rem; color: var(--muted); }}

    .card-title {{
      font-size: .88rem;
      font-weight: 600;
      line-height: 1.45;
      color: var(--text);
    }}

    .card-summary {{
      font-size: .78rem;
      color: var(--muted);
      line-height: 1.5;
    }}

    .empty {{ color: var(--muted); font-style: italic; }}

    /* ── Footer ── */
    footer {{
      border-top: 1px solid var(--border);
      text-align: center;
      padding: 24px;
      color: var(--muted);
      font-size: .78rem;
    }}

    /* ── Responsive ── */
    @media (max-width: 680px) {{
      header {{ padding: 14px 20px; flex-direction: column; align-items: flex-start; gap: 6px; }}
      main {{ padding: 24px 16px 48px; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="logo">Finance <em>News</em></div>
    <div class="header-meta">
      <div class="date">{date_str}</div>
      <div class="updated">Updated {time_str} · auto-refreshes hourly</div>
    </div>
  </header>

  <main>
{sections_html}
  </main>

  <footer>
    Free: CNBC &middot; MarketWatch &middot; Yahoo Finance &middot; Investopedia &middot; Crunchbase &middot; Google News &nbsp;|&nbsp;
    Premium: WSJ &middot; Financial Times &nbsp;|&nbsp;
    Regenerates 3&times; daily
  </footer>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    now    = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=LOOKBACK_HOURS)

    print(f"\n Finance News Feed")
    print(f" {now.strftime('%Y-%m-%d %H:%M UTC')}  |  lookback {LOOKBACK_HOURS}h\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sections: dict = {}
    for name, config in FEEDS.items():
        print(f"[{config['icon']} {name}]")
        raw = fetch_section(config, cutoff)

        free_raw     = [a for a in raw if not a["premium"]]
        premium_raw  = [a for a in raw if a["premium"]]

        free_articles    = dedupe(free_raw)
        premium_articles = dedupe(premium_raw)

        free_articles.sort(
            key=lambda a: a["pub"] or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        premium_articles.sort(
            key=lambda a: a["pub"] or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        free_articles    = free_articles[:MAX_FREE]
        premium_articles = premium_articles[:MAX_PREMIUM]

        sections[name] = (config, free_articles, premium_articles)
        print(f"  → {len(free_articles)} free · {len(premium_articles)} premium\n")

    page = build_html(sections, now)
    OUTPUT_FILE.write_text(page, encoding="utf-8")

    print(f" Saved → {OUTPUT_FILE}")
    print(f" Run:   open \"{OUTPUT_FILE}\"\n")


if __name__ == "__main__":
    main()
