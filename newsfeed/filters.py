"""Publisher-name cleanup, junk detection and finance-relevance filtering."""
from __future__ import annotations

import re


# ── Publisher names & junk filtering ──────────────────────────────────────────
# Google News reports publishers inconsistently ("Bloomberg.com", "Financial Times")
PUBLISHER_ALIASES = {
    "pei private equity": "PEI", "bloomberg.com": "Bloomberg", "financial times": "FT", "ft.com": "FT",
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
    r"^\s*[-–—]\s",                                             # title is only "- Publisher"
    r"^reg - ",                                                # LSE regulatory filings
    r"\bcramer\b",                                             # CNBC entertainment segments
    r"^we['’]re (upgrading|downgrading|buying|selling|trimming|adding)\b",  # CNBC Investing Club
    r"^(current|today['’]s|best) .*\b(rates|accounts|cards)\b",  # evergreen rate/SEO pages
    r"^how major us stock indexes fared\b",                    # AP daily table
    r"\btfsa\b",                                               # Canadian personal-finance SEO
]), re.IGNORECASE)

# Recaps, newsletters, previews and opinion: fine as cards, but never the headline for a story
ROUNDUP_RE = re.compile("|".join([
    r"\bweek in (review|\w+ charts?)\b", r"\bweek in explainers\b", r"\bin (five|\d) charts\b",
    r"\bweek ahead\b", r"\bloom for\b", r"\bweekly\b.*\b(recap|wrap)\b", r"\bwhat['’]s news\b", r"\bmorning bid\b",
    r"^firstft\b", r"\bmarkets wrap\b", r"\bmarket talk\b", r"^newsletter\b", r"^live news\b",
    r"\btop\s?\d+\b.*\bnews\b", r"^opinion\b", r"^commentary\b", r"\b(rating )?(up|down)grade\)$",
]), re.IGNORECASE)
WEAK_PUBLISHERS = {"Seeking Alpha", "The Motley Fool", "TIKR.com", "ChartMill"}   # opinion-led


def is_roundup(title: str) -> bool:
    return bool(ROUNDUP_RE.search(title))


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
    sell-?offs?|plunges?|plunged|surges?|surged|soars?|soared|tumbles?|tumbled|
    slumps?|slumped|sinks?|sank|dips?|analysts?|bullish|bearish|activist|shareholders?|
    billion|trillion|fintech|payments?|crypto|bitcoin|stablecoins?|
    q[1-4]|shipments|deliveries|turnaround|buys|sells|divest\w*|spin-?offs?|
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


# War and arms stories mention dollars and "billion" without being market news
MILITARY_RE   = re.compile(r"\b(interceptors?|missiles?|troops|airstrikes?|warplanes?|fighter jets?)\b",
                           re.IGNORECASE)
MARKET_ANGLE_RE = re.compile(r"\b(stocks?|shares?|oil|markets?|yields?|earnings|contracts?)\b",
                             re.IGNORECASE)
# So do crime stories ("held on $3 million bond")
CRIME_RE = re.compile(r"\b(killings?|murders?|homicide|shooting|stabbing)\b", re.IGNORECASE)
# And sports ("27-19 loss to the Packers")
SPORTS_RE = re.compile(r"\b\d{1,3}-\d{1,3} (loss|win|victory)\b|\b(defensive|offensive) coordinator\b",
                       re.IGNORECASE)


def is_off_topic(title: str, filtered: bool) -> bool:
    title = title.replace("’", "'")
    if ADVICE_RE.search(title):
        return True
    if not filtered:
        return False
    if MILITARY_RE.search(title) and not MARKET_ANGLE_RE.search(title):
        return True
    if CRIME_RE.search(title) or SPORTS_RE.search(title):
        return True
    return not FINANCE_RE.search(title)


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


# Publishers sometimes update an article's headline after results but keep the preview blurb
RESULTS_TITLE_RE   = re.compile(r"\b(tops|beats|beat|misses|missed|posts|reported|reports|"
                                r"raises|cuts|lifts|hikes)\b", re.IGNORECASE)
PREVIEW_SUMMARY_RE = re.compile(r"\b(is|are) expected to\b|\bahead of (its|their)\b|"
                                r"\bwill report\b|\bset to report\b|\bwhat to (watch|expect)\b",
                                re.IGNORECASE)


def is_stale_summary(title: str, summary: str) -> bool:
    """A results headline paired with pre-results preview text."""
    return bool(RESULTS_TITLE_RE.search(title) and PREVIEW_SUMMARY_RE.search(summary))
