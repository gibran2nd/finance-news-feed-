"""Choosing what to show: same-story clustering, Top Stories, per-section picks, trending."""
from __future__ import annotations

import re
from datetime import datetime

from .config import MAX_PER_SOURCE, MAX_TOP_STORIES


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
