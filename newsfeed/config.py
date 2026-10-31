"""Settings: paths, limits, feed sources and static link lists."""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT                 = Path(__file__).resolve().parent.parent
OUTPUT_DIR           = ROOT / "output"
OUTPUT_FILE          = OUTPUT_DIR / "index.html"
WEEK_FILE            = OUTPUT_DIR / "week.html"
RECAPS_FILE          = OUTPUT_DIR / "recaps.html"
DATA_FILE            = OUTPUT_DIR / "data.json"
WEEK_DATA_FILE       = OUTPUT_DIR / "week-data.json"
SUMMARIES_DATA_FILE  = ROOT / "data" / "summaries.json"
HEALTH_FILE          = ROOT / "data" / "feed_health.json"
ARCHIVE_DIR          = ROOT / "data" / "archive"
AI_LOG_FILE          = ROOT / "data" / "ai_last.json"
ARCHIVE_KEEP_WEEKS   = 3      # current week + 2 previous (weekly page needs the last 7 days)
HEALTH_ALERT_RUNS    = 3      # warn after this many consecutive empty/failed runs (~1 day)
HEALTH_STALE_DAYS    = 4      # a feed with nothing newer than this counts as failed
FEED_ALERT_FILE      = ROOT / "data" / "feed_alerts.md"   # present only when feeds need attention
MIN_LIVE_RATIO       = 0.5    # below this share of live feeds, don't publish (keep old site)
MAX_PER_SECTION      = 12
MAX_PER_SECTION_WEEK = 20
MAX_TOP_STORIES      = 6
MAX_PER_SOURCE       = 3      # per publisher, per section
MAX_PER_COMPANY      = 3      # cards led by one company, across the whole page
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
        "url":      "https://www.linkedin.com/jobs/search/?keywords=finance%20intern",
        "featured": False,
    },
    {
        "firm":     "Handshake",
        "role":     "Campus Finance Recruiting",
        "deadline": "College-focused internship board",
        "url":      "https://joinhandshake.com/",
        "featured": False,
    },
]

# Outlets that usually need a subscription (cards get a lock; free versions preferred)
PAYWALLED_PUBLISHERS = {
    "WSJ", "FT", "Bloomberg", "Barron's", "NYT", "DealBook", "Money Stuff", "MarketWatch",
    "Seeking Alpha", "The Business Journals", "The Information", "The Economist", "PitchBook",
}
# Major outlets: weighted higher when ranking Top Stories, preferred as the card shown
MAJOR_PUBLISHERS = ["Reuters", "Bloomberg", "WSJ", "FT", "AP", "CNBC", "NYT", "DealBook",
                    "Barron's", "MarketWatch", "Axios"]
PAYWALL_RANK_FACTOR = 0.8     # paywalled stories need ~25% more importance to outrank free ones

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
            ("CNBC",          CNBC.format(15839069)),
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
            ("Google News",     gnews('site:pehub.com when:3d'), {"label": "PE Hub search"}),
            ("Google News",     gnews('site:privateequityinternational.com when:3d'), {"label": "PEI search"}),
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
