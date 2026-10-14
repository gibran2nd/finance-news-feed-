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

import os
import re
import sys
import json
import urllib.parse
import urllib.error
import urllib.request
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
OUTPUT_DIR           = Path(__file__).parent / "output"
OUTPUT_FILE          = OUTPUT_DIR / "index.html"
WEEK_FILE            = OUTPUT_DIR / "week.html"
RECAPS_FILE          = OUTPUT_DIR / "recaps.html"
SUMMARIES_DATA_FILE  = Path(__file__).parent / "data" / "summaries.json"
HEALTH_FILE          = Path(__file__).parent / "data" / "feed_health.json"
HEALTH_ALERT_RUNS    = 3      # warn after this many consecutive empty/failed runs (~1 day)
MIN_LIVE_RATIO       = 0.5    # below this share of live feeds, don't publish (keep old site)
MAX_PER_SECTION      = 12
MAX_PER_SECTION_WEEK = 20
MAX_TOP_STORIES      = 6
MAX_PER_SOURCE       = 3      # per publisher, per section
LOOKBACK_HOURS       = 36
WEEK_HOURS           = 168
NEW_THRESHOLD_H      = 2

# Set to a non-empty string to show a pinned announcement banner on the site.
# Example: "Recruiting season is OPEN — check deadlines in the Careers section below!"
ANNOUNCEMENT = ""

# ── Premium Sites ─────────────────────────────────────────────────────────────
PREMIUM_SITES = [
    {"name": "Wall Street Journal", "short": "WSJ", "url": "https://www.wsj.com",        "desc": "Markets, deals & economy"},
    {"name": "Financial Times",     "short": "FT",  "url": "https://www.ft.com",          "desc": "Global financial news"},
    {"name": "Bloomberg",           "short": "BBG", "url": "https://www.bloomberg.com",   "desc": "Markets data & analysis"},
    {"name": "PitchBook",           "short": "PB",  "url": "https://pitchbook.com",       "desc": "PE, VC & M&A data"},
    {"name": "The Economist",       "short": "ECO", "url": "https://www.economist.com",   "desc": "Global business & macro"},
]

# ── TradingView Ticker (plain string — outside f-string to avoid brace escaping) ──
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

# ── TradingView Economic Calendar (plain string — outside f-string) ──────────
CALENDAR_HTML = """\
  <div class="tradingview-widget-container" style="min-height:450px">
    <div class="tradingview-widget-container__widget"></div>
    <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-events.js" async>
    {
      "colorTheme": "dark",
      "isTransparent": true,
      "width": "100%",
      "height": "450",
      "locale": "en",
      "importanceFilter": "-1,0,1,2,3",
      "countryFilter": "us"
    }
    </script>
  </div>"""

# ── Internship Resources ───────────────────────────────────────────────────────
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
def gnews(query: str) -> str:
    """Google News search feed. Use `when:Nd` in the query to keep results fresh."""
    return ("https://news.google.com/rss/search?q=" + urllib.parse.quote_plus(query)
            + "&hl=en-US&gl=US&ceid=US:en")


# Restricts a Google News search to major outlets (keeps out SEO/content-farm sites)
TOP_OUTLETS = ("(site:reuters.com OR site:apnews.com OR site:bloomberg.com OR site:wsj.com"
               " OR site:ft.com OR site:cnbc.com OR site:barrons.com OR site:axios.com"
               " OR site:nytimes.com OR site:marketwatch.com)")

CNBC = "https://www.cnbc.com/id/{}/device/rss/rss.html"
DJ   = "https://feeds.content.dowjones.io/public/rss/{}"

# Each source is (publisher, url) or (publisher, url, opts).
#   opts["filter"] → general-interest feed; keep only finance-relevant stories
#   opts["label"]  → name used in logs / feed health (defaults to publisher)
# Google News items show their real publisher (Reuters, Barron's…), not "Google News".
FEEDS = {
    "Stock Market & Equities": {
        "icon":  "📈",
        "color": "#22c55e",
        "sources": [
            ("WSJ",           DJ.format("RSSMarketsMain")),
            ("Bloomberg",     "https://feeds.bloomberg.com/markets/news.rss", {"filter": True}),
            ("FT",            "https://www.ft.com/markets?format=rss"),
            ("MarketWatch",   DJ.format("mw_topstories"), {"filter": True}),
            ("CNBC",          CNBC.format(10000664)),
            ("Google News",   gnews('(stocks OR "Wall Street" OR shares OR S&P) (site:reuters.com OR site:apnews.com OR site:barrons.com) when:1d'),
                              {"label": "Reuters/AP/Barron's markets search", "filter": True}),
        ],
    },
    "Macro & Economy": {
        "icon":  "🏛️",
        "color": "#3b82f6",
        "sources": [
            ("WSJ",               DJ.format("socialeconomyfeed")),
            ("Bloomberg",         "https://feeds.bloomberg.com/economics/news.rss"),
            ("FT",                "https://www.ft.com/global-economy?format=rss"),
            ("CNBC",              CNBC.format(20910258)),
            ("NYT",               "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml"),
            ("Investing.com",     "https://www.investing.com/rss/news_14.rss", {"filter": True}),
            ("Federal Reserve",   "https://www.federalreserve.gov/feeds/press_all.xml"),
            ("Project Syndicate", "https://www.project-syndicate.org/rss", {"filter": True}),
            ("Google News",       gnews(f'("Federal Reserve" OR "rate cut" OR inflation OR "jobs report" OR "treasury yields") {TOP_OUTLETS} when:2d'),
                                  {"label": "Fed & rates search"}),
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
            ("DealBook",        "https://rss.nytimes.com/services/xml/rss/nyt/Dealbook.xml"),
            ("PE Hub",          "https://www.pehub.com/feed/"),
            ("PEI",             "https://www.privateequityinternational.com/feed/"),
            ("Crunchbase News", "https://news.crunchbase.com/feed/"),
            ("Money Stuff",     "https://www.bloomberg.com/opinion/authors/ARbTQlRLRjE/matthew-s-levine.rss"),
            ("Google News",     gnews(f'(intitle:acquire OR intitle:acquires OR intitle:acquisition OR intitle:merger OR intitle:buyout OR intitle:takeover OR intitle:"take-private" OR intitle:"to buy") {TOP_OUTLETS} when:2d'),
                                {"label": "M&A search"}),
            ("Google News",     gnews('IPO (prices OR files OR debut OR "going public" OR "S-1") when:2d'),
                                {"label": "IPO search"}),
            ("Google News",     gnews('"private equity" (acquire OR buyout OR stake OR fundraise OR "closes fund") when:2d'),
                                {"label": "Private equity search"}),
        ],
    },
    "Real Estate & REITs": {
        "icon":  "🏢",
        "color": "#06b6d4",
        "sources": [
            ("Commercial Observer", "https://commercialobserver.com/feed/"),
            ("Bisnow",              "https://www.bisnow.com/national/rss"),
            ("HousingWire",         "https://www.housingwire.com/feed/"),
            ("Connect CRE",         "https://www.connectcre.com/feed/"),
            ("CNBC",                CNBC.format(10000115)),
            ("WSJ",                 DJ.format("latestnewsrealestate"), {"filter": True}),
            ("Google News",         gnews('REIT (acquisition OR acquire OR merger OR sells OR buys) when:3d'),
                                    {"label": "REIT deals search"}),
        ],
    },
    "Earnings & Results": {
        "icon":  "📊",
        "color": "#ec4899",
        "sources": [
            ("Seeking Alpha", "https://seekingalpha.com/tag/earnings/feed.xml"),
            ("Investing.com", "https://www.investing.com/rss/news_1062.rss"),
            ("CNBC",          CNBC.format(15839135)),
            ("Google News",   gnews(f'(intitle:earnings OR intitle:profit OR intitle:revenue OR intitle:results OR intitle:quarter) {TOP_OUTLETS} when:1d'),
                              {"label": "Earnings search"}),
            ("Google News",   gnews('("raises guidance" OR "cuts guidance" OR "raised its forecast" OR "lowered its forecast" OR "full-year outlook") when:2d'),
                              {"label": "Guidance search"}),
        ],
    },
    "Tech & Fintech": {
        "icon":  "💻",
        "color": "#8b5cf6",
        "sources": [
            ("Bloomberg",   "https://feeds.bloomberg.com/technology/news.rss"),
            ("WSJ",         DJ.format("RSSWSJD"), {"filter": True}),
            ("CNBC",        CNBC.format(19854910), {"filter": True}),
            ("TechCrunch",  "https://techcrunch.com/feed/", {"filter": True}),
            ("Finextra",    "https://www.finextra.com/rss/headlines.aspx"),
            ("CoinDesk",    "https://www.coindesk.com/arc/outboundfeeds/rss/"),
            ("Google News", gnews('(fintech OR neobank OR "payments startup" OR stablecoin) (raises OR launches OR acquires OR funding) when:2d'),
                            {"label": "Fintech search"}),
        ],
    },
}

