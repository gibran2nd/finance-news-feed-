"""Rates and bonds: official Treasury and New York Fed data, plus bond ETF prices.

All free and keyless. Treasury's curve updates once a day after the close, so the panel shows
its own date. Each source can fail alone; the panel is hidden only if there's no curve.
"""
from __future__ import annotations

import csv
import io
import json
import urllib.request
from datetime import datetime

from .fetch import USER_AGENT
from .markets import _from_yahoo

TREASURY_URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
                "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
                "&field_tdr_date_value={year}&page&_format=csv")
EFFR_URL     = "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/1.json"
TENORS       = [("3 Mo", "3M"), ("2 Yr", "2Y"), ("10 Yr", "10Y"), ("30 Yr", "30Y")]
BOND_ETFS    = [("TLT", "Treasuries"), ("LQD", "Inv. Grade"), ("HYG", "High Yield")]
RATES_TIMEOUT = 30            # Treasury often takes about 20 seconds


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=RATES_TIMEOUT) as resp:
        return resp.read().decode("utf-8")


def parse_curve(text: str) -> dict | None:
    """Latest two days of the Treasury CSV (newest row first) as tenor levels and bp changes."""
    rows = list(csv.DictReader(io.StringIO(text)))
    if len(rows) < 2:
        return None
    latest, prior = rows[0], rows[1]
    try:
        tenors = [{"label": label, "level": float(latest[col]),
                   "change_bp": round((float(latest[col]) - float(prior[col])) * 100)}
                  for col, label in TENORS]
        spread = round((float(latest["10 Yr"]) - float(latest["2 Yr"])) * 100)
        prior_spread = round((float(prior["10 Yr"]) - float(prior["2 Yr"])) * 100)
        date = datetime.strptime(latest["Date"], "%m/%d/%Y")
    except (KeyError, ValueError):
        return None
    return {"date": date.strftime("%b %-d"), "tenors": tenors, "spread_2s10s": spread,
            "spread_change": spread - prior_spread}


def parse_effr(text: str) -> dict | None:
    try:
        rate = json.loads(text)["refRates"][0]
        return {"effr": float(rate["percentRate"]), "target_low": float(rate["targetRateFrom"]),
                "target_high": float(rate["targetRateTo"])}
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _fetch_curve(now: datetime) -> dict | None:
    for year in (now.year, now.year - 1):              # early January has too few rows
        try:
            curve = parse_curve(_get(TREASURY_URL.format(year=year)))
        except Exception:
            continue
        if curve:
            return curve
    return None


def _fetch_bonds() -> list[dict]:
    bonds = []
    for symbol, label in BOND_ETFS:
        try:
            q = _from_yahoo(symbol)
        except Exception:
            continue
        if q and q["prev"]:
            bonds.append({"symbol": symbol, "label": label, "price": q["price"],
                          "change_pct": (q["price"] - q["prev"]) / q["prev"] * 100})
    return bonds


def fetch_rates(now: datetime) -> dict | None:
    curve = _fetch_curve(now)
    if not curve:
        return None
    try:
        fed = parse_effr(_get(EFFR_URL))
    except Exception:
        fed = None
    return {**curve, "fed": fed, "bonds": _fetch_bonds()}
