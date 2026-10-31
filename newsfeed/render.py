"""HTML page builders."""
from __future__ import annotations

import re
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ANNOUNCEMENT, PAYWALLED_PUBLISHERS, INTERNSHIP_RESOURCES, MAX_PER_SECTION, MAX_PER_SECTION_WEEK, PREMIUM_SITES
from .recaps import get_week_key


# ── TradingView Economic Calendar (plain string — outside f-string) ──────────
CALENDAR_HTML = """\
  <div class="tv-panel"><div class="tradingview-widget-container" style="min-height:450px">
    <div class="tradingview-widget-container__widget"></div>
    <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-events.js" async>
    {
      "colorTheme": "dark",
      "isTransparent": true,
      "width": "100%",
      "height": "450",
      "locale": "en",
      "importanceFilter": "-1,0,1,2,3",
      "countryFilter": "us"
    }
    </script>
  </div></div>"""
# Shared CSS lives in static/styles.css (inlined into each page)
COMMON_STYLES = (Path(__file__).parent / "static" / "styles.css").read_text(encoding="utf-8")

# Section accents that aren't feed sections
TOP_COLOR, CAREERS_COLOR, CALENDAR_COLOR, PREMIUM_COLOR, BRIEF_COLOR = (
    "#fb923c", "#f87171", "#94a3b8", "#eab308", "#34d399")
NAV_NAMES = {"Stock Market & Equities": "Markets", "Macro & Economy": "Macro",
             "Investment Banking & Deals": "Deals", "Real Estate & REITs": "Real Estate",
             "Earnings & Results": "Earnings", "Tech & Fintech": "Tech"}

LOGO_MARK = ('<svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><rect width="24" height="24" rx="6" fill="#34d399"/>'
             '<path d="M6 17l4.5-5 3 3L18.5 8" fill="none" stroke="#06281d" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>')
THEME_ICONS = ('<svg class="icon-sun" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">'
               '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
               '<svg class="icon-moon" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
               '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>')
FAVICON = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><rect width='24' height='24' rx='6' fill='%2334d399'/>"
           "<path d='M6 17l4.5-5 3 3L18.5 8' fill='none' stroke='%2306281d' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'/></svg>")
# Runs before the page paints so nobody gets a flash of the wrong theme
HEAD_ASSETS = f"""\
  <link rel="icon" href="{FAVICON}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;650;700&display=swap">
  <script>
    (function () {{
      var saved = null;
      try {{ saved = localStorage.getItem('theme'); }} catch (e) {{}}
      var dark = window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.setAttribute('data-theme', saved || (dark ? 'dark' : 'light'));
    }})();
  </script>"""
THEME_JS = """\
    document.getElementById('theme-btn').addEventListener('click', () => {
      const root = document.documentElement;
      const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) {}
    });"""


# ── Helpers ───────────────────────────────────────────────────────────────────
def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def time_ago(pub: datetime | None) -> str:
    if not pub:
        return ""
    diff = datetime.now(timezone.utc) - pub
    m = int(diff.total_seconds() / 60)
    if m < 60:   return f"{m}m ago"
    if m < 1440: return f"{m // 60}h ago"
    return f"{diff.days}d ago"


