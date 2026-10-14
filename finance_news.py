#!/usr/bin/env python3
"""
Finance News Feed
-----------------
Fetches finance news feeds, picks and dedupes stories, and builds the site in output/.
The code lives in newsfeed/; GitHub Actions (.github/workflows/update.yml) runs this on
a market-hours schedule and publishes to GitHub Pages.

Usage:
  pip3 install -r requirements.txt
  python3 finance_news.py                        # build locally (writes output/ and data/)
  open output/index.html                         # view the page
  python3 -m unittest discover -s tests -t .     # run the tests
"""
from newsfeed.build import main

if __name__ == "__main__":
    main()
