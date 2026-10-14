"""Market snapshot (indices, rates, commodities, crypto) fetched at build time.

Primary source is Yahoo's chart endpoint (gives a 5-day close history for sparklines);
CNBC's quote service is the fallback. Both are unofficial, so every failure is tolerated:
a market that can't be fetched is simply left out, and the strip is hidden if all fail.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .fetch import USER_AGENT

# (key, label, Yahoo symbol, CNBC symbol, kind) — kind "yield" shows % level and bp change
MARKETS = [
    ("spx",  "S&P 500",   "^GSPC",   ".SPX",    "index"),
    ("ndx",  "Nasdaq",    "^IXIC",   ".IXIC",   "index"),
    ("dji",  "Dow",       "^DJI",    ".DJI",    "index"),
    ("us10", "10Y Yield", "^TNX",    "US10Y",   "yield"),
    ("vix",  "VIX",       "^VIX",    ".VIX",    "index"),
    ("oil",  "WTI Oil",   "CL=F",    "@CL.1",   "price"),
    ("gold", "Gold",      "GC=F",    "@GC.1",   "price"),
    ("btc",  "Bitcoin",   "BTC-USD", "BTC.CM=", "price"),
]
MARKET_TIMEOUT = 10


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=MARKET_TIMEOUT) as resp:
        return json.loads(resp.read())


def _from_yahoo(symbol: str) -> dict | None:
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(symbol) + "?range=5d&interval=1d")
    result = _get_json(url)["chart"]["result"][0]
    price  = result["meta"].get("regularMarketPrice")
    closes = [c for c in result["indicators"]["quote"][0].get("close", []) if c is not None]
    if price is None or len(closes) < 2:
        return None
    # The last close is the current/latest session; the one before it is the prior close.
    # (meta.chartPreviousClose is the close before the whole 5-day window — not "yesterday".)
    return {"price": float(price), "prev": float(closes[-2]), "spark": closes}


def _from_cnbc(symbols: list[str]) -> dict[str, dict]:
    url = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols="
           + urllib.parse.quote("|".join(symbols))
           + "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1")
    out = {}
    for q in _get_json(url)["FormattedQuoteResult"]["FormattedQuote"]:
        try:
            price  = float(str(q["last"]).replace(",", "").rstrip("%"))
            change = float(str(q["change"]).replace(",", "").rstrip("%"))
        except (KeyError, ValueError):
            continue
        out[q.get("symbol")] = {"price": price, "prev": price - change, "spark": []}
    return out


def fetch_market_snapshot() -> list[dict] | None:
    """Returns one dict per market that could be fetched, in MARKETS order, or None."""
    quotes: dict[str, dict] = {}
    for key, _, yahoo, _, _ in MARKETS:
        try:
            q = _from_yahoo(yahoo)
            if q:
                quotes[key] = q
        except Exception:
            pass
    missing = [m for m in MARKETS if m[0] not in quotes]
    if missing:
        try:
            cnbc = _from_cnbc([m[3] for m in missing])
            for key, _, _, cnbc_sym, _ in missing:
                if cnbc_sym in cnbc:
                    quotes[key] = cnbc[cnbc_sym]
        except Exception:
            pass

    snapshot = []
    for key, label, _, _, kind in MARKETS:
        q = quotes.get(key)
        if not q or not q["prev"]:
            continue
        change = q["price"] - q["prev"]
        snapshot.append({
            "key": key, "label": label, "kind": kind, "price": q["price"],
            "change": change, "change_pct": change / q["prev"] * 100, "spark": q["spark"],
        })
    return snapshot or None
