"""Company-name detection in headlines (powers the Trending bar).

The name list lives in data/companies.json; regenerate it with tools/update_companies.py.
Matching is case-sensitive so "Apple" the company doesn't match "apple" the fruit.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_DATA = json.loads((Path(__file__).parent / "data" / "companies.json").read_text(encoding="utf-8"))
_ALIAS_TO_NAME = {alias: c["name"] for c in _DATA for alias in c["aliases"]}
# Longest aliases first so "Goldman Sachs" wins over "Goldman"; allow a trailing possessive
_COMPANY_RE = re.compile(
    r"(?<![\w&.-])("
    + "|".join(re.escape(a) for a in sorted(_ALIAS_TO_NAME, key=len, reverse=True))
    + r")(?:['’]s)?(?![\w&-])")


def find_companies(title: str) -> list[str]:
    """Canonical company names mentioned in a headline, in order of appearance."""
    found: list[str] = []
    for m in _COMPANY_RE.finditer(title):
        name = _ALIAS_TO_NAME[m.group(1)]
        if name not in found:
            found.append(name)
    return found