# ── HTML Renderers ─────────────────────────────────────────────────────────────
def _et(dt: datetime) -> datetime:
    """Display times in US Eastern (the site's readers follow US market hours)."""
    return dt.astimezone(ZoneInfo("America/New_York"))


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_card(article: dict, color: str | None = None, lead: bool = False) -> str:
    t         = esc(article["title"])
    lk        = esc(article["link"])
    src       = esc(article["source"])
    ts        = time_ago(article["pub"])
    c         = color or article.get("color", "#34d399")
    new_badge = '<span class="new-badge">NEW</span>' if article.get("is_new") else ""
    s         = esc(article.get("summary_short") or article["summary"])
    via       = (f' <span class="card-via">— {esc(article["summary_via"])}</span>'
                 if article.get("summary_via") and article["summary_via"] != article["source"] else "")
    summary_html = f'<p class="card-summary">{s}{via}</p>' if s else ""
    lock      = (' <svg class="lock" viewBox="0 0 16 16" width="9" height="9" aria-label="Subscription may be required">'
                 '<title>Subscription may be required</title><path fill="currentColor" d="M4 7V5a4 4 0 1 1 8 0v2h1v8H3V7h1zm2 0h4V5a2 2 0 1 0-4 0v2z"/></svg>'
                 if article["source"] in PAYWALLED_PUBLISHERS else "")
    co_attr   = f' data-co="{esc("|".join(article["companies"]))}"' if article.get("companies") else ""
    lead_cls  = " card-lead" if lead else ""
    outlets   = (f' <span class="card-outlets">· {article["coverage"]} outlets</span>'
                 if lead and article.get("coverage", 0) > 1 else "")
    return f"""\
    <a class="card{lead_cls}" style="--c:{c}" href="{lk}" target="_blank" rel="noopener noreferrer"{co_attr}>
      <p class="card-title">{t}</p>
      {summary_html}
      <div class="card-meta">
        <span class="card-src">{src}{lock}{outlets}</span>
        <span class="ts">{new_badge}{ts}</span>
      </div>
    </a>"""


def render_careers_section() -> str:
    cards = ""
    for item in INTERNSHIP_RESOURCES:
        featured_cls = " career-featured" if item["featured"] else ""
        cards += f"""\
    <a class="career-card{featured_cls}" href="{item['url']}" target="_blank" rel="noopener noreferrer">
      <div class="career-firm">{esc(item['firm'])}</div>
      <div class="career-role">{esc(item['role'])}</div>
      <div class="career-deadline">{esc(item['deadline'])}</div>
    </a>"""
    return cards


def render_premium_sites() -> str:
    cards = ""
    for site in PREMIUM_SITES:
        cards += f"""\
    <a class="premium-site-card" href="{site['url']}" target="_blank" rel="noopener noreferrer">
      <span class="premium-short">{esc(site['short'])}</span>
      <div class="premium-info">
        <span class="premium-name">{esc(site['name'])}</span>
        <span class="premium-desc">{esc(site['desc'])}</span>
      </div>
      <span class="premium-arrow">↗</span>
    </a>"""
    return cards


def _fmt_price(m: dict) -> str:
    if m["kind"] == "yield":
        return f"{m['price']:.2f}%"
    if m["key"] in ("oil", "gold", "btc"):
        return f"${m['price']:,.0f}" if m["price"] >= 10000 else f"${m['price']:,.2f}"
    return f"{m['price']:,.2f}"


def _fmt_change(m: dict) -> str:
    if m["kind"] == "yield":                       # yields move in basis points
        return f"{m['change'] * 100:+.0f} bp"
    return f"{m['change_pct']:+.2f}%"


def _sparkline(values: list[float]) -> str:
    if len(values) < 2:
        return ""
    w, h = 56, 18
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(values) - 1):.1f},{h - 1 - (v - lo) / span * (h - 2):.1f}"
                   for i, v in enumerate(values))
    return (f'<svg class="mkt-spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="1.5" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')


def render_market_strip(markets: list[dict] | None, generated: datetime) -> str:
    """Server-rendered market snapshot. Renders nothing if no data (never a blank widget)."""
    if not markets:
        return ""
    et     = _et(generated)
    as_of  = et.strftime("%-I:%M %p ET, %b %-d")
    items  = ""
    for m in markets:
        if abs(m["change"]) < 1e-9:
            cls = "flat"
        else:
            cls = "up" if m["change"] > 0 else "down"
        items += (f'<div class="mkt-item mkt-{cls}">'
                  f'<span class="mkt-label">{esc(m["label"])}</span>'
                  f'<span class="mkt-price">{_fmt_price(m)}</span>'
                  f'<span class="mkt-change">{_fmt_change(m)}</span>'
                  f'{_sparkline(m["spark"])}</div>')
    return (f'  <div class="mkt-strip" aria-label="Market snapshot">\n'
            f'    <div class="mkt-items">{items}</div>\n'
            f'    <span class="mkt-asof">as of {as_of}</span>\n  </div>')


