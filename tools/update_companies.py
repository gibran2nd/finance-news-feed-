#!/usr/bin/env python3
"""Regenerate newsfeed/data/companies.json (used for the Trending bar).

Pulls the S&P 500 list from Wikipedia, cleans names into the forms headlines use,
and merges hand-maintained aliases and notable non-S&P companies. Run occasionally:
  python3 tools/update_companies.py
"""
import html
import json
import re
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "newsfeed" / "data" / "companies.json"
SUFFIX_RE = re.compile(
    r"(,?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.?|Holdings?|Group|plc|"
    r"Ltd\.?|Limited|N\.V\.|S\.A\.|SE|AG|& Co\.?|Companies|Enterprises|Industries|"
    r"International|Worldwide|Brands|Technologies|Platforms))+$")

# Short forms that are ordinary words (title-case headlines would false-match them)
AMBIGUOUS = {
    "Target", "Southern", "Block", "Visa", "Progressive", "Ball", "Fox", "Gap", "Match",
    "Equity", "Public", "Trade", "Global", "General", "American", "United", "First",
    "Booking", "Oracle Health", "Expand", "Copart", "Monster", "Insulet", "Assurant",
    "Corning", "Masco", "Snap-on", "Henry", "Ross", "Dollar", "Discover", "Principal",
    "Prudential", "Allstate", "Interpublic", "Hess", "Dover", "Avery", "Mosaic", "Cardinal",
    "Generac", "Garmin", "Paycom", "Leidos", "Textron", "Waters", "Republic", "Regency",
    "Realty", "Welltower", "Ventas", "Darden", "Hershey", "Hormel", "Lennar", "Pool",
    "Builders", "Quanta", "Jabil", "Amcor", "Steel", "Nucor", "News", "Universal",
    "Fortive", "Tapestry", "Revvity", "Veralto", "Vistra", "Solventum", "Constellation",
    "Carrier", "Otis", "Edison", "Entergy", "Evergy", "Eversource", "Exelon",
    "Dow", "Nasdaq", "Williams", "Carnival", "Travelers", "Coherent", "Ferguson", "Tyler",
    "Rollins", "Cooper", "Everest", "Hartford", "Flex", "TKO", "APA", "Casey's", "Yum!",
}

# canonical display name → extra aliases (also overrides the cleaned S&P name)
MANUAL = {
    "JPMorgan": ["JPMorgan Chase", "JP Morgan", "J.P. Morgan"],
    "Bank of America": ["BofA"],
    "Goldman Sachs": ["Goldman"],
    "Morgan Stanley": [],
    "Citigroup": ["Citi"],
    "Wells Fargo": [],
    "Google": ["Alphabet"],
    "Meta": ["Meta Platforms", "Facebook"],
    "Berkshire Hathaway": ["Berkshire"],
    "Exxon": ["Exxon Mobil", "ExxonMobil"],
    "UnitedHealth": ["UnitedHealth Group", "UNH"],
    "Johnson & Johnson": ["J&J"],
    "Procter & Gamble": ["P&G"],
    "Disney": ["Walt Disney"],
    "Eli Lilly": ["Lilly"],
    "AMD": ["Advanced Micro Devices"],
    "Schwab": ["Charles Schwab"],
    "Apollo": ["Apollo Global"],
    "American Express": ["Amex"],
    "Lowe's": [],
    "Home Depot": [],
    "General Motors": ["GM"],
    "GE Aerospace": ["GE"],
    "IBM": [],
    "Micron": ["Micron Technology"],
    "Warner Bros. Discovery": ["Warner Bros"],
    "Target": ["Target Corp"],
    "Visa": ["Visa Inc"],
    "Block": ["Block Inc"],
    "Southern Company": [],
    "Apple": [], "Amazon": [], "Microsoft": [], "Nvidia": ["NVIDIA"], "Tesla": [],
    "Intel": [], "Oracle": [], "Netflix": [], "Salesforce": [], "Adobe": [], "Uber": [],
    "Boeing": [], "Ford": ["Ford Motor"], "Walmart": [], "Costco": [], "PepsiCo": ["Pepsi"],
    "Coca-Cola": [], "McDonald's": [], "Starbucks": [], "Nike": [], "Chipotle": [],
    "BlackRock": [], "Blackstone": [], "KKR": [], "Broadcom": [], "Qualcomm": [],
    "Palantir": [], "CrowdStrike": [], "Kimberly-Clark": [], "Kenvue": [], "PayPal": [],
    # notable companies outside the S&P 500
    "OpenAI": [], "Anthropic": [], "SpaceX": [], "xAI": [], "Stripe": [], "Databricks": [],
    "Samsung": [], "TSMC": ["Taiwan Semiconductor"], "ASML": [], "Toyota": [], "Honda": [],
    "Nestle": ["Nestlé"], "LVMH": [], "Shell": [], "BP": [], "HSBC": [], "UBS": [],
    "Barclays": [], "Deutsche Bank": [], "Santander": [], "SoftBank": [], "Alibaba": [],
    "Tencent": [], "BYD": [], "Aramco": ["Saudi Aramco"], "Arm Holdings": [], "Carlyle": [],
    "TPG": [], "Bain Capital": [], "LSEG": ["London Stock Exchange Group"], "Glencore": [],
    "Rio Tinto": [], "BHP": [], "Novo Nordisk": [], "Sony": [], "Nintendo": [],
    "Volkswagen": [], "Stellantis": [], "Siemens": [], "SAP": [], "Shein": [], "ByteDance": [],
    "TikTok": [], "Huawei": [], "Xiaomi": [], "Temu": [], "Kroger": [], "Albertsons": [],
    "Binance": [], "Jio": ["Jio Platforms"], "OPay": ["Opay"], "Reliance": ["Reliance Industries"],
    "Kalshi": [], "Polymarket": [], "Revolut": [], "Klarna": [], "Mubadala": [],
}


def fetch_sp500() -> list[dict]:
    req = urllib.request.Request("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                                 headers={"User-Agent": "FinanceNewsFeed/2.0"})
    page = urllib.request.urlopen(req, timeout=30).read().decode()
    table = page[page.index('id="constituents"'):]
    table = table[:table.index("</table>")]
    text = lambda c: html.unescape(re.sub(r"<[^>]+>", "", c)).strip(" |\n")
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) >= 3:
            rows.append({"ticker": text(cells[0]), "name": text(cells[1]), "sector": text(cells[2])})
    return rows


def clean(name: str) -> str:
    name = re.sub(r"\s*\(.*?\)", "", name)          # "(Class A)"
    name = re.sub(r"^The\s+", "", name)
    return SUFFIX_RE.sub("", name).strip(" ,")


def main() -> None:
    companies: dict[str, set] = {}
    all_aliases = {a for display, extra in MANUAL.items() for a in [display, *extra]}
    for row in fetch_sp500():
        full, short = re.sub(r"\s*\(.*?\)", "", row["name"]).strip(), clean(row["name"])
        if full in all_aliases or short in all_aliases:
            continue                                  # covered by MANUAL
        display = full if (short in AMBIGUOUS or len(short) < 3) else short
        companies.setdefault(display, set()).add(display)
    for display, extra in MANUAL.items():
        # an ambiguous display name (e.g. "Target") is shown but only matched via its aliases
        companies.setdefault(display, set()).update(
            [*extra] + ([] if display in AMBIGUOUS else [display]))
    out = [{"name": d, "aliases": sorted(a, key=len, reverse=True)} for d, a in sorted(companies.items())]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(out)} companies → {OUT}")


if __name__ == "__main__":
    main()
