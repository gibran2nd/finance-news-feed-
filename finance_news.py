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
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
OUTPUT_DIR       = Path(__file__).parent / "output"
OUTPUT_FILE      = OUTPUT_DIR / "index.html"
MAX_PER_SECTION  = 12
MAX_TOP_STORIES  = 6
LOOKBACK_HOURS   = 36
NEW_THRESHOLD_H  = 2

# ── Premium Sites ─────────────────────────────────────────────────────────────
PREMIUM_SITES = [
    {"name": "Wall Street Journal", "short": "WSJ", "url": "https://www.wsj.com",        "desc": "Markets, deals & economy"},
    {"name": "Financial Times",     "short": "FT",  "url": "https://www.ft.com",          "desc": "Global financial news"},
    {"name": "Bloomberg",           "short": "BBG", "url": "https://www.bloomberg.com",   "desc": "Markets data & analysis"},
    {"name": "PitchBook",           "short": "PB",  "url": "https://pitchbook.com",       "desc": "PE, VC & M&A data"},
    {"name": "The Economist",       "short": "ECO", "url": "https://www.economist.com",   "desc": "Global business & macro"},
]

# ── TradingView Ticker (plain string — kept outside f-string to avoid brace escaping) ──
TICKER_HTML = """\
  <div class="ticker-wrap">
    <div class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js" async>
      {
        "symbols": [
          {"proName": "FOREXCOM:SPXUSD",  "title": "S&P 500"},
          {"proName": "FOREXCOM:NSXUSD",  "title": "Nasdaq 100"},
          {"proName": "DJ:DJI",           "title": "Dow Jones"},
          {"proName": "TVC:US10Y",        "title": "10Y Treasury"},
          {"proName": "COINBASE:BTCUSD",  "title": "Bitcoin"},
          {"proName": "TVC:GOLD",         "title": "Gold"},
          {"proName": "TVC:USOIL",        "title": "Crude Oil"}
        ],
        "showSymbolLogo": false,
        "isTransparent": true,
        "displayMode": "adaptive",
        "colorTheme": "dark",
        "locale": "en"
      }
      </script>
    </div>
  </div>"""

# ── Internship Resources (static — The Trackr is a JS app, can't be scraped) ─
INTERNSHIP_RESOURCES = [
    {
        "firm":     "The Trackr — Full Deadline Calendar",
        "role":     "Summer 2027 Internships",
        "deadline": "View all upcoming deadlines →",
        "url":      "https://app.the-trackr.com/na-finance-2027/summer-internships",
        "featured": True,
    },
    {
        "firm":     "Wall Street Oasis",
        "role":     "IB / PE / HF Recruiting Hub",
        "deadline": "Guides, timelines & firm reviews",
        "url":      "https://www.wallstreetoasis.com/finance-jobs",
        "featured": False,
    },
    {
        "firm":     "Mergers & Inquisitions",
        "role":     "Breaking Into Finance",
        "deadline": "Recruiting guides & career resources",
        "url":      "https://mergersandinquisitions.com",
        "featured": False,
    },
    {
        "firm":     "LinkedIn Finance Internships",
        "role":     "Summer 2027 Postings",
        "deadline": "Browse open applications",
        "url":      "https://www.linkedin.com/jobs/finance-internships/",
        "featured": False,
    },
    {
        "firm":     "Handshake",
        "role":     "Campus Finance Recruiting",
        "deadline": "College-focused internship board",
        "url":      "https://joinhandshake.com/job-collections/finance-internships/",
        "featured": False,
    },
]

