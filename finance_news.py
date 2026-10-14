#!/usr/bin/env python3
"""
Finance News Feed
-----------------
Fetches finance/investment banking RSS feeds and generates a styled HTML dashboard.

Usage:
  python3 finance_news.py           # run manually
  open output/index.html            # view the page

Scheduling: see setup.sh (launchd, runs daily at 7 AM)
"""
from newsfeed.build import main

if __name__ == "__main__":
    main()