# ── Ticker tokens to ignore when extracting trending companies ─────────────────
TICKER_STOPWORDS = {
    # Finance abbreviations
    "US", "UK", "EU", "ECB", "FED", "SEC", "IPO", "GDP", "CEO", "CFO", "COO", "CTO",
    "ETF", "PE", "VC", "AI", "IT", "ML", "CPI", "PPI", "IMF", "WTO", "NYSE", "FDIC",
    "FOMC", "DOJ", "FTC", "DOE", "ESG", "LBO", "REIT", "SPX", "SPY", "ETH", "BTC",
    "NEW", "TOP", "IRS", "APR", "APY", "AUM", "FY", "YTD", "EPS", "EV", "ROE",
    "DCF", "IRR", "NAV", "NPV", "NIM", "NII", "ROA", "EBIT", "NFT",
    # English words that appear in caps in headlines
    "THE", "AND", "FOR", "INC", "LLC", "LTD", "PLC", "CORP", "CO", "AS", "AT", "IN",
    "ON", "TO", "OF", "BY", "IS", "AN", "OR", "BE", "DO", "NOT", "ALL", "CAN",
    "WAS", "OUT", "ONE", "TWO", "MAY", "HAS", "HAD", "WHO", "ARE", "BUT",
    "SAYS", "SAID", "WILL", "AFTER", "OVER", "MORE", "DOWN", "WHAT", "HOW", "WHEN",
    "THAN", "FROM", "WITH", "AMID", "INTO", "PLAN", "DEAL", "RATE", "RISE", "FALL",
    "CUTS", "HIKE", "BANK", "FUND", "FIRM", "YEAR", "WEEK", "DAYS", "LAST", "NEXT",
    "HIGH", "MAKE", "TAKE", "BACK", "WELL", "JUST", "ALSO", "ONLY", "ALSO",
    "AMID", "FIRST", "THEIR", "COULD", "WOULD", "ABOUT", "THESE",
    # Months
    "JAN", "FEB", "MAR", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
}