def render_brief(brief: list[dict], generated: datetime) -> str:
    """The Morning Brief: Claude's 5-point summary of the day's most important stories."""
    if not brief:
        return ""
    et    = _et(generated)
    label = "Morning Brief" if et.hour < 12 else "Afternoon Brief" if et.hour < 17 else "Evening Brief"
    items = "".join(
        f'<li><div><a href="{esc(b["article"]["link"])}" target="_blank" rel="noopener noreferrer">'
        f'<strong>{esc(b["headline"])}</strong></a> {esc(b["detail"])} '
        f'<span class="brief-src">{esc(b["article"]["source"])}</span></div></li>'
        for b in brief)
    return f"""\
  <section class="brief" id="brief" style="--c:{BRIEF_COLOR}">
    <h2 class="section-heading">{label}
      <span class="brief-time">{et.strftime("%-I:%M %p ET")}</span></h2>
    <ol class="brief-list">{items}
      <li class="brief-note">Written by Claude (AI) from today's headlines and publisher summaries.
      It can make mistakes — open the linked articles for the full story.</li></ol>
  </section>
"""


def render_trending_bar(trending: list[tuple[str, int]]) -> str:
    if not trending:
        return ""
    chips = "".join(
        f'<button class="chip" data-co="{esc(t)}" onclick="filterByChip(this)" '
        f'title="{c} {"story" if c == 1 else "stories"} on this page">'
        f'{esc(t)}</button>'
        for t, c in trending
    )
    return f"""\
  <div class="trending-bar" id="trending-bar">
    <span class="trending-label">Trending</span>
    <div class="trending-chips">{chips}</div>
  </div>"""


def _render_sections_html(sections: dict, top_stories: list[dict],
                           max_per: int) -> tuple[str, str, list[str]]:
    """Returns (nav_items_html, sections_html, section_ids_list)."""
    section_ids = []
    nav_items   = ""

    def add_nav(sid: str, label: str, color: str) -> None:
        nonlocal nav_items
        nav_items += (f'    <a class="nav-item" href="#{sid}" style="--c:{color}"><i></i>{label}</a>\n')
        section_ids.append(sid)

    if top_stories:
        add_nav("top-stories", "Top Stories", TOP_COLOR)

    for name, (config, _) in sections.items():
        add_nav(slugify(name), NAV_NAMES.get(name, name), config["color"])
        if name == "Investment Banking & Deals":
            add_nav("careers-recruiting", "Careers", CAREERS_COLOR)
        if name == "Earnings & Results":
            add_nav("economic-calendar", "Calendar", CALENDAR_COLOR)

    add_nav("premium", "Premium", PREMIUM_COLOR)

    # ── Build section HTML ───────────────────────────────────────────────────
    sections_html = ""
    if top_stories:
        top_cards = "\n".join(render_card(a, lead=i == 0) for i, a in enumerate(top_stories))
        sections_html += f"""\
  <section class="section" id="top-stories" style="--c:{TOP_COLOR}" data-section>
    <h2 class="section-heading">Top Stories</h2>
    <div class="grid">
{top_cards}
    </div>
  </section>
"""

    for name, (config, articles) in sections.items():
        color = config["color"]
        sid   = slugify(name)
        shown = articles[:max_per]
        cards = "\n".join(render_card(a, color) for a in shown) if shown else \
                '<p class="empty">No articles found for this period.</p>'
        sections_html += f"""\
  <section class="section" id="{sid}" style="--c:{color}" data-section>
    <h2 class="section-heading">{name}</h2>
    <div class="grid">
{cards}
    </div>
  </section>
"""
        if name == "Investment Banking & Deals":
            sections_html += f"""\
  <section class="section" id="careers-recruiting" style="--c:{CAREERS_COLOR}" data-section>
    <h2 class="section-heading">Careers &amp; Recruiting</h2>
    <div class="career-grid">
{render_careers_section()}
    </div>
  </section>
"""
        if name == "Earnings & Results":
            sections_html += f"""\
  <section class="section" id="economic-calendar" style="--c:{CALENDAR_COLOR}" data-section>
    <h2 class="section-heading">Economic Calendar</h2>
{CALENDAR_HTML}
  </section>
"""

    return nav_items, sections_html, section_ids


