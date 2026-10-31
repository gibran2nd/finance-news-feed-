"""Claude-powered extras: Morning Brief, same-story merging, concise card summaries.

Everything here is optional. Without ANTHROPIC_API_KEY (or the anthropic package), or if a
request fails, the site is built exactly as before. Claude only sees headlines and the
publishers' own summaries, and is told to use nothing else; condensed summaries containing
a number that isn't in the source text are rejected.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from .config import AI_LOG_FILE

AI_MODEL          = "claude-haiku-5-5"
MAX_CANDIDATES    = 150     # stories offered for merging / the brief
BRIEF_ITEMS       = 5
SUMMARY_MAX_CHARS = 180
CONDENSE_MIN_CHARS = 140    # shorter publisher summaries are already concise
# USD per million tokens (input, output) — for the cost line in data/ai_last.json
PRICE_PER_MTOK    = (0.10, 0.50)

SYSTEM_PROMPT = """You help run a finance news website read by students and early-career \
professionals interested in markets, investment banking, private equity and the economy.
You work only from the headlines and publisher summaries you are given. Never add facts, \
numbers, names or claims that are not stated in that text. If something is unclear, leave it out."""

MERGE_BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "duplicate_groups": {
            "type": "array",
            "items": {"type": "array", "items": {"type": "integer"}},
        },
        "brief": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "detail":   {"type": "string"},
                    "story_id": {"type": "integer"},
                },
                "required": ["headline", "detail", "story_id"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["duplicate_groups", "brief"],
    "additionalProperties": False,
}

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summaries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "summary": {"type": "string"}},
                "required": ["id", "summary"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summaries"],
    "additionalProperties": False,
}

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")


# Internal metadata that must never reach readers, even if the model repeats it
_METADATA_RE = re.compile(r",?\s*(?:a story\s+)?covered by \d+ outlets?,?(?:\s+according to [^.,]+)?",
                          re.IGNORECASE)


def _clean_detail(text: str) -> str:
    return _METADATA_RE.sub("", text).strip()


class AI:
    """One instance per build; collects results and usage for data/ai_last.json."""

    def __init__(self) -> None:
        self.client = None
        self.log: dict = {"model": AI_MODEL, "calls": [], "errors": []}
        if not os.environ.get("ANTHROPIC_API_KEY"):
            self.log["errors"].append("ANTHROPIC_API_KEY not set — AI features skipped")
            return
        try:
            import anthropic
            self.client = anthropic.Anthropic(timeout=120.0, max_retries=2)
        except ImportError:
            self.log["errors"].append("anthropic package not installed — AI features skipped")

    @property
    def enabled(self) -> bool:
        return self.client is not None

    # ── low-level call ────────────────────────────────────────────────────────
    def _call(self, name: str, prompt: str, schema: dict) -> dict | None:
        if not self.client:
            return None
        try:
            response = self.client.messages.create(
                model=AI_MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "medium",
                               "format": {"type": "json_schema", "schema": schema}},
            )
        except Exception as e:
            self.log["errors"].append(f"{name}: {type(e).__name__}: {e}")
            return None
        usage = response.usage
        cost  = (usage.input_tokens * PRICE_PER_MTOK[0]
                 + usage.output_tokens * PRICE_PER_MTOK[1]) / 1_000_000
        self.log["calls"].append({"name": name, "stop_reason": response.stop_reason,
                                  "input_tokens": usage.input_tokens,
                                  "output_tokens": usage.output_tokens,
                                  "cost_usd": round(cost, 5)})
        if response.stop_reason != "end_turn":           # refusal, max_tokens, …
            self.log["errors"].append(f"{name}: stopped with {response.stop_reason}")
            return None
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            self.log["errors"].append(f"{name}: bad JSON: {e}")
            return None

    # ── 1. merge near-duplicate stories + write the Morning Brief ────────────
    def merge_and_brief(self, clusters: list[dict], rank) -> tuple[list[list[int]], list[dict]]:
        """Returns (cluster-id groups to merge, brief items with their article)."""
        if not self.enabled:
            return [], []
        reps = []
        for c in clusters:
            best = max(c["articles"], key=rank)
            reps.append((rank(best), c, best))
        reps.sort(key=lambda r: r[0], reverse=True)
        reps = reps[:MAX_CANDIDATES]
        lines = []
        for _, c, a in reps:
            summary = a["summary"][:160]
            lines.append(f'{c["id"]} | {a["section"]} | {len(c["publishers"])} outlets | '
                         f'{a["source"]} | {a["title"]}' + (f" | {summary}" if summary else ""))
        prompt = f"""Here are today's candidate stories, one per line:
id | section | number of outlets covering it | publisher | headline | publisher summary

{chr(10).join(lines)}

Task 1 — duplicate_groups: list groups of ids that report the SAME specific news event \
(the same company announcement, deal, data release, statement or incident), even when worded \
differently. Stories that merely share a topic, company or theme are NOT duplicates. \
Be conservative; omit anything you are unsure about. Each group needs 2+ ids.

Task 2 — brief: pick the {BRIEF_ITEMS} most important stories for finance readers today \
(weigh market impact and how many outlets cover it; cover {BRIEF_ITEMS} different events). For each:
- headline: plain-English, at most 10 words
- detail: one sentence, at most 30 words, saying what happened and why it matters — using only \
facts stated in the headline/summary above
- story_id: the id of the story

Write for readers: never mention outlet counts, publishers, ids, or how this list was made."""
        data = self._call("merge_and_brief", prompt, MERGE_BRIEF_SCHEMA)
        if not data:
            return [], []
        valid  = {c["id"]: (c, a) for _, c, a in reps}
        groups = [[i for i in dict.fromkeys(g) if i in valid] for g in data["duplicate_groups"]]
        groups = [g for g in groups if len(g) >= 2]
        brief, used = [], set()
        for item in data["brief"]:
            sid = item["story_id"]
            if sid not in valid or sid in used:
                continue
            used.add(sid)
            brief.append({"headline": item["headline"].strip()[:90],
                          "detail": _clean_detail(item["detail"])[:260],
                          "article": valid[sid][1]})
        self.log["merge_groups"] = [[valid[i][1]["title"] for i in g] for g in groups]
        self.log["brief"] = [{k: b[k] for k in ("headline", "detail")} | {"link": b["article"]["link"]}
                             for b in brief]
        return groups, brief[:BRIEF_ITEMS]

    # ── 2. concise one-line card summaries ───────────────────────────────────
    def condense_summaries(self, articles: list[dict]) -> None:
        """Adds a["summary_short"] to cards whose publisher summary can be condensed."""
        todo = [a for a in articles if len(a.get("summary", "")) > CONDENSE_MIN_CHARS]
        if not self.enabled or not todo:
            return
        lines = [f"{i} | {a['title']} | {a['summary']}" for i, a in enumerate(todo)]
        prompt = f"""For each story below (id | headline | publisher summary), write one concise \
line (at most 25 words) for a news card that tells a busy reader what happened, so they can decide \
whether to open the article. Do not repeat the headline word for word; add the most useful detail \
from the summary. Use only facts in the given text.

{chr(10).join(lines)}"""
        data = self._call("condense_summaries", prompt, SUMMARY_SCHEMA)
        if not data:
            return
        rejected = 0
        for item in data["summaries"]:
            i, text = item["id"], item["summary"].strip()
            if not 0 <= i < len(todo) or not text or len(text) > SUMMARY_MAX_CHARS:
                continue
            a = todo[i]
            source_text = f"{a['title']} {a['summary']}"
            # grounding check: every number in the summary must appear in the source text
            if any(n not in source_text for n in _NUMBER_RE.findall(text)):
                rejected += 1
                continue
            a["summary_short"] = text
        self.log["summaries"] = {"requested": len(todo), "rejected_ungrounded": rejected,
                                 "applied": sum("summary_short" in a for a in todo)}

    def save_log(self, now: datetime) -> None:
        self.log["generated"]      = now.isoformat(timespec="minutes")
        self.log["total_cost_usd"] = round(sum(c["cost_usd"] for c in self.log["calls"]), 5)
        AI_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        AI_LOG_FILE.write_text(json.dumps(self.log, indent=1, ensure_ascii=False), encoding="utf-8")