# ── Feed Sources ───────────────────────────────────────────────────────────────
FEEDS = {
    "Stock Market & Equities": {
        "icon":  "📈",
        "color": "#22c55e",
        "sources": [
            ("CNBC Markets",
             "https://www.cnbc.com/id/15839135/device/rss/rss.html"),
            ("MarketWatch",
             "https://feeds.marketwatch.com/marketwatch/marketpulse/"),
            ("Yahoo Finance",
             "https://finance.yahoo.com/news/rssindex"),
            ("Google – Stocks",
             "https://news.google.com/rss/search?q=S%26P+500+Nasdaq+Dow+Jones+stock+market&hl=en-US&gl=US&ceid=US:en"),
        ],
    },
    "Macro & Economy": {
        "icon":  "🏛️",
        "color": "#3b82f6",
        "sources": [
            ("CNBC Economy",
             "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
            ("Google – Fed & Rates",
             "https://news.google.com/rss/search?q=Federal+Reserve+interest+rates+economy&hl=en-US&gl=US&ceid=US:en"),
            ("Google – Inflation & GDP",
             "https://news.google.com/rss/search?q=inflation+GDP+unemployment+recession+consumer+spending&hl=en-US&gl=US&ceid=US:en"),
            ("Google – AP Economics",
             "https://news.google.com/rss/search?q=economy+source%3AAssociated+Press&hl=en-US&gl=US&ceid=US:en"),
            ("Google – Reuters Economy",
             "https://news.google.com/rss/search?q=economy+Federal+Reserve+source%3AReuters&hl=en-US&gl=US&ceid=US:en"),
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
             "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
            ("Google – Active Deals",
             "https://news.google.com/rss/search?q=%22acquires%22+OR+%22to+acquire%22+OR+%22merger+agreement%22+OR+%22buyout%22+OR+%22taken+private%22+billion&hl=en-US&gl=US&ceid=US:en"),
            ("Google – IPO",
             "https://news.google.com/rss/search?q=%22IPO%22+OR+%22S-1%22+OR+%22going+public%22+OR+%22initial+public+offering%22+OR+%22direct+listing%22+2026&hl=en-US&gl=US&ceid=US:en"),
            ("Google – PE / LBO",
             "https://news.google.com/rss/search?q=%22private+equity%22+%22acquisition%22+OR+%22buyout%22+OR+%22LBO%22+OR+%22portfolio+company%22+billion&hl=en-US&gl=US&ceid=US:en"),
            ("Google – Advisors",
             "https://news.google.com/rss/search?q=%22Goldman+Sachs%22+OR+%22Morgan+Stanley%22+OR+%22JPMorgan%22+OR+%22Lazard%22+OR+%22Evercore%22+deal+OR+advises+OR+mandate&hl=en-US&gl=US&ceid=US:en"),
            ("Crunchbase News",
             "https://news.crunchbase.com/feed/"),
        ],
    },
    "Real Estate & REITs": {
        "icon":  "🏢",
        "color": "#06b6d4",
        "sources": [
            ("Google – REITs",
             "https://news.google.com/rss/search?q=REIT+%22real+estate+investment+trust%22+dividend+%22commercial+real+estate%22&hl=en-US&gl=US&ceid=US:en"),
            ("Google – CRE",
             "https://news.google.com/rss/search?q=%22commercial+real+estate%22+office+retail+multifamily+industrial+%22cap+rate%22&hl=en-US&gl=US&ceid=US:en"),
            ("Google – Housing Market",
             "https://news.google.com/rss/search?q=housing+market+%22home+prices%22+%22mortgage+rate%22+%22existing+home+sales%22+2026&hl=en-US&gl=US&ceid=US:en"),
            ("Google – Real Estate Deals",
             "https://news.google.com/rss/search?q=%22real+estate%22+%22acquisition%22+OR+%22development%22+OR+%22leasing%22+billion+2026&hl=en-US&gl=US&ceid=US:en"),
        ],
    },
    "Earnings & Results": {
        "icon":  "📊",
        "color": "#ec4899",
        "sources": [
            ("Google – Earnings Beats",
             "https://news.google.com/rss/search?q=earnings+%22beats+estimates%22+OR+%22tops+expectations%22+OR+%22earnings+per+share%22&hl=en-US&gl=US&ceid=US:en"),
            ("Google – Earnings Reports",
             "https://news.google.com/rss/search?q=%22quarterly+results%22+OR+%22earnings+report%22+OR+%22earnings+call%22+revenue+profit+2026&hl=en-US&gl=US&ceid=US:en"),
            ("Google – Guidance",
             "https://news.google.com/rss/search?q=%22raised+guidance%22+OR+%22lowered+guidance%22+OR+%22full+year+outlook%22+OR+%22earnings+forecast%22&hl=en-US&gl=US&ceid=US:en"),
            ("Yahoo Finance",
             "https://finance.yahoo.com/news/rssindex"),
        ],
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


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


def fetch_section(config: dict, cutoff: datetime, now: datetime, color: str) -> list[dict]:
    try:
        import feedparser
    except ImportError:
        print("  ✗ feedparser not installed. Run: pip3 install feedparser")
        return []

    blocklist  = [kw.lower() for kw in config.get("blocklist", [])]
    new_cutoff = now - timedelta(hours=NEW_THRESHOLD_H)

    articles = []
    for source_name, url in config["sources"]:
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
                if any(kw in title.lower() for kw in blocklist):
                    continue
                articles.append({
                    "title":   title,
                    "summary": summary,
                    "link":    link,
                    "source":  source_name,
                    "pub":     pub,
                    "is_new":  pub is not None and pub >= new_cutoff,
                    "color":   color,
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
        if not any(len(words & s) / max(len(words | s), 1) > 0.55 for s in seen):
            seen.append(words)
            out.append(a)
    return out


def find_top_stories(sections_raw: dict[str, list[dict]]) -> list[dict]:
    """Promote articles covered by 2+ different sources to Top Stories."""
    all_articles: list[dict] = []
    for arts in sections_raw.values():
        all_articles.extend(arts)

    clusters: list[dict] = []
    for a in all_articles:
        words = set(re.findall(r"\b\w{4,}\b", a["title"].lower()))
        if not words:
            continue
        matched = False
        for cluster in clusters:
            sim = len(words & cluster["words"]) / max(len(words | cluster["words"]), 1)
            if sim > 0.45:
                cluster["sources"].add(a["source"])
                if a["pub"] and (not cluster["article"]["pub"] or a["pub"] > cluster["article"]["pub"]):
                    cluster["article"] = a
                matched = True
                break
        if not matched:
            clusters.append({"article": a, "words": words, "sources": {a["source"]}})

    top = [c["article"] for c in clusters if len(c["sources"]) >= 2]
    top.sort(key=lambda a: a["pub"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return top[:MAX_TOP_STORIES]


# ── HTML Generation ───────────────────────────────────────────────────────────
def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_card(article: dict, color: str | None = None) -> str:
    t        = esc(article["title"])
    s        = esc(article["summary"])
    lk       = article["link"]
    src      = esc(article["source"])
    ts       = time_ago(article["pub"])
    c        = color or article.get("color", "#22c55e")
    new_badge = '<span class="new-badge">NEW</span>' if article.get("is_new") else ""
    summary_html = f'<p class="card-summary">{s}</p>' if s else ""
    return f"""\
    <a class="card" href="{lk}" target="_blank" rel="noopener noreferrer">
      <div class="card-meta">
        <span class="badge" style="border-color:{c};color:{c}">{src}</span>
        <span class="ts">{new_badge}{ts}</span>
      </div>
      <p class="card-title">{t}</p>
      {summary_html}
    </a>"""


def render_careers_section() -> str:
    cards = ""
    for item in INTERNSHIP_RESOURCES:
        featured_cls = " career-featured" if item["featured"] else ""
        cards += f"""\
    <a class="career-card{featured_cls}" href="{item['url']}" target="_blank" rel="noopener noreferrer">
      <div class="career-firm">{esc(item['firm'])}</div>
      <div class="career-role">{esc(item['role'])}</div>
      <div class="career-deadline">{esc(item['deadline'])}</div>
    </a>"""
    return cards


def render_premium_sites() -> str:
    cards = ""
    for site in PREMIUM_SITES:
        cards += f"""\
    <a class="premium-site-card" href="{site['url']}" target="_blank" rel="noopener noreferrer">
      <span class="premium-short">{esc(site['short'])}</span>
      <div class="premium-info">
        <span class="premium-name">{esc(site['name'])}</span>
        <span class="premium-desc">{esc(site['desc'])}</span>
      </div>
      <span class="premium-arrow">↗</span>
    </a>"""
    return cards


def build_html(sections: dict, top_stories: list[dict], generated: datetime) -> str:
    date_str  = generated.strftime("%A, %B %-d, %Y")
    time_str  = generated.strftime("%-I:%M %p UTC")
    total     = sum(len(arts) for _, arts in sections.values()) + len(top_stories)

    # ── Section nav links ────────────────────────────────────────────────────
    nav_items = f'<a class="nav-item" href="#top-stories">🔥 Top Stories</a>\n'
    for name, (config, _) in sections.items():
        sid = slugify(name)
        nav_items += f'    <a class="nav-item" href="#{sid}">{config["icon"]} {name.split(" & ")[0].split(" ")[0]}</a>\n'
    nav_items += '    <a class="nav-item" href="#careers-recruiting">💼 Careers</a>\n'
    nav_items += '    <a class="nav-item" href="#premium">🔒 Premium</a>\n'

    # ── Top Stories section ──────────────────────────────────────────────────
    if top_stories:
        top_cards = "\n".join(render_card(a) for a in top_stories)
        top_section = f"""\
  <section class="section" id="top-stories" data-section>
    <h2 class="section-heading" style="color:#f97316">
      🔥 Top Stories <span class="pill">{len(top_stories)}</span>
    </h2>
    <div class="grid">
{top_cards}
    </div>
  </section>
"""
    else:
        top_section = ""

    # ── News sections ────────────────────────────────────────────────────────
    sections_html = top_section
    for name, (config, articles) in sections.items():
        color = config["color"]
        icon  = config["icon"]
        sid   = slugify(name)
        count = len(articles)
        if articles:
            cards = "\n".join(render_card(a, color) for a in articles)
        else:
            cards = '<p class="empty">No articles found for this period.</p>'
        sections_html += f"""\
  <section class="section" id="{sid}" data-section>
    <h2 class="section-heading" style="color:{color}">
      {icon} {name} <span class="pill">{count}</span>
    </h2>
    <div class="grid">
{cards}
    </div>
  </section>
"""

    premium_html = render_premium_sites()

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="3600">
  <meta name="description" content="Live finance news — markets, deals, macro, real estate, earnings & careers.">
  <meta property="og:title" content="Finance News Feed">
  <meta property="og:description" content="Live finance news — markets, deals, macro, real estate, earnings & careers.">
  <title>Finance News — {date_str} ({total} articles)</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📈</text></svg>">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    /* ── Themes ── */
    html[data-theme="dark"] {{
      --bg:      #0b0e14;
      --surface: #111520;
      --border:  #1c2332;
      --text:    #dde4f0;
      --muted:   #5a6a85;
      --hover:   #161d2e;
      --gold:    #f59e0b;
      --header-bg: #111520;
    }}
    html[data-theme="light"] {{
      --bg:      #f4f6f9;
      --surface: #ffffff;
      --border:  #dde3ed;
      --text:    #1a2236;
      --muted:   #6b7a96;
      --hover:   #eef1f7;
      --gold:    #d97706;
      --header-bg: #ffffff;
    }}

    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      font-size: 15px;
      line-height: 1.55;
      transition: background .2s, color .2s;
    }}

    /* ── Ticker ── */
    .ticker-wrap {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
    }}

    /* ── Header ── */
    header {{
      position: sticky;
      top: 0;
      z-index: 20;
      background: var(--header-bg);
      border-bottom: 1px solid var(--border);
      box-shadow: 0 1px 8px rgba(0,0,0,.15);
    }}
    .header-row {{
      padding: 12px 40px;
      display: flex;
      align-items: center;
      gap: 16px;
    }}
    .logo {{ font-size: 1.2rem; font-weight: 700; letter-spacing: -.02em; white-space: nowrap; }}
    .logo em {{ color: #22c55e; font-style: normal; }}

    /* Search */
    .search-wrap {{ flex: 1; max-width: 380px; }}
    #search {{
      width: 100%;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 7px 14px;
      color: var(--text);
      font-size: .85rem;
      outline: none;
      transition: border-color .15s;
    }}
    #search::placeholder {{ color: var(--muted); }}
    #search:focus {{ border-color: #3b82f6; }}

    /* Theme toggle */
    #theme-btn {{
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 6px 10px;
      font-size: 1rem;
      cursor: pointer;
      color: var(--text);
      flex-shrink: 0;
      transition: background .15s;
    }}
    #theme-btn:hover {{ background: var(--hover); }}

    .header-meta {{ text-align: right; white-space: nowrap; margin-left: auto; }}
    .header-meta .date {{ font-size: .9rem; font-weight: 600; }}
    .header-meta .updated {{ font-size: .75rem; color: var(--muted); margin-top: 2px; }}

    /* ── Section Nav ── */
    .section-nav {{
      display: flex;
      gap: 4px;
      padding: 8px 40px;
      border-top: 1px solid var(--border);
      overflow-x: auto;
      scrollbar-width: none;
    }}
    .section-nav::-webkit-scrollbar {{ display: none; }}
    .nav-item {{
      white-space: nowrap;
      font-size: .72rem;
      font-weight: 600;
      letter-spacing: .03em;
      padding: 4px 12px;
      border-radius: 99px;
      border: 1px solid var(--border);
      color: var(--muted);
      text-decoration: none;
      transition: background .15s, color .15s, border-color .15s;
      flex-shrink: 0;
    }}
    .nav-item:hover {{
      background: var(--hover);
      color: var(--text);
      border-color: #3b82f6;
    }}

    /* ── Layout ── */
    main {{ max-width: 1440px; margin: 0 auto; padding: 36px 28px 80px; }}

    .section {{ margin-bottom: 52px; scroll-margin-top: 120px; }}

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
    .card-meta {{ display: flex; align-items: center; justify-content: space-between; }}
    .badge {{
      font-size: .65rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .06em;
      padding: 2px 7px;
      border-radius: 4px;
      border: 1px solid;
    }}
    .ts {{ font-size: .72rem; color: var(--muted); display: flex; align-items: center; gap: 5px; }}
    .new-badge {{
      font-size: .6rem;
      font-weight: 800;
      letter-spacing: .08em;
      color: #fff;
      background: #ef4444;
      border-radius: 3px;
      padding: 1px 5px;
    }}
    .card-title {{ font-size: .88rem; font-weight: 600; line-height: 1.45; }}
    .card-summary {{ font-size: .78rem; color: var(--muted); line-height: 1.5; }}
    .empty {{ color: var(--muted); font-style: italic; }}

    /* ── Career Cards ── */
    .career-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 12px;
    }}
    .career-card {{
      display: flex;
      flex-direction: column;
      gap: 5px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px 18px;
      text-decoration: none;
      color: inherit;
      transition: background .15s, border-color .15s, transform .1s;
    }}
    .career-card:hover {{
      background: var(--hover);
      border-color: #f97316;
      transform: translateY(-1px);
    }}
    .career-card.career-featured {{
      grid-column: 1 / -1;
      border-color: #f97316;
      background: #120d06;
      flex-direction: row;
      align-items: center;
      gap: 20px;
      padding: 20px 24px;
    }}
    .career-card.career-featured:hover {{
      background: #1a1209;
    }}
    .career-firm {{
      font-size: .82rem;
      font-weight: 700;
      color: #f97316;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .career-featured .career-firm {{ font-size: 1rem; }}
    .career-role {{
      font-size: .88rem;
      font-weight: 600;
      color: var(--text);
    }}
    .career-featured .career-role {{ font-size: 1rem; }}
    .career-deadline {{
      font-size: .78rem;
      color: var(--muted);
    }}
    .career-featured .career-deadline {{
      margin-left: auto;
      font-size: .88rem;
      color: #f97316;
      white-space: nowrap;
    }}

    /* ── Premium Sites ── */
    .premium-section {{ margin-bottom: 52px; scroll-margin-top: 120px; }}
    .premium-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 10px;
    }}
    .premium-site-card {{
      display: flex;
      align-items: center;
      gap: 14px;
      background: var(--surface);
      border: 1px solid #2a2010;
      border-radius: 10px;
      padding: 14px 16px;
      text-decoration: none;
      color: inherit;
      transition: background .15s, border-color .15s, transform .1s;
    }}
    .premium-site-card:hover {{ background: #16120a; border-color: var(--gold); transform: translateY(-1px); }}
    .premium-short {{
      font-size: .75rem;
      font-weight: 800;
      letter-spacing: .06em;
      color: var(--gold);
      background: #1f1608;
      border: 1px solid #2a2010;
      border-radius: 6px;
      padding: 4px 8px;
      white-space: nowrap;
      flex-shrink: 0;
    }}
    .premium-info {{ display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }}
    .premium-name {{ font-size: .82rem; font-weight: 600; }}
    .premium-desc {{ font-size: .72rem; color: var(--muted); }}
    .premium-arrow {{ font-size: .9rem; color: var(--muted); flex-shrink: 0; }}

    /* ── Back to top ── */
    #back-top {{
      position: fixed;
      bottom: 28px;
      right: 28px;
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: #3b82f6;
      color: #fff;
      border: none;
      font-size: 1.1rem;
      cursor: pointer;
      display: none;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 14px rgba(59,130,246,.4);
      transition: opacity .2s, transform .2s;
      z-index: 99;
    }}
    #back-top:hover {{ transform: translateY(-2px); }}

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
      .header-row {{ padding: 10px 16px; flex-wrap: wrap; }}
      .search-wrap {{ order: 3; max-width: 100%; width: 100%; }}
      .section-nav {{ padding: 8px 16px; }}
      main {{ padding: 24px 16px 80px; }}
      .grid {{ grid-template-columns: 1fr; }}
      .premium-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>