# ── Shared CSS (real braces — inserted via {COMMON_STYLES} in f-strings) ──────
COMMON_STYLES = """\
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    /* ── Themes ── */
    html[data-theme="dark"] {
      --bg:        #0b0e14;
      --surface:   #111520;
      --border:    #1c2332;
      --text:      #dde4f0;
      --muted:     #5a6a85;
      --hover:     #161d2e;
      --gold:      #f59e0b;
      --header-bg: #111520;
    }
    html[data-theme="light"] {
      --bg:        #f4f6f9;
      --surface:   #ffffff;
      --border:    #dde3ed;
      --text:      #1a2236;
      --muted:     #6b7a96;
      --hover:     #eef1f7;
      --gold:      #d97706;
      --header-bg: #ffffff;
    }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      font-size: 15px;
      line-height: 1.55;
      transition: background .2s, color .2s;
    }

    /* ── Announcement Banner ── */
    .announcement-banner {
      background: #0d1f0d;
      border-bottom: 1px solid #22c55e40;
      padding: 10px 40px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: .85rem;
      color: #22c55e;
    }
    .announcement-banner span { flex: 1; }
    .announce-close {
      background: none;
      border: none;
      color: #22c55e;
      font-size: 1.2rem;
      cursor: pointer;
      padding: 0 4px;
      line-height: 1;
      opacity: .6;
    }
    .announce-close:hover { opacity: 1; }
    html[data-theme="light"] .announcement-banner { background: #f0fdf4; }

    /* ── Ticker ── */
    .ticker-wrap {
      background: var(--surface);
      border-bottom: 1px solid var(--border);
    }

    /* ── Header ── */
    header {
      position: sticky;
      top: 0;
      z-index: 20;
      background: var(--header-bg);
      border-bottom: 1px solid var(--border);
      box-shadow: 0 1px 8px rgba(0,0,0,.15);
    }
    .header-row {
      padding: 12px 40px;
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .logo { font-size: 1.2rem; font-weight: 700; letter-spacing: -.02em; white-space: nowrap; }
    .logo em { color: #22c55e; font-style: normal; }

    /* Fear & Greed Widget */
    .fg-widget {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1px;
      padding: 5px 10px;
      border: 1px solid var(--border);
      border-radius: 8px;
      text-decoration: none;
      color: inherit;
      transition: background .15s;
      flex-shrink: 0;
      min-width: 68px;
    }
    .fg-widget:hover { background: var(--hover); }
    .fg-label  { font-size: .5rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); white-space: nowrap; }
    .fg-score  { font-size: 1.05rem; font-weight: 800; line-height: 1.1; }
    .fg-rating { font-size: .55rem; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; white-space: nowrap; }
    .fg-neutral { color: var(--muted); }

    /* Search */
    .search-wrap { flex: 1; max-width: 380px; }
    #search {
      width: 100%;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 7px 14px;
      color: var(--text);
      font-size: .85rem;
      outline: none;
      transition: border-color .15s;
    }
    #search::placeholder { color: var(--muted); }
    #search:focus { border-color: #3b82f6; }

    /* Theme toggle */
    #theme-btn {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 6px 10px;
      font-size: 1rem;
      cursor: pointer;
      color: var(--text);
      flex-shrink: 0;
      transition: background .15s;
    }
    #theme-btn:hover { background: var(--hover); }

    .header-meta { text-align: right; white-space: nowrap; margin-left: auto; }
    .header-meta .date    { font-size: .9rem; font-weight: 600; }
    .header-meta .updated { font-size: .75rem; color: var(--muted); margin-top: 2px; }

    /* ── Section Nav ── */
    .section-nav {
      display: flex;
      gap: 4px;
      padding: 8px 40px;
      border-top: 1px solid var(--border);
      overflow-x: auto;
      scrollbar-width: none;
    }
    .section-nav::-webkit-scrollbar { display: none; }
    .nav-item {
      white-space: nowrap;
      font-size: .72rem;
      font-weight: 600;
      letter-spacing: .03em;
      padding: 4px 10px;
      border-radius: 99px;
      border: 1px solid var(--border);
      color: var(--muted);
      text-decoration: none;
      transition: background .15s, color .15s, border-color .15s;
      flex-shrink: 0;
    }
    .nav-item:hover { background: var(--hover); color: var(--text); border-color: #3b82f6; }
    .nav-item kbd {
      font-size: .55rem;
      font-family: inherit;
      background: var(--border);
      border-radius: 3px;
      padding: 1px 3px;
      margin-left: 3px;
      color: var(--muted);
    }
    .nav-item.nav-ext { border-color: #22c55e40; color: #22c55e; }
    .nav-item.nav-ext:hover { border-color: #22c55e; background: #0c2314; }

    /* ── Trending Companies Bar ── */
    .trending-bar {
      padding: 10px 28px 0;
      max-width: 1440px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .trending-label {
      font-size: .6rem;
      font-weight: 800;
      letter-spacing: .08em;
      text-transform: uppercase;
      color: var(--muted);
      white-space: nowrap;
      flex-shrink: 0;
    }
    .trending-chips { display: flex; gap: 6px; flex-wrap: wrap; }
    .chip {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 99px;
      padding: 3px 10px;
      font-size: .72rem;
      font-weight: 700;
      letter-spacing: .04em;
      cursor: pointer;
      color: var(--text);
      transition: background .12s, border-color .12s, color .12s;
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .chip:hover { background: var(--hover); border-color: #3b82f6; color: #3b82f6; }
    .chip.active { background: #172136; border-color: #3b82f6; color: #3b82f6; }
    .chip-count {
      font-size: .6rem;
      font-weight: 600;
      color: var(--muted);
      background: var(--border);
      border-radius: 99px;
      padding: 1px 5px;
    }
    .chip.active .chip-count { color: #3b82f6; background: #1e3a5f; }

    /* ── Layout ── */
    main { max-width: 1440px; margin: 0 auto; padding: 24px 28px 80px; }

    .section { margin-bottom: 52px; scroll-margin-top: 120px; }

    .section-heading {
      font-size: 1rem;
      font-weight: 700;
      letter-spacing: .02em;
      text-transform: uppercase;
      margin-bottom: 18px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .pill {
      background: var(--border);
      color: var(--muted);
      font-size: .7rem;
      font-weight: 600;
      padding: 2px 9px;
      border-radius: 99px;
    }

    /* ── Cards ── */
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 12px;
    }
    .card {
      display: flex;
      flex-direction: column;
      gap: 8px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px 18px;
      text-decoration: none;
      color: inherit;
      transition: background .15s, border-color .15s, transform .1s, opacity .15s;
    }
    .card:hover {
      background: var(--hover);
      border-color: #2a3550;
      transform: translateY(-1px);
      opacity: 1 !important;
    }

    /* Recency fade */
    .age-fresh  { opacity: 1; }
    .age-recent { opacity: 0.80; }
    .age-old    { opacity: 0.58; }

    .card-meta  { display: flex; align-items: center; justify-content: space-between; }
    .badge {
      font-size: .65rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .06em;
      padding: 2px 7px;
      border-radius: 4px;
      border: 1px solid;
    }
    .ts { font-size: .72rem; color: var(--muted); display: flex; align-items: center; gap: 5px; }
    .new-badge {
      font-size: .6rem;
      font-weight: 800;
      letter-spacing: .08em;
      color: #fff;
      background: #ef4444;
      border-radius: 3px;
      padding: 1px 5px;
    }
    .card-title   { font-size: .88rem; font-weight: 600; line-height: 1.45; }
    .card-summary { font-size: .78rem; color: var(--muted); line-height: 1.5; }
    .empty        { color: var(--muted); font-style: italic; }

    /* ── Career Cards ── */
    .career-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 12px;
    }
    .career-card {
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
    }
    .career-card:hover { background: var(--hover); border-color: #f97316; transform: translateY(-1px); }
    .career-card.career-featured {
      grid-column: 1 / -1;
      border-color: #f97316;
      background: #120d06;
      flex-direction: row;
      align-items: center;
      gap: 20px;
      padding: 20px 24px;
    }
    .career-card.career-featured:hover { background: #1a1209; }
    .career-firm {
      font-size: .82rem;
      font-weight: 700;
      color: #f97316;
      text-transform: uppercase;
      letter-spacing: .04em;
    }
    .career-featured .career-firm { font-size: 1rem; }
    .career-role     { font-size: .88rem; font-weight: 600; color: var(--text); }
    .career-featured .career-role { font-size: 1rem; }
    .career-deadline { font-size: .78rem; color: var(--muted); }
    .career-featured .career-deadline {
      margin-left: auto;
      font-size: .88rem;
      color: #f97316;
      white-space: nowrap;
    }

    /* ── Premium Sites ── */
    .premium-section { margin-bottom: 52px; scroll-margin-top: 120px; }
    .premium-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 10px;
    }
    .premium-site-card {
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
    }
    .premium-site-card:hover { background: #16120a; border-color: var(--gold); transform: translateY(-1px); }
    .premium-short {
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
    }
    .premium-info  { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
    .premium-name  { font-size: .82rem; font-weight: 600; }
    .premium-desc  { font-size: .72rem; color: var(--muted); }
    .premium-arrow { font-size: .9rem; color: var(--muted); flex-shrink: 0; }

    /* ── Recap Cards ── */
    .recap-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 22px 26px;
      margin-bottom: 20px;
    }
    .recap-week-label {
      font-size: .88rem;
      font-weight: 700;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .04em;
      margin-bottom: 14px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .recap-week-label .current-tag {
      background: #22c55e20;
      border: 1px solid #22c55e40;
      color: #22c55e;
      font-size: .6rem;
      padding: 2px 7px;
      border-radius: 99px;
    }
    .recap-bullets { list-style: none; display: flex; flex-direction: column; gap: 10px; }
    .recap-bullet {
      display: flex;
      gap: 10px;
      align-items: flex-start;
      font-size: .85rem;
      line-height: 1.45;
    }
    .recap-bullet a { color: var(--text); text-decoration: none; flex: 1; }
    .recap-bullet a:hover { color: #3b82f6; }
    .recap-src {
      font-size: .6rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .05em;
      color: var(--muted);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 2px 6px;
      white-space: nowrap;
      flex-shrink: 0;
      margin-top: 2px;
    }
    .recap-stats {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid var(--border);
    }
    .recap-stat {
      font-size: .68rem;
      color: var(--muted);
      background: var(--border);
      border-radius: 99px;
      padding: 2px 9px;
    }

    /* ── Back to top ── */
    #back-top {
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
    }
    #back-top:hover { transform: translateY(-2px); }

    /* ── Week digest badge ── */
    .week-badge {
      display: inline-block;
      background: #1e1b4b;
      border: 1px solid #4f46e5;
      color: #818cf8;
      font-size: .7rem;
      font-weight: 700;
      letter-spacing: .04em;
      padding: 3px 10px;
      border-radius: 99px;
      margin-left: 8px;
    }

    /* ── Footer ── */
    footer {
      border-top: 1px solid var(--border);
      text-align: center;
      padding: 24px;
      color: var(--muted);
      font-size: .78rem;
    }

    /* ── Responsive ── */
    @media (max-width: 680px) {
      .header-row    { padding: 10px 16px; flex-wrap: wrap; }
      .search-wrap   { order: 3; max-width: 100%; width: 100%; }
      .section-nav   { padding: 8px 16px; }
      main           { padding: 16px 16px 80px; }
      .trending-bar  { padding: 8px 16px 0; }
      .grid          { grid-template-columns: 1fr; }
      .premium-grid  { grid-template-columns: 1fr; }
      .fg-widget     { display: none; }
    }"""


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


