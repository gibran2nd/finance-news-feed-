# Data branch

Written by the GitHub Action on every run (do not edit by hand):

- `archive/` — every article the site kept, one file per ISO week (last 3 weeks)
- `summaries.json` — weekly recaps shown on recaps.html
- `feed_health.json` — per-source status; sources failing 3 runs in a row are flagged
- `ai_last.json` — the last Claude call: brief, merges, summary stats, token usage and cost

Kept off `main` so code history stays readable.