{TICKER_HTML}

  <header>
    <div class="header-row">
      <div class="logo">Finance <em>News</em></div>
      <div class="search-wrap">
        <input id="search" type="search" placeholder="Search all articles…" autocomplete="off">
      </div>
      <button id="theme-btn" title="Toggle light/dark mode">☀️</button>
      <div class="header-meta">
        <div class="date">{date_str}</div>
        <div class="updated">Updated {time_str} · auto-refreshes hourly</div>
      </div>
    </div>
    <nav class="section-nav">
    {nav_items}
    </nav>
  </header>

  <main>
{sections_html}
  <section class="section" id="careers-recruiting" data-section>
    <h2 class="section-heading" style="color:#f97316">
      💼 Careers &amp; Recruiting <span class="pill">{len(INTERNSHIP_RESOURCES)}</span>
    </h2>
    <div class="career-grid">
{render_careers_section()}
    </div>
  </section>

  <section class="premium-section" id="premium">
    <h2 class="section-heading" style="color:var(--gold)">
      🔒 Premium Sources <span class="pill">{len(PREMIUM_SITES)}</span>
    </h2>
    <div class="premium-grid">
{premium_html}
    </div>
  </section>
  </main>

  <footer>
    Free: CNBC &middot; MarketWatch &middot; Yahoo Finance &middot; WSO &middot; M&amp;I &middot; Crunchbase &middot; Google News &nbsp;|&nbsp;
    Premium: WSJ &middot; FT &middot; Bloomberg &middot; PitchBook &middot; The Economist &nbsp;|&nbsp;
    Regenerates 3&times; daily
  </footer>

  <button id="back-top" title="Back to top">↑</button>

  <script>
    // ── Search ──────────────────────────────────────────────────────────────
    const searchInput = document.getElementById('search');
    searchInput.addEventListener('input', () => {{
      const q = searchInput.value.toLowerCase().trim();
      let visible = 0;
      document.querySelectorAll('[data-section]').forEach(section => {{
        let sectionVisible = 0;
        section.querySelectorAll('.card').forEach(card => {{
          const match = !q || card.textContent.toLowerCase().includes(q);
          card.style.display = match ? '' : 'none';
          if (match) {{ sectionVisible++; visible++; }}
        }});
        section.style.display = sectionVisible === 0 && q ? 'none' : '';
      }});
      document.title = q
        ? `Finance News — ${{visible}} results`
        : `Finance News — {date_str} ({total} articles)`;
    }});

    // ── Light / Dark Mode ────────────────────────────────────────────────────
    const html      = document.documentElement;
    const themeBtn  = document.getElementById('theme-btn');
    const saved     = localStorage.getItem('theme') || 'dark';
    html.setAttribute('data-theme', saved);
    themeBtn.textContent = saved === 'dark' ? '☀️' : '🌙';

    themeBtn.addEventListener('click', () => {{
      const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      html.setAttribute('data-theme', next);
      themeBtn.textContent = next === 'dark' ? '☀️' : '🌙';
      localStorage.setItem('theme', next);
    }});

    // ── Back to Top ──────────────────────────────────────────────────────────
    const backTop = document.getElementById('back-top');
    window.addEventListener('scroll', () => {{
      backTop.style.display = window.scrollY > 400 ? 'flex' : 'none';
    }}, {{ passive: true }});
    backTop.addEventListener('click', () => window.scrollTo({{ top: 0, behavior: 'smooth' }}));
  </script>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    now    = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=LOOKBACK_HOURS)

    print(f"\n Finance News Feed")
    print(f" {now.strftime('%Y-%m-%d %H:%M UTC')}  |  lookback {LOOKBACK_HOURS}h\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sections:     dict = {}
    sections_raw: dict = {}

    for name, config in FEEDS.items():
        print(f"[{config['icon']} {name}]")
        raw      = fetch_section(config, cutoff, now, config["color"])
        sections_raw[name] = raw
        articles = dedupe(raw)
        articles.sort(
            key=lambda a: a["pub"] or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        articles = articles[:MAX_PER_SECTION]
        sections[name] = (config, articles)
        print(f"  → {len(articles)} unique articles\n")

    print("[🔥 Top Stories]")
    top_stories = find_top_stories(sections_raw)
    print(f"  → {len(top_stories)} top stories\n")

    page = build_html(sections, top_stories, now)
    OUTPUT_FILE.write_text(page, encoding="utf-8")

    print(f" Saved → {OUTPUT_FILE}")
    print(f" Run:   open \"{OUTPUT_FILE}\"\n")


if __name__ == "__main__":
    main()