def find_trending(sections_raw: dict[str, list[dict]], top_n: int = 12) -> list[tuple[str, int]]:
    """Extract most-mentioned company tickers/names from all article headlines."""
    token_re = re.compile(r'\b([A-Z]{2,5})\b')
    counts: dict[str, int] = {}
    for articles in sections_raw.values():
        for a in articles:
            for token in token_re.findall(a["title"]):
                if token not in TICKER_STOPWORDS:
                    counts[token] = counts.get(token, 0) + 1
    trending = [(t, c) for t, c in counts.items() if c >= 2]
    trending.sort(key=lambda x: -x[1])
    return trending[:top_n]


def get_week_key(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def get_week_label(dt: datetime) -> str:
    monday = dt - timedelta(days=dt.weekday())
    friday = monday + timedelta(days=4)
    if monday.month == friday.month:
        return f"Week of {monday.strftime('%B %-d')}–{friday.strftime('%-d, %Y')}"
    return f"Week of {monday.strftime('%B %-d')} – {friday.strftime('%B %-d, %Y')}"


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


# ── Publisher names & junk filtering ──────────────────────────────────────────
# Google News reports publishers inconsistently ("Bloomberg.com", "Financial Times")
PUBLISHER_ALIASES = {
    "bloomberg.com": "Bloomberg", "financial times": "FT", "ft.com": "FT",
    "the wall street journal": "WSJ", "wall street journal": "WSJ",
    "ap news": "AP", "associated press": "AP",
    "the new york times": "NYT", "new york times": "NYT", "nytimes.com": "NYT",
    "marketwatch": "MarketWatch", "barron's": "Barron's", "barrons": "Barron's",
}

# Content farms, auto-generated stock posts and crypto SEO sites seen in Google News results
LOW_QUALITY_PUBLISHERS = {
    "kalkine", "kalkine media", "marketbeat", "simply wall st", "simply wall st.", "ainvest",
    "stock titan", "stocktwits", "tipranks", "gurufocus", "insider monkey", "beincrypto",
    "fxstreet", "bloomingbit", "biggo finance", "scanx.trade", "ad-hoc-news.de", "indexbox",
    "briefs finance", "startup fortune", "pulse 2.0", "nai500", "coincentral", "intellectia ai",
    "meyka", "moomoo", "futunn", "sahm capital", "stockstotrade", "timothy sykes",
    "parameter", "marketscreener", "marketscreener.com", "www.marketscreener.com", "digitaljournal",
    "traders union", "coinfomania", "crypto briefing", "cointrust", "hokanews", "pluang",
    "goodreturns", "investors king", "prop news time", "coinmarketcap", "london south east",
    "intlbm", "the realist | howard chai", "247 wall st.", "24/7 wall st.",
}

JUNK_TITLE_RE = re.compile("|".join([
    r"\bearnings preview\b",                                   # Seeking Alpha stubs
    r"stock price, news, quote",                               # quote pages
    r"\b(buys|bought) back [\d,]+ (shares|securities)\b",      # buyback filings
    r"\b(director|officer|insider)\b.*\b(sells|buys|sold|bought)\b.*\b(stock|shares)\b",
    r"\b(raises|lowers|trims|boosts|cuts|increases|decreases) (its )?(stake|position|holdings) in\b",
    r"\b(stake|position|holdings) in .+ (raised|lowered|trimmed|boosted|cut) by\b",
    r"\bprice prediction\b",
    r":\s*live( levels)?$",                                     # chart-level posts
    r"^(podcast|watch|video)\b",
    r"^reg - ",                                                # LSE regulatory filings
    r"\bcramer\b",                                             # CNBC entertainment segments
    r"^we['’]re (upgrading|downgrading|buying|selling|trimming|adding)\b",  # CNBC Investing Club
    r"^(current|today['’]s|best) .*\b(rates|accounts|cards)\b",  # evergreen rate/SEO pages
]), re.IGNORECASE)


# Headline must mention one of these to pass on general-interest feeds (opts["filter"])
FINANCE_RE = re.compile(r"""\b(
    stocks?|shares?|equit(y|ies)|markets?|investors?|investing|investment|traders?|trading|
    earnings|revenue|profits?|loss(es)?|sales|guidance|forecasts?|outlook|quarter(ly)?|
    deals?|mergers?|acquisitions?|acquires?|acquired|buyouts?|takeovers?|ipos?|valuation|
    funding|raises|fundrais\w*|funds?|private\ equity|venture|startups?|unicorn|
    banks?|banking|bankers?|lenders?|lending|loans?|credit|debt|bonds?|yields?|treasur(y|ies)|
    rates?|inflation|fed|central\ bank|economy|economies|economic|gdp|recession|jobs|
    unemployment|payrolls|tariffs?|trade\ (war|deal|talks|deficit|surplus|policy)|exports?|imports?|
    dollar|currenc(y|ies)|
    oil|gold|coal|copper|lng|iron\ ore|metals?|commodit(y|ies)|prices?|wall\ street|s&p|nasdaq|dow|
    rall(y|ies|ied)|sell-?offs?|plunges?|plunged|surges?|surged|soars?|soared|tumbles?|tumbled|
    slumps?|slumped|sinks?|sank|dips?|analysts?|bullish|bearish|activist|shareholders?|
    billion|trillion|fintech|payments?|crypto|bitcoin|stablecoins?|
    q[1-4]|shipments|deliveries|turnaround|buys|sells|sale|divest\w*|spin-?offs?|
    settle(s|d|ment)?|lay(s|ing)?\ off|luxury|industry|morning\ bid|
    mortgages?|housing|real\ estate|reits?|property|properties|condos?|borrow\w*|layoffs?|
    bankrupt\w*|chapter\ 11|
    antitrust|regulators?|sec|ftc|sanctions?|subsidies|chipmakers?|semiconductors?|data\ centers?
)\b | [$€£]\d   # any currency amount""", re.IGNORECASE | re.VERBOSE)

# Reader-question / personal-advice columns (MarketWatch "Moneyist" etc.)
ADVICE_RE = re.compile(
    r"\bmy (wife|husband|partner|girlfriend|boyfriend|fianc\w*|mom|dad|mother|father|son|"
    r"daughter|brother|sister|parents|family|financial advis[eo]r|planner)\b"
    r"|\b(i'?m|i am) (a |an )?\d{2}\b|\bshould i\b|\bcan i\b|\bam i\b",
    re.IGNORECASE)


def is_off_topic(title: str, filtered: bool) -> bool:
    title = title.replace("’", "'")
    return bool(ADVICE_RE.search(title)) or (filtered and not FINANCE_RE.search(title))


def normalize_publisher(name: str) -> str:
    name = name.strip()
    key  = name.lower()
    if key.startswith("investing.com"):
        return "Investing.com"
    if key.startswith("yahoo"):
        return "Yahoo Finance"
    return PUBLISHER_ALIASES.get(key, name)


def is_english(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return not letters or sum(c.isascii() for c in letters) / len(letters) > 0.8


def is_junk(title: str, publisher: str) -> bool:
    pub = publisher.lower()
    return (pub in LOW_QUALITY_PUBLISHERS
            or pub.startswith(("http", "www."))                # unnamed/scraper sites
            or not is_english(title) or not is_english(publisher)
            or bool(JUNK_TITLE_RE.search(title)))


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


def spread_publishers(articles: list[dict]) -> list[dict]:
    """Keep recency order but avoid showing the same publisher twice in a row."""
    out, pending = [], list(articles)
    while pending:
        idx = next((i for i, a in enumerate(pending)
                    if not out or a["source"] != out[-1]["source"]), 0)
        out.append(pending.pop(idx))
    return out


def pick_diverse(articles: list[dict], limit: int, per_source: int = MAX_PER_SOURCE,
                 key=lambda a: a["pub"]) -> list[dict]:
    """Best-first selection (newest by default) with at most `per_source` cards per publisher."""
    counts: dict[str, int] = {}
    picked = []
    for a in sorted(articles, key=key, reverse=True):
        if counts.get(a["source"], 0) >= per_source:
            continue
        counts[a["source"]] = counts.get(a["source"], 0) + 1
        picked.append(a)
        if len(picked) >= limit:
            break
    return spread_publishers(picked)


# ── Story matching (dedupe + Top Stories) ─────────────────────────────────────
TITLE_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "over", "after", "amid", "about", "says",
    "said", "say", "will", "would", "could", "can", "may", "its", "his", "her", "their", "this",
    "that", "than", "more", "most", "new", "how", "why", "what", "who", "when", "are", "was",
    "has", "have", "had", "been", "not", "but", "out", "off", "via", "per", "you", "your",
    "our", "all", "set", "top", "big", "first", "year", "week", "day", "u.s", "us",
    "report", "news", "update", "exclusive", "commentary", "analysis", "source",
}


def _stem(word: str) -> str:
    """Crude stemmer so 'fined'/'fine' and 'raises'/'raised' compare equal."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    return word[:-1] if len(word) > 3 and word.endswith("e") else word


def story_words(article: dict) -> set:
    """Normalized content words of a headline (cached on the article)."""
    if "_words" not in article:
        title = article["title"].lower().replace("’", "'").replace("'s ", " ")
        raw   = re.findall(r"[a-z][a-z&.']*|\d+(?:\.\d+)?", title)
        words = {_stem(w.strip(".'")) for w in raw}
        article["_words"] = {w for w in words if len(w) > 2 or w[0].isdigit()} - TITLE_STOPWORDS
    return article["_words"]


def cluster_articles(articles: list[dict]) -> list[dict]:
    """Group articles about the same story. Sets a["cluster"] and a["coverage"].

    Two headlines match when they share several words *and* at least one of the shared
    words is rare across today's headlines (a company name, a dollar figure…), so generic
    finance vocabulary like "stocks" or "Wall Street" can't link unrelated stories.
    """
    df: dict[str, int] = {}
    for a in articles:
        for w in story_words(a):
            df[w] = df.get(w, 0) + 1
    rare_max = max(3, len(articles) // 100)

    def same_story(a: dict, b: dict) -> bool:
        wa, wb = story_words(a), story_words(b)
        if not wa or not wb:
            return False
        shared  = wa & wb
        rare    = [w for w in shared if df[w] <= rare_max]
        overlap = len(shared) / min(len(wa), len(wb))
        return ((len(shared) >= 3 and overlap >= 0.5 and len(rare) >= 1)
                or (len(rare) >= 2 and len(shared) >= 3 and overlap >= 0.4))

    clusters: list[dict] = []
    for a in sorted(articles, key=lambda a: a["pub"], reverse=True):
        # must match a cluster's lead article, or two of its members (limits A~B~C chaining)
        home = next((c for c in clusters
                     if same_story(a, c["articles"][0])
                     or sum(same_story(a, m) for m in c["articles"][1:6]) >= 2), None)
        if home is None:
            home = {"id": len(clusters), "articles": [], "publishers": set()}
            clusters.append(home)
        home["articles"].append(a)
        home["publishers"].add(a["source"])
        a["cluster"] = home["id"]
    for c in clusters:
        for a in c["articles"]:
            a["coverage"] = len(c["publishers"])
    return clusters


# Major outlets: weighted higher when ranking Top Stories, preferred as the card shown
MAJOR_PUBLISHERS = ["Reuters", "Bloomberg", "WSJ", "FT", "AP", "CNBC", "NYT", "DealBook",
                    "Barron's", "MarketWatch", "Axios"]


NON_HEADLINE_RE = re.compile(r"transcript|live blog|live updates|as it happened", re.IGNORECASE)


def _display_rank(a: dict) -> tuple:
    """Higher is better: a real headline, from a major outlet, with a summary, newest."""
    major = len(MAJOR_PUBLISHERS) - MAJOR_PUBLISHERS.index(a["source"]) \
        if a["source"] in MAJOR_PUBLISHERS else 0
    return (not NON_HEADLINE_RE.search(a["title"]), major, bool(a["summary"]), a["pub"])


def find_top_stories(clusters: list[dict], now: datetime, window_h: float) -> list[dict]:
    """Stories covered by 2+ publishers, ranked by breadth of coverage then recency."""
    def score(c):
        majors = sum(p in MAJOR_PUBLISHERS for p in c["publishers"])
        minors = len(c["publishers"]) - majors
        age_h  = (now - max(a["pub"] for a in c["articles"])).total_seconds() / 3600
        return 2 * majors + 0.5 * minors + 2 * max(0.0, 1 - age_h / window_h)

    used_publishers: set[str] = set()
    result = []
    for c in sorted((c for c in clusters if len(c["publishers"]) >= 2), key=score, reverse=True):
        cands = sorted(c["articles"], key=_display_rank, reverse=True)
        # prefer a publisher not already shown in Top Stories
        chosen = next((a for a in cands if a["source"] not in used_publishers), cands[0])
        used_publishers.add(chosen["source"])
        result.append(chosen)
        if len(result) >= MAX_TOP_STORIES:
            break
    return result


def select_stories(raw: dict[str, list[dict]], limit: int, now: datetime, window_h: float,
                   by_coverage: bool) -> tuple[list[dict], dict[str, list[dict]]]:
    """Pick Top Stories and each section's cards so no story appears twice on the page.

    by_coverage=False → newest first (daily page); True → most widely covered first (weekly).
    """
    # copies: the daily and weekly pages cluster the same articles independently
    raw = {name: [dict(a) for a in arts] for name, arts in raw.items()}
    clusters = cluster_articles([a for arts in raw.values() for a in arts])
    top      = find_top_stories(clusters, now, window_h)
    shown    = {a["cluster"] for a in top}
    rank     = (lambda a: (a["coverage"], a["pub"])) if by_coverage else (lambda a: a["pub"])

    sections = {}
    for name, arts in raw.items():
        best: dict[int, dict] = {}
        for a in arts:
            if a["cluster"] in shown:
                continue
            cur = best.get(a["cluster"])
            if cur is None or _display_rank(a) > _display_rank(cur):
                best[a["cluster"]] = a
        sections[name] = pick_diverse(list(best.values()), limit, key=rank)
        shown |= {a["cluster"] for a in sections[name]}
    return top, sections


# ── HTML Renderers ─────────────────────────────────────────────────────────────
def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_card(article: dict, color: str | None = None) -> str:
    t         = esc(article["title"])
    s         = esc(article["summary"])
    lk        = esc(article["link"])
    src       = esc(article["source"])
    ts        = time_ago(article["pub"])
    c         = color or article.get("color", "#22c55e")
    age_cls   = article.get("age_class", "age-old")
    new_badge = '<span class="new-badge">NEW</span>' if article.get("is_new") else ""
    summary_html = f'<p class="card-summary">{s}</p>' if s else ""
    return f"""\
    <a class="card {age_cls}" href="{lk}" target="_blank" rel="noopener noreferrer">
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


def render_fear_greed_widget(fg: dict | None) -> str:
    if not fg:
        return (
            '<a class="fg-widget" href="https://money.cnn.com/data/fear-and-greed/"'
            ' target="_blank" rel="noopener noreferrer">'
            '<span class="fg-label">Fear &amp; Greed</span>'
            '<span class="fg-score fg-neutral">–</span>'
            '<span class="fg-rating">View →</span></a>'
        )
    score  = fg["score"]
    rating = fg["rating"]
    prev   = fg.get("prev")
    if score < 25:
        color = "#ef4444"; bg = "#2d0f0f"
    elif score < 45:
        color = "#f97316"; bg = "#2a1506"
    elif score < 55:
        color = "#eab308"; bg = "#241d03"
    elif score < 75:
        color = "#22c55e"; bg = "#0c2314"
    else:
        color = "#16a34a"; bg = "#082010"
    arrow = ""
    if prev is not None:
        arrow = " ▲" if score > prev else " ▼" if score < prev else ""
    return (
        f'<a class="fg-widget" href="https://money.cnn.com/data/fear-and-greed/"'
        f' target="_blank" rel="noopener noreferrer"'
        f' style="background:{bg};border-color:{color}40">'
        f'<span class="fg-label">Fear &amp; Greed</span>'
        f'<span class="fg-score" style="color:{color}">{score}{arrow}</span>'
        f'<span class="fg-rating" style="color:{color}">{esc(rating)}</span></a>'
    )


def render_trending_bar(trending: list[tuple[str, int]]) -> str:
    if not trending:
        return ""
    chips = "".join(
        f'<button class="chip" onclick="filterByChip(this,\'{t}\')">'
        f'{t}<span class="chip-count">{c}</span></button>'
        for t, c in trending
    )
    return f"""\
  <div class="trending-bar" id="trending-bar">
    <span class="trending-label">Trending</span>
    <div class="trending-chips">{chips}</div>
  </div>"""


def _render_sections_html(sections: dict, top_stories: list[dict],
                           max_per: int) -> tuple[str, str, list[str]]:
    """Returns (nav_items_html, sections_html, section_ids_list)."""
    key_num     = 1
    section_ids = []
    nav_items   = ""

    if top_stories:
        nav_items += f'<a class="nav-item" href="#top-stories">🔥 Top Stories <kbd>{key_num}</kbd></a>\n'
        section_ids.append("top-stories")
        key_num += 1

    for name in sections:
        sid   = slugify(name)
        first = name.split(" & ")[0].split(" ")[0]
        icon  = sections[name][0]["icon"]
        nav_items += f'    <a class="nav-item" href="#{sid}">{icon} {first} <kbd>{key_num}</kbd></a>\n'
        section_ids.append(sid)
        key_num += 1
        if name == "Investment Banking & Deals":
            nav_items += f'    <a class="nav-item" href="#careers-recruiting">💼 Careers <kbd>{key_num}</kbd></a>\n'
            section_ids.append("careers-recruiting")
            key_num += 1
        if name == "Earnings & Results":
            nav_items += f'    <a class="nav-item" href="#economic-calendar">📅 Calendar <kbd>{key_num}</kbd></a>\n'
            section_ids.append("economic-calendar")
            key_num += 1

    nav_items += f'    <a class="nav-item" href="#premium">🔒 Premium <kbd>{key_num}</kbd></a>\n'
    section_ids.append("premium")

    # ── Build section HTML ───────────────────────────────────────────────────
    sections_html = ""
    if top_stories:
        top_cards = "\n".join(render_card(a) for a in top_stories)
        sections_html += f"""\
  <section class="section" id="top-stories" data-section>
    <h2 class="section-heading" style="color:#f97316">
      🔥 Top Stories <span class="pill">{len(top_stories)}</span>
    </h2>
    <div class="grid">
{top_cards}
    </div>
  </section>
"""

    for name, (config, articles) in sections.items():
        color = config["color"]
        icon  = config["icon"]
        sid   = slugify(name)
        shown = articles[:max_per]
        count = len(shown)
        cards = "\n".join(render_card(a, color) for a in shown) if shown else \
                '<p class="empty">No articles found for this period.</p>'
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
        if name == "Investment Banking & Deals":
            sections_html += f"""\
  <section class="section" id="careers-recruiting" data-section>
    <h2 class="section-heading" style="color:#f97316">
      \U0001f4bc Careers &amp; Recruiting <span class="pill">{len(INTERNSHIP_RESOURCES)}</span>
    </h2>
    <div class="career-grid">
{render_careers_section()}
    </div>
  </section>
"""
        if name == "Earnings & Results":
            sections_html += f"""\
  <section class="section" id="economic-calendar" data-section>
    <h2 class="section-heading" style="color:#f59e0b">
      \U0001f4c5 Economic Calendar
    </h2>
{CALENDAR_HTML}
  </section>
"""

    return nav_items, sections_html, section_ids


def build_html(sections: dict, top_stories: list[dict], generated: datetime,
               fg: dict | None, trending: list[tuple[str, int]], health: dict) -> str:
    date_str  = generated.strftime("%A, %B %-d, %Y")
    time_str  = generated.strftime("%-I:%M %p UTC")
    total     = sum(len(arts) for _, arts in sections.values()) + len(top_stories)

    nav_items, sections_html, section_ids = _render_sections_html(
        sections, top_stories, MAX_PER_SECTION
    )
    nav_items += '    <a class="nav-item nav-ext" href="week.html">📅 Weekly</a>\n'
    nav_items += '    <a class="nav-item nav-ext" href="recaps.html">📋 Recaps</a>\n'

    fg_widget       = render_fear_greed_widget(fg)
    trending_bar    = render_trending_bar(trending)
    shown_counts: dict[str, int] = {}
    for a in top_stories + [a for _, arts in sections.values() for a in arts]:
        shown_counts[a["source"]] = shown_counts.get(a["source"], 0) + 1
    top_pubs        = sorted(shown_counts, key=shown_counts.get, reverse=True)[:10]
    live_feeds      = sum(r["status"] == "ok" for r in health.values())
    footer_sources  = (f"Sources today: {' &middot; '.join(esc(p) for p in top_pubs)} &amp; more"
                       f" &nbsp;|&nbsp; {live_feeds}/{len(health)} feeds live")
    premium_html    = render_premium_sites()
    section_ids_js  = json.dumps(section_ids)

    announcement_html = ""
    if ANNOUNCEMENT:
        announcement_html = (
            '  <div class="announcement-banner" id="announcement">\n'
            f'    <span>{esc(ANNOUNCEMENT)}</span>\n'
            '    <button class="announce-close" id="announce-close" title="Dismiss">×</button>\n'
            '  </div>\n'
        )

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
{COMMON_STYLES}
  </style>
</head>
<body>

{announcement_html}{TICKER_HTML}

  <header>
    <div class="header-row">
      <div class="logo">Finance <em>News</em></div>
      {fg_widget}
      <div class="search-wrap">
        <input id="search" type="search" placeholder="Search… (press / to focus)" autocomplete="off">
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

{trending_bar}
  <main>
{sections_html}
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
    {footer_sources} &nbsp;|&nbsp;
    Regenerates 3&times; daily &nbsp;|&nbsp;
    <a href="week.html" style="color:inherit">📅 Weekly</a> &nbsp;|&nbsp;
    <a href="recaps.html" style="color:inherit">📋 Recaps</a>
  </footer>

  <button id="back-top" title="Back to top">↑</button>

  <script>
    // ── Search ──────────────────────────────────────────────────────────────
    const searchInput = document.getElementById('search');
    function runSearch(q) {{
      const lower = q.toLowerCase().trim();
      let visible = 0;
      document.querySelectorAll('[data-section]').forEach(section => {{
        let sv = 0;
        section.querySelectorAll('.card').forEach(card => {{
          const match = !lower || card.textContent.toLowerCase().includes(lower);
          card.style.display = match ? '' : 'none';
          if (match) {{ sv++; visible++; }}
        }});
        section.style.display = sv === 0 && lower ? 'none' : '';
      }});
      document.title = lower
        ? `Finance News — ${{visible}} results`
        : `Finance News — {date_str} ({total} articles)`;
    }}
    searchInput.addEventListener('input', () => runSearch(searchInput.value));

    // ── Trending Chip Filter ─────────────────────────────────────────────────
    let activeChip = null;
    function filterByChip(btn, term) {{
      if (activeChip === term) {{
        activeChip = null;
        btn.classList.remove('active');
        searchInput.value = '';
        runSearch('');
      }} else {{
        document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
        activeChip = term;
        btn.classList.add('active');
        searchInput.value = term;
        runSearch(term);
      }}
    }}

    // ── Light / Dark Mode ────────────────────────────────────────────────────
    const html     = document.documentElement;
    const themeBtn = document.getElementById('theme-btn');
    const saved    = localStorage.getItem('theme') || 'dark';
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

    // ── Announcement dismiss ─────────────────────────────────────────────────
    const announceClose = document.getElementById('announce-close');
    if (announceClose) {{
      announceClose.addEventListener('click', () => {{
        document.getElementById('announcement').style.display = 'none';
      }});
    }}

    // ── Keyboard Shortcuts ───────────────────────────────────────────────────
    const sectionIds = {section_ids_js};
    document.addEventListener('keydown', e => {{
      if (e.target === searchInput) {{
        if (e.key === 'Escape') {{
          searchInput.value = '';
          searchInput.blur();
          runSearch('');
          document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
          activeChip = null;
        }}
        return;
      }}
      if (e.key === '/' && !e.ctrlKey && !e.metaKey) {{ e.preventDefault(); searchInput.focus(); return; }}
      const num = parseInt(e.key, 10);
      if (!isNaN(num) && num >= 1 && num <= sectionIds.length) {{
        const el = document.getElementById(sectionIds[num - 1]);
        if (el) el.scrollIntoView({{ behavior: 'smooth' }});
      }}
    }});
  </script>
</body>
</html>"""


def build_week_html(sections: dict, top_stories: list[dict], generated: datetime,
                    fg: dict | None) -> str:
    time_str   = generated.strftime("%-I:%M %p UTC")
    week_start = generated - timedelta(days=6)
    week_range = f"{week_start.strftime('%b %-d')} – {generated.strftime('%b %-d, %Y')}"
    total      = sum(len(arts) for _, arts in sections.values()) + len(top_stories)

    nav_items, sections_html, section_ids = _render_sections_html(
        sections, top_stories, MAX_PER_SECTION_WEEK
    )
    nav_items += '    <a class="nav-item nav-ext" href="index.html">← Today</a>\n'
    nav_items += '    <a class="nav-item nav-ext" href="recaps.html">📋 Recaps</a>\n'

    fg_widget      = render_fear_greed_widget(fg)
    premium_html   = render_premium_sites()
    section_ids_js = json.dumps(section_ids)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Weekly finance digest — top stories from the past 7 days.">
  <meta property="og:title" content="Finance News — Weekly Digest">
  <title>Finance News — Weekly Digest ({week_range})</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📅</text></svg>">
  <style>
{COMMON_STYLES}
  </style>
</head>
<body>

{TICKER_HTML}

  <header>
    <div class="header-row">
      <div class="logo">Finance <em>News</em> <span class="week-badge">7-DAY DIGEST</span></div>
      {fg_widget}
      <div class="search-wrap">
        <input id="search" type="search" placeholder="Search… (press / to focus)" autocomplete="off">
      </div>
      <button id="theme-btn" title="Toggle light/dark mode">☀️</button>
      <div class="header-meta">
        <div class="date">{week_range}</div>
        <div class="updated">Generated {time_str} · {total} articles</div>
      </div>
    </div>
    <nav class="section-nav">
    {nav_items}
    </nav>
  </header>

  <main>
{sections_html}
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
    Weekly Digest covers the past 7 days &nbsp;|&nbsp;
    <a href="index.html" style="color:inherit">← Back to Today's Feed</a> &nbsp;|&nbsp;
    <a href="recaps.html" style="color:inherit">📋 Past Recaps</a>
  </footer>

  <button id="back-top" title="Back to top">↑</button>

  <script>
    const searchInput = document.getElementById('search');
    searchInput.addEventListener('input', () => {{
      const q = searchInput.value.toLowerCase().trim();
      document.querySelectorAll('[data-section]').forEach(section => {{
        let sv = 0;
        section.querySelectorAll('.card').forEach(card => {{
          const match = !q || card.textContent.toLowerCase().includes(q);
          card.style.display = match ? '' : 'none';
          if (match) sv++;
        }});
        section.style.display = sv === 0 && q ? 'none' : '';
      }});
    }});

    const html     = document.documentElement;
    const themeBtn = document.getElementById('theme-btn');
    const saved    = localStorage.getItem('theme') || 'dark';
    html.setAttribute('data-theme', saved);
    themeBtn.textContent = saved === 'dark' ? '☀️' : '🌙';
    themeBtn.addEventListener('click', () => {{
      const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      html.setAttribute('data-theme', next);
      themeBtn.textContent = next === 'dark' ? '☀️' : '🌙';
      localStorage.setItem('theme', next);
    }});

    const backTop = document.getElementById('back-top');
    window.addEventListener('scroll', () => {{
      backTop.style.display = window.scrollY > 400 ? 'flex' : 'none';
    }}, {{ passive: true }});
    backTop.addEventListener('click', () => window.scrollTo({{ top: 0, behavior: 'smooth' }}));

    const sectionIds = {section_ids_js};
    document.addEventListener('keydown', e => {{
      if (e.target === searchInput) {{
        if (e.key === 'Escape') {{ searchInput.value = ''; searchInput.blur(); searchInput.dispatchEvent(new Event('input')); }}
        return;
      }}
      if (e.key === '/' && !e.ctrlKey && !e.metaKey) {{ e.preventDefault(); searchInput.focus(); return; }}
      const num = parseInt(e.key, 10);
      if (!isNaN(num) && num >= 1 && num <= sectionIds.length) {{
        const el = document.getElementById(sectionIds[num - 1]);
        if (el) el.scrollIntoView({{ behavior: 'smooth' }});
      }}
    }});
  </script>
</body>
</html>"""


def build_recaps_html(summaries: list, generated: datetime,
                      fg: dict | None) -> str:
    """Render the weekly recaps archive page."""
    date_str      = generated.strftime("%B %-d, %Y")
    time_str      = generated.strftime("%-I:%M %p UTC")
    fg_widget     = render_fear_greed_widget(fg)
    current_week  = get_week_key(generated)
    sorted_sums   = sorted(summaries, key=lambda s: s["week"], reverse=True)

    cards_html = ""
    if not sorted_sums:
        cards_html = '<p class="empty" style="margin-top:24px">No past summaries yet — check back after the first full week of data is collected.</p>'
    else:
        for entry in sorted_sums:
            is_current = entry["week"] == current_week
            current_tag = '<span class="current-tag">THIS WEEK</span>' if is_current else ""
            bullets_html = ""
            for b in entry.get("bullets", []):
                src_badge = f'<span class="recap-src">{esc(b.get("source",""))}</span>'
                link = esc(b.get("link", "#"))
                bullets_html += (
                    f'<li class="recap-bullet">{src_badge}'
                    f'<a href="{link}" target="_blank" rel="noopener noreferrer">'
                    f'{esc(b["headline"])}</a></li>\n'
                )

            stats_html = ""
            for sec, cnt in entry.get("section_counts", {}).items():
                short = sec.split(" & ")[0].split(" ")[0]
                stats_html += f'<span class="recap-stat">{short} {cnt}</span>\n'

            cards_html += f"""\
  <div class="recap-card">
    <div class="recap-week-label">{esc(entry['label'])} {current_tag}</div>
    <ul class="recap-bullets">
{bullets_html}
    </ul>
    <div class="recap-stats">
{stats_html}
    </div>
  </div>
"""

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Weekly finance news recaps — catch up on what you missed.">
  <meta property="og:title" content="Finance News — Weekly Recaps">
  <title>Finance News — Weekly Recaps</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📋</text></svg>">
  <style>
{COMMON_STYLES}
  </style>
</head>
<body>

{TICKER_HTML}

  <header>
    <div class="header-row">
      <div class="logo">Finance <em>News</em> <span class="week-badge">RECAPS</span></div>
      {fg_widget}
      <div class="search-wrap">
        <input id="search" type="search" placeholder="Search recaps…" autocomplete="off">
      </div>
      <button id="theme-btn" title="Toggle light/dark mode">☀️</button>
      <div class="header-meta">
        <div class="date">Weekly Recaps</div>
        <div class="updated">Updated {time_str} · {len(sorted_sums)} weeks archived</div>
      </div>
    </div>
    <nav class="section-nav">
      <a class="nav-item nav-ext" href="index.html">← Today</a>
      <a class="nav-item nav-ext" href="week.html">📅 This Week</a>
    </nav>
  </header>

  <main style="max-width:860px">
    <h2 class="section-heading" style="color:#818cf8;margin-bottom:24px">
      📋 Weekly Recaps <span class="pill">{len(sorted_sums)} weeks</span>
    </h2>
    <p style="color:var(--muted);font-size:.82rem;margin-bottom:28px">
      Catch up on what you missed. Each recap shows the week's top cross-source stories
      and article counts per section. New entries are added automatically each week.
    </p>
{cards_html}
  </main>

  <footer>
    <a href="index.html" style="color:inherit">← Today's Feed</a> &nbsp;|&nbsp;
    <a href="week.html" style="color:inherit">📅 Weekly Digest</a> &nbsp;|&nbsp;
    Updated {date_str}
  </footer>

  <button id="back-top" title="Back to top">↑</button>

  <script>
    const searchInput = document.getElementById('search');
    searchInput.addEventListener('input', () => {{
      const q = searchInput.value.toLowerCase().trim();
      document.querySelectorAll('.recap-card').forEach(card => {{
        card.style.display = !q || card.textContent.toLowerCase().includes(q) ? '' : 'none';
      }});
    }});

    const html     = document.documentElement;
    const themeBtn = document.getElementById('theme-btn');
    const saved    = localStorage.getItem('theme') || 'dark';
    html.setAttribute('data-theme', saved);
    themeBtn.textContent = saved === 'dark' ? '☀️' : '🌙';
    themeBtn.addEventListener('click', () => {{
      const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      html.setAttribute('data-theme', next);
      themeBtn.textContent = next === 'dark' ? '☀️' : '🌙';
      localStorage.setItem('theme', next);
    }});

    const backTop = document.getElementById('back-top');
    window.addEventListener('scroll', () => {{
      backTop.style.display = window.scrollY > 300 ? 'flex' : 'none';
    }}, {{ passive: true }});
    backTop.addEventListener('click', () => window.scrollTo({{ top: 0, behavior: 'smooth' }}));
  </script>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    now         = datetime.now(timezone.utc)
    week_cutoff = now - timedelta(hours=WEEK_HOURS)
    main_cutoff = now - timedelta(hours=LOOKBACK_HOURS)

    print(f"\n Finance News Feed")
    print(f" {now.strftime('%Y-%m-%d %H:%M UTC')}  |  daily {LOOKBACK_HOURS}h / weekly {WEEK_HOURS}h\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sections_raw_main: dict = {}
    sections_raw_week: dict = {}

    print("[Fetching feeds]")
    fetched = fetch_all(now)
    print(f"  → {len(fetched)} feeds\n")

    feed_stats: list[dict] = []
    for name, config in FEEDS.items():
        print(f"[{config['icon']} {name}]")
        raw_week, stats = parse_section(name, config, fetched, week_cutoff, now)
        feed_stats.extend(stats)
        for st in stats:
            status = st["error"] or f"{st['kept']:3} kept / {st['fresh']:3} fresh / {st['entries']:3} in feed"
            print(f"  {'✗' if st['error'] or not st['fresh'] else '✓'} {st['label']:28} {status}  ({st['secs']}s)")
        raw_main = [a for a in raw_week if a["pub"] >= main_cutoff]
        sections_raw_week[name] = raw_week
        sections_raw_main[name] = raw_main
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

    print("[🔥 Selecting stories]")
    top_stories, picked_main = select_stories(sections_raw_main, MAX_PER_SECTION, now,
                                              LOOKBACK_HOURS, by_coverage=False)
    top_stories_week, picked_week = select_stories(sections_raw_week, MAX_PER_SECTION_WEEK, now,
                                                   WEEK_HOURS, by_coverage=True)
    sections_main = {name: (FEEDS[name], arts) for name, arts in picked_main.items()}
    sections_week = {name: (FEEDS[name], arts) for name, arts in picked_week.items()}
    print(f"  → top stories: {len(top_stories)} daily / {len(top_stories_week)} weekly")
    for name in FEEDS:
        print(f"  → {name}: {len(picked_main[name])} daily / {len(picked_week[name])} weekly")
    print()

    print("[📊 Fear & Greed Index]")
    fear_greed = fetch_fear_greed()
    if fear_greed:
        print(f"  → {fear_greed['score']} ({fear_greed['rating']})\n")
    else:
        print("  → unavailable\n")

    print("[🔥 Trending Companies]")
    trending = find_trending(sections_raw_main)
    print(f"  → {[t for t, _ in trending[:6]]}\n")

    print("[📋 Weekly Summaries]")
    summaries    = load_summaries()
    week_summary = build_week_summary(top_stories_week, sections_raw_week, now)
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
    page = build_html(sections_main, top_stories, now, fear_greed, trending, health)
    OUTPUT_FILE.write_text(page, encoding="utf-8")

    week_page = build_week_html(sections_week, top_stories_week, now, fear_greed)
    WEEK_FILE.write_text(week_page, encoding="utf-8")

    recaps_page = build_recaps_html(summaries, now, fear_greed)
    RECAPS_FILE.write_text(recaps_page, encoding="utf-8")

    print(f" Saved → {OUTPUT_FILE}")
    print(f" Saved → {WEEK_FILE}")
    print(f" Saved → {RECAPS_FILE}")
    print(f' Run:   open "{OUTPUT_FILE}"\n')


if __name__ == "__main__":
    main()
