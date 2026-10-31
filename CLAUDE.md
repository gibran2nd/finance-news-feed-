# Finance News Feed

A static finance news site. It fetches RSS feeds, picks and dedupes stories, adds Claude summaries, and builds HTML that GitHub Actions publishes to GitHub Pages at https://gibran2nd.github.io/finance-news-feed-. Read this file first and go to the code only for what the task needs. This repo is public, so keep private details out of it.

## Status (2026-10-31)
- Live: data overhaul, market strip, trending, importance ranking, archive, Claude layer, `data.json`, CI tests, market-hours schedule, quick-fix batch from the October audit.
- Next: (1) Story selection: sort sections by content rather than feed order, better Top Story headlines, weekly over-grouping, weak recap sources, missing summaries, remaining duplicates, trade press (PEI) outranked. (2) Redesign, mockups first, plus link-preview image.
- To check: the economic calendar's contents in a real browser. The feed-alert issue step hasn't fired yet.

## Commands
There's no virtual environment here, and `.gitignore` doesn't cover one. Make it outside the repo, then install from `requirements.txt`.
- Tests: `python -m unittest discover -s tests -t .` (needs `feedparser`; without it, three build tests fail)
- Build locally: `python finance_news.py`, then open `output/index.html`
- Company list: `python tools/update_companies.py`

## Map
`finance_news.py` calls `newsfeed/build.py`, which runs fetch, filter, select, then render.
- `config.py`: feeds, limits and link lists. Start here for settings.
- `fetch.py`: feeds to article dicts. `filters.py`: junk, relevance and publisher cleanup.
- `stories.py`: clustering, Top Stories, section picks, trending. `companies.py`: company detection, from `newsfeed/data/companies.json`.
- `ai.py`: brief, merges and summaries, with a check that numbers match the source. `markets.py`: Yahoo with a CNBC fallback.
- `render.py` and `newsfeed/static/`: the pages. `export.py`: JSON copies. `archive.py`, `recaps.py`, `health.py`: history and feed health.

## Rules
- `.github/workflows/update.yml` runs the tests first, so a failing test stops publishing. cron-job.org triggers runs on a market-hours schedule through a GitHub token that expires within a year; GitHub's own cron is a daily backup.
- Bot data lives on the `data` branch, checked out into `data/`. Never commit it to `main`. `data/` and `output/` are generated.
- The AI layer uses Haiku 5.5 at about $0.50 a month. That was a deliberate choice, so don't upgrade the model without asking.
- Work on a branch and push to `main` only when verified. A push to `main` goes to the public site.
- Audit after every step against real output, more than one pass, then finish with a larger final audit that suggests further changes.
- Redesign work: show mockups before building. Check phone widths.
- Headless Chrome won't go below 500px wide, so `--window-size=390` isn't a phone test. Use a 390px iframe.