def build_html(sections: dict, top_stories: list[dict], generated: datetime,
               markets: list[dict] | None, trending: list[tuple[str, int]], health: dict,
               brief: list[dict] | None = None) -> str:
    date_str  = _et(generated).strftime("%A, %B %-d, %Y")
    time_str  = _et(generated).strftime("%-I:%M %p ET")
    total     = sum(len(arts) for _, arts in sections.values()) + len(top_stories)

    nav_items, sections_html, section_ids = _render_sections_html(
        sections, top_stories, MAX_PER_SECTION
    )
    nav_items += '    <a class="nav-item nav-ext nav-first-ext" href="week.html">Weekly</a>\n'
    nav_items += '    <a class="nav-item nav-ext" href="recaps.html">Recaps</a>\n'

    market_strip    = render_market_strip(markets, generated)
    trending_bar    = render_trending_bar(trending)
    brief_html      = render_brief(brief or [], generated)
    shown_counts: dict[str, int] = {}
    for a in top_stories + [a for _, arts in sections.values() for a in arts]:
        shown_counts[a["source"]] = shown_counts.get(a["source"], 0) + 1
    top_pubs        = sorted(shown_counts, key=shown_counts.get, reverse=True)[:10]
    live_feeds      = sum(r["status"] == "ok" for r in health.values())
    footer_sources  = (f"Sources today: {' &middot; '.join(esc(p) for p in top_pubs)} &amp; more"
                       f" &nbsp;|&nbsp; {live_feeds}/{len(health)} feeds live")
    premium_html    = render_premium_sites()
    section_ids_js  = json.dumps(section_ids)

    announcement_html = ""
    if ANNOUNCEMENT:
        announcement_html = (
            '  <div class="announcement-banner" id="announcement">\n'
            f'    <span>{esc(ANNOUNCEMENT)}</span>\n'
            '    <button class="announce-close" id="announce-close" title="Dismiss">×</button>\n'
            '  </div>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Live finance news — markets, deals, macro, real estate, earnings & careers.">
  <meta property="og:title" content="Finance News Feed">
  <meta property="og:description" content="Live finance news — markets, deals, macro, real estate, earnings & careers.">
  <title>Finance News — {date_str} ({total} articles)</title>
{HEAD_ASSETS}
  <style>
{COMMON_STYLES}
  </style>
</head>
<body>

{announcement_html}{market_strip}

  <header>
    <div class="header-row">
      <a class="logo" href="index.html">{LOGO_MARK}Finance News</a>
      <div class="search-wrap">
        <input id="search" type="search" placeholder="Search… (press / to focus)" autocomplete="off">
      </div>
      <button id="theme-btn" title="Toggle light/dark mode" aria-label="Toggle light or dark mode">{THEME_ICONS}</button>
      <div class="header-meta">
        <div class="date">{date_str}</div>
        <div class="updated">Updated {time_str} · updates 5&times; each market day</div>
      </div>
    </div>
    <nav class="section-nav">
    {nav_items}
    </nav>
  </header>

{trending_bar}
  <main>
{brief_html}{sections_html}
  <section class="premium-section" id="premium" style="--c:{PREMIUM_COLOR}">
    <h2 class="section-heading">Premium Sources</h2>
    <div class="premium-grid">
{premium_html}
    </div>
  </section>
  </main>

  <footer>
    {footer_sources} &nbsp;|&nbsp;
    Updates before the open, after the open, midday, after the close &amp; evening &nbsp;|&nbsp;
    <a href="week.html" style="color:inherit">Weekly</a> &nbsp;|&nbsp;
    <a href="recaps.html" style="color:inherit">Recaps</a>
  </footer>

  <button id="back-top" title="Back to top">↑</button>

  <script>
    // ── Search & Trending filter ────────────────────────────────────────────
    const searchInput = document.getElementById('search');
    function applyFilter(match, active) {{
      let visible = 0;
      document.querySelectorAll('[data-section]').forEach(section => {{
        let sv = 0;
        section.querySelectorAll('.card').forEach(card => {{
          const ok = match(card);
          card.style.display = ok ? '' : 'none';
          if (ok) {{ sv++; visible++; }}
        }});
        section.style.display = sv === 0 && active ? 'none' : '';
      }});
      return visible;
    }}
    function clearChips() {{
      document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
    }}
    function runSearch(q) {{
      const lower = q.toLowerCase().trim();
      const visible = applyFilter(card => !lower || card.textContent.toLowerCase().includes(lower), !!lower);
      document.title = lower
        ? `Finance News — ${{visible}} results`
        : `Finance News — {date_str} ({total} articles)`;
    }}
    searchInput.addEventListener('input', () => {{ clearChips(); runSearch(searchInput.value); }});

    function filterByChip(btn) {{
      const co = btn.dataset.co;
      const turningOn = !btn.classList.contains('active');
      clearChips();
      searchInput.value = '';
      if (turningOn) {{
        btn.classList.add('active');
        applyFilter(card => (card.dataset.co || '').split('|').includes(co), true);
      }} else {{
        runSearch('');
      }}
    }}

{THEME_JS}

    // ── Back to Top ──────────────────────────────────────────────────────────
    const backTop = document.getElementById('back-top');
    window.addEventListener('scroll', () => {{
      backTop.style.display = window.scrollY > 400 ? 'flex' : 'none';
    }}, {{ passive: true }});
    backTop.addEventListener('click', () => window.scrollTo({{ top: 0, behavior: 'smooth' }}));

    // ── Announcement dismiss ─────────────────────────────────────────────────
    const announceClose = document.getElementById('announce-close');
    if (announceClose) {{
      announceClose.addEventListener('click', () => {{
        document.getElementById('announcement').style.display = 'none';
      }});
    }}

    // ── Keyboard Shortcuts ───────────────────────────────────────────────────
    const sectionIds = {section_ids_js};
    document.addEventListener('keydown', e => {{
      if (e.target === searchInput) {{
        if (e.key === 'Escape') {{
          searchInput.value = '';
          searchInput.blur();
          runSearch('');
          clearChips();
        }}
        return;
      }}
      if (e.key === '/' && !e.ctrlKey && !e.metaKey) {{ e.preventDefault(); searchInput.focus(); return; }}
      const num = parseInt(e.key, 10);
      if (!isNaN(num) && num >= 1 && num <= sectionIds.length) {{
        const el = document.getElementById(sectionIds[num - 1]);
        if (el) el.scrollIntoView({{ behavior: 'smooth' }});
      }}
    }});
  </script>
</body>
</html>"""


def build_week_html(sections: dict, top_stories: list[dict], generated: datetime,
                    markets: list[dict] | None) -> str:
    time_str   = _et(generated).strftime("%-I:%M %p ET")
    week_start = generated - timedelta(days=6)
    week_range = f"{_et(week_start).strftime('%b %-d')} – {_et(generated).strftime('%b %-d, %Y')}"
    total      = sum(len(arts) for _, arts in sections.values()) + len(top_stories)

    nav_items, sections_html, section_ids = _render_sections_html(
        sections, top_stories, MAX_PER_SECTION_WEEK
    )
    nav_items += '    <a class="nav-item nav-ext nav-first-ext" href="index.html">← Today</a>\n'
    nav_items += '    <a class="nav-item nav-ext" href="recaps.html">Recaps</a>\n'

    market_strip   = render_market_strip(markets, generated)
    premium_html   = render_premium_sites()
    section_ids_js = json.dumps(section_ids)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Weekly finance digest — top stories from the past 7 days.">
  <meta property="og:title" content="Finance News — Weekly Digest">
  <title>Finance News — Weekly Digest ({week_range})</title>
{HEAD_ASSETS}
  <style>
{COMMON_STYLES}
  </style>
</head>
<body>

{market_strip}

  <header>
    <div class="header-row">
      <a class="logo" href="index.html">{LOGO_MARK}Finance News <span class="week-badge">7-day digest</span></a>
      <div class="search-wrap">
        <input id="search" type="search" placeholder="Search… (press / to focus)" autocomplete="off">
      </div>
      <button id="theme-btn" title="Toggle light/dark mode" aria-label="Toggle light or dark mode">{THEME_ICONS}</button>
      <div class="header-meta">
        <div class="date">{week_range}</div>
        <div class="updated">Generated {time_str} · {total} articles</div>
      </div>
    </div>
    <nav class="section-nav">
    {nav_items}
    </nav>
  </header>

  <main>
{sections_html}
  <section class="premium-section" id="premium" style="--c:{PREMIUM_COLOR}">
    <h2 class="section-heading">Premium Sources</h2>
    <div class="premium-grid">
{premium_html}
    </div>
  </section>
  </main>

  <footer>
    Weekly Digest covers the past 7 days &nbsp;|&nbsp;
    <a href="index.html" style="color:inherit">← Back to Today's Feed</a> &nbsp;|&nbsp;
    <a href="recaps.html" style="color:inherit">Past Recaps</a>
  </footer>

  <button id="back-top" title="Back to top">↑</button>

  <script>
    const searchInput = document.getElementById('search');
    searchInput.addEventListener('input', () => {{
      const q = searchInput.value.toLowerCase().trim();
      document.querySelectorAll('[data-section]').forEach(section => {{
        let sv = 0;
        section.querySelectorAll('.card').forEach(card => {{
          const match = !q || card.textContent.toLowerCase().includes(q);
          card.style.display = match ? '' : 'none';
          if (match) sv++;
        }});
        section.style.display = sv === 0 && q ? 'none' : '';
      }});
    }});

{THEME_JS}

    const backTop = document.getElementById('back-top');
    window.addEventListener('scroll', () => {{
      backTop.style.display = window.scrollY > 400 ? 'flex' : 'none';
    }}, {{ passive: true }});
    backTop.addEventListener('click', () => window.scrollTo({{ top: 0, behavior: 'smooth' }}));

    const sectionIds = {section_ids_js};
    document.addEventListener('keydown', e => {{
      if (e.target === searchInput) {{
        if (e.key === 'Escape') {{ searchInput.value = ''; searchInput.blur(); searchInput.dispatchEvent(new Event('input')); }}
        return;
      }}
      if (e.key === '/' && !e.ctrlKey && !e.metaKey) {{ e.preventDefault(); searchInput.focus(); return; }}
      const num = parseInt(e.key, 10);
      if (!isNaN(num) && num >= 1 && num <= sectionIds.length) {{
        const el = document.getElementById(sectionIds[num - 1]);
        if (el) el.scrollIntoView({{ behavior: 'smooth' }});
      }}
    }});
  </script>
</body>
</html>"""


def build_recaps_html(summaries: list, generated: datetime,
                      markets: list[dict] | None) -> str:
    """Render the weekly recaps archive page."""
    date_str      = _et(generated).strftime("%B %-d, %Y")
    time_str      = _et(generated).strftime("%-I:%M %p ET")
    market_strip  = render_market_strip(markets, generated)
    current_week  = get_week_key(generated)
    sorted_sums   = sorted(summaries, key=lambda s: s["week"], reverse=True)

    cards_html = ""
    if not sorted_sums:
        cards_html = '<p class="empty" style="margin-top:24px">No past summaries yet — check back after the first full week of data is collected.</p>'
    else:
        for entry in sorted_sums:
            is_current = entry["week"] == current_week
            current_tag = '<span class="current-tag">This week</span>' if is_current else ""
            bullets_html = ""
            for b in entry.get("bullets", []):
                src_badge = f'<span class="recap-src">{esc(b.get("source",""))}</span>'
                link = esc(b.get("link", "#"))
                bullets_html += (
                    f'<li class="recap-bullet">{src_badge}'
                    f'<a href="{link}" target="_blank" rel="noopener noreferrer">'
                    f'{esc(b["headline"])}</a></li>\n'
                )

            stats_html = ""
            for sec, cnt in entry.get("section_counts", {}).items():
                short = sec.split(" & ")[0].split(" ")[0]
                stats_html += f'<span class="recap-stat">{short} {cnt}</span>\n'

            cards_html += f"""\
  <div class="recap-card">
    <div class="recap-week-label">{esc(entry['label'])} {current_tag}</div>
    <ul class="recap-bullets">
{bullets_html}
    </ul>
    <div class="recap-stats">
{stats_html}
    </div>
  </div>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Weekly finance news recaps — catch up on what you missed.">
  <meta property="og:title" content="Finance News — Weekly Recaps">
  <title>Finance News — Weekly Recaps</title>
{HEAD_ASSETS}
  <style>
{COMMON_STYLES}
  </style>
</head>
<body>

{market_strip}

  <header>
    <div class="header-row">
      <a class="logo" href="index.html">{LOGO_MARK}Finance News <span class="week-badge">Recaps</span></a>
      <div class="search-wrap">
        <input id="search" type="search" placeholder="Search recaps…" autocomplete="off">
      </div>
      <button id="theme-btn" title="Toggle light/dark mode" aria-label="Toggle light or dark mode">{THEME_ICONS}</button>
      <div class="header-meta">
        <div class="date">Weekly Recaps</div>
        <div class="updated">Updated {time_str} · {len(sorted_sums)} weeks archived</div>
      </div>
    </div>
    <nav class="section-nav">
      <a class="nav-item nav-ext" href="index.html">← Today</a>
      <a class="nav-item nav-ext" href="week.html">This Week</a>
    </nav>
  </header>

  <main style="max-width:860px">
    <h2 class="section-heading" style="--c:{TOP_COLOR}">
      Weekly Recaps <span class="pill">{len(sorted_sums)} weeks</span>
    </h2>
    <p class="recap-intro">
      Catch up on what you missed. Each recap shows the week's top cross-source stories
      and article counts per section. New entries are added automatically each week.
    </p>
{cards_html}
  </main>

  <footer>
    <a href="index.html" style="color:inherit">← Today's Feed</a> &nbsp;|&nbsp;
    <a href="week.html" style="color:inherit">Weekly Digest</a> &nbsp;|&nbsp;
    Updated {date_str}
  </footer>

  <button id="back-top" title="Back to top">↑</button>

  <script>
    const searchInput = document.getElementById('search');
    searchInput.addEventListener('input', () => {{
      const q = searchInput.value.toLowerCase().trim();
      document.querySelectorAll('.recap-card').forEach(card => {{
        card.style.display = !q || card.textContent.toLowerCase().includes(q) ? '' : 'none';
      }});
    }});

{THEME_JS}

    const backTop = document.getElementById('back-top');
    window.addEventListener('scroll', () => {{
      backTop.style.display = window.scrollY > 300 ? 'flex' : 'none';
    }}, {{ passive: true }});
    backTop.addEventListener('click', () => window.scrollTo({{ top: 0, behavior: 'smooth' }}));
  </script>
</body>
</html>"""
