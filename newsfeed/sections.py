"""Sorting stories into sections by what they're about, not which feed they came from."""
from __future__ import annotations

import re

from .config import FEEDS

STOCKS, MACRO, DEALS = "Stock Market & Equities", "Macro & Economy", "Investment Banking & Deals"
REAL_ESTATE, EARNINGS, TECH = "Real Estate & REITs", "Earnings & Results", "Tech & Fintech"

# First match wins, so the order settles headlines that fit twice: "Bitcoin slips after Fed
# holds rates" is a crypto story, "Exxon profit beats forecasts" isn't about markets overall.
# Patterns are case-sensitive where the word is also an ordinary one ("Fed" / "fed").
SECTION_RULES = [
    (REAL_ESTATE, re.compile(r"\b(?i:reits?|commercial real estate|home sales|housing (?:market|starts)"
                             r"|mortgage rates?|office (?:market|vacanc\w+))\b")),
    (DEALS, re.compile(r"\b(?i:ipos?|s-1|mergers?|acquisitions?|acquires?|acquired|(?<!voluntary )buyouts?(?! to )"
                       r"|takeovers?|take[- ]private|going private|equity raise|spin-?offs?"
                       r"|(?:to|will) (?:buy|acquire) (?!shares|stock|the dip)|stake in|market debut"
                       r"|deal (?:for|to buy|to acquire))\b")),
    (TECH, re.compile(r"\b(?i:crypto\w*|bitcoin|ether(?:eum)?|stablecoins?|fintech|neobank|tokeni[sz]ed"
                      r"|hyperliquid)\b|\b(?:Binance|Coinbase)\b")),
    (MACRO, re.compile(r"\bFed\b|\bFed['’]s\b|\bFOMC\b|\bECB\b|\bBOJ\b|\bBOE\b|\bCPI\b|\bPCE\b|\bGDP\b"
                       r"|\b(?i:federal reserve|central banks?|bank of (?:england|japan|canada)"
                       r"|inflation|payrolls|jobs report|unemployment|rate (?:hikes?|cuts?)"
                       r"|treasury yields|recession|national debt|tariffs?|factory activity"
                       r"|(?:euro zone|eurozone|u\.?s\.?|uk|china|japan) economy)\b")),
    (EARNINGS, re.compile(r"\b(?i:earnings|q[1-4]|(?:first|second|third|fourth)[- ]quarter|quarterly"
                          r"|profits?|net (?:income|loss)|revenue|same-store|full-year|annual forecast"
                          r"|guidance|(?:beats?|tops|misses) (?:estimates|forecasts|expectations)"
                          r"|(?:raises|lifts|cuts) (?:\w+ )?(?:outlook|forecast))\b")),
    (STOCKS, re.compile(r"\b(?i:stocks|wall street|s&p(?: 500)?|nasdaq|dow|futures|sell-?off|treasuries)\b")),
    (TECH, re.compile(r"\bAI\b|\b(?i:chipmakers?|semiconductors?|data centers?|software)\b")),
]


def classify(title: str) -> str | None:
    for section, pattern in SECTION_RULES:
        if pattern.search(title):
            lowered = title.lower()
            if any(kw.lower() in lowered for kw in FEEDS[section].get("blocklist", ())):
                continue
            return section
    return None


def assign_section(lead_title: str, home: str, available: list[str]) -> str:
    """The section for a whole story, judged on the headline readers will see.

    Stories with no clear topic stay in `home`, the section whose feeds carried them, and
    real-estate trade press stays put: a REIT's earnings belong with the rest of the sector.
    """
    if home == REAL_ESTATE:
        return home
    section = classify(lead_title) or home
    return section if section in available else home
