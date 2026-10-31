"""HTML page builders."""
from __future__ import annotations

import re
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ANNOUNCEMENT, HOME_PER_SECTION, PAYWALLED_PUBLISHERS, INTERNSHIP_RESOURCES, MAX_PER_SECTION, MAX_PER_SECTION_WEEK, PREMIUM_SITES
from .recaps import get_week_key
from .stories import home_picks

DESCRIPTION = "Finance headlines across markets, macro, deals, real estate, earnings and tech."


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
TOP_COLOR, CAREERS_COLOR, CALENDAR_COLOR, PREMIUM_COLOR, WIRE_COLOR = (
    "#fb923c", "#f87171", "#94a3b8", "#eab308", "#fb7185")
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


def _lock(article: dict) -> str:
    if article["source"] not in PAYWALLED_PUBLISHERS:
        return ""
    return (' <svg class="lock" viewBox="0 0 16 16" width="9" height="9" aria-label="Subscription may be required">'
            '<title>Subscription may be required</title><path fill="currentColor" d="M4 7V5a4 4 0 1 1 8 0v2h1v8H3V7h1zm2 0h4V5a2 2 0 1 0-4 0v2z"/></svg>')


def render_card(article: dict, color: str | None = None) -> str:
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
    co_attr   = f' data-co="{esc("|".join(article["companies"]))}"' if article.get("companies") else ""
    return f"""\
    <a class="card" style="--c:{c}" href="{lk}" target="_blank" rel="noopener noreferrer"{co_attr}>
      <p class="card-title">{t}</p>
      {summary_html}
      <div class="card-meta">
        <span class="card-src">{src}{_lock(article)}</span>
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


# ── Ticker ────────────────────────────────────────────────────────────────────
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


def _tick(label: str, value: str, change: str, move: float) -> str:
    cls = "flat" if abs(move) < 1e-9 else "up" if move > 0 else "down"
    return f'<span class="tick tick-{cls}"><span>{esc(label)}</span><b>{value}</b><em>{change}</em></span>'


def render_ticker(markets: list[dict] | None, rates: dict | None) -> str:
    """One rotating line of markets and rates. Renders an empty slot if there's no data."""
    by_key = {m["key"]: m for m in markets or []}

    def market(key: str, label: str | None = None) -> str:
        m = by_key.get(key)
        return _tick(label or m["label"], _fmt_price(m), _fmt_change(m), m["change"]) if m else ""

    ticks = "".join(market(k) for k in ("spx", "ndx", "dji", "vix", "oil", "gold", "btc"))
    if rates:
        tenors = {t["label"]: t for t in rates["tenors"]}

        def tenor(label: str) -> str:
            t = tenors[label]
            return _tick(label, f'{t["level"]:.2f}%', f'{t["change_bp"]:+d} bp', t["change_bp"])

        if rates["fed"]:
            fed = rates["fed"]
            ticks += _tick("Fed Funds", f'{fed["effr"]:.2f}%',
                           f'tgt {fed["target_low"]:.2f}–{fed["target_high"]:.2f}', 0)
        ticks += tenor("2Y") + market("us10", "10Y") + tenor("30Y")
        ticks += _tick("2s10s", f'{rates["spread_2s10s"]:+d} bp', f'{rates["spread_change"]:+d} bp',
                       rates["spread_change"])
        ticks += "".join(_tick(f'{b["symbol"]} {b["label"]}', f'${b["price"]:.2f}',
                               f'{b["change_pct"]:+.2f}%', b["change_pct"])
                         for b in rates["bonds"] if b["symbol"] != "LQD")
    else:
        ticks += market("us10", "10Y")
    if not ticks:
        return '<div class="ticker"></div>'
    # Two identical halves make the loop seamless; the second is hidden from screen readers
    return (f'<div class="ticker" tabindex="0" aria-label="Market snapshot"><div class="roll">'
            f'<div class="roll-set">{ticks}</div><div class="roll-set" aria-hidden="true">{ticks}</div>'
            f'</div></div>')


# ── Front page ────────────────────────────────────────────────────────────────
def render_row(article: dict) -> str:
    """A headline to click: title, then publisher and age."""
    new_badge = '<span class="new-badge">NEW</span> ' if article.get("is_new") else ""
    return (f'<a class="row" href="{esc(article["link"])}" target="_blank" rel="noopener noreferrer">'
            f'<span class="row-title">{esc(article["title"])}</span>'
            f'<span class="row-meta">{new_badge}{esc(article["source"])}{_lock(article)} · '
            f'{time_ago(article["pub"])}</span></a>')


def render_home_section(name: str, color: str, articles: list[dict]) -> str:
    sid  = slugify(name)
    rows = "".join(render_row(a) for a in home_picks(articles, HOME_PER_SECTION, name)) or \
        '<p class="empty">No stories right now.</p>'
    return f"""\
  <section class="panel" id="{sid}" style="--c:{color}">
    <h2 class="panel-heading"><i></i>{NAV_NAMES.get(name, name)}<a href="all.html#{sid}">All</a></h2>
    {rows}
  </section>
"""


def render_wire(wire: list[dict]) -> str:
    if not wire:
        return ""

    def text(item: dict) -> str:
        p = item["print"]
        if not p:
            return esc(item["title"])
        estimate = f' vs {esc(p["forecast"])} est.' if p["forecast"] else ""
        return f'<strong>{esc(p["name"])}: {esc(p["actual"])}</strong>{estimate}, prev. {esc(p["previous"])}'

    rows = "".join(
        f'<li class="wire-item"><a href="{esc(w["link"])}" target="_blank" rel="noopener noreferrer">'
        f'<span class="ts">{time_ago(w["pub"])}</span><span>{text(w)}</span></a></li>'
        for w in wire)
    return f"""\
  <section class="section" id="wire" data-section style="--c:{WIRE_COLOR}">
    <h2 class="section-heading">Headline Wire
      <a class="wire-credit" href="https://www.financialjuice.com/home" target="_blank" rel="noopener noreferrer">via FinancialJuice</a></h2>
    <ul class="wire-list">{rows}</ul>
  </section>
"""


def _render_sections_html(sections: dict, top_stories: list[dict],
                          max_per: int) -> tuple[str, str]:
    """Every story as a card, for All Stories and Weekly. Returns (jump links, sections)."""
    jumps, html = "", ""
    if top_stories:
        jumps += f'<a href="#top-stories" style="--c:{TOP_COLOR}"><i></i>Top Stories</a>'
        cards = "\n".join(render_card(a) for a in top_stories)
        html += f"""\
  <section class="section" id="top-stories" style="--c:{TOP_COLOR}" data-section>
    <h2 class="section-heading">Top Stories</h2>
    <div class="grid">
{cards}
    </div>
  </section>
"""
    for name, (config, articles) in sections.items():
        color = config["color"]
        sid   = slugify(name)
        jumps += f'<a href="#{sid}" style="--c:{color}"><i></i>{NAV_NAMES.get(name, name)}</a>'
        shown = articles[:max_per]
        cards = "\n".join(render_card(a, color) for a in shown) if shown else \
                '<p class="empty">No articles found for this period.</p>'
        html += f"""\
  <section class="section" id="{sid}" style="--c:{color}" data-section>
    <h2 class="section-heading">{name}</h2>
    <div class="grid">
{cards}
    </div>
  </section>
"""
    return jumps, html


# ── Page shell ────────────────────────────────────────────────────────────────
TABS = [("all", "all.html", "All Stories"), ("week", "week.html", "Weekly"), ("recaps", "recaps.html", "Recaps"),
        ("calendar", "calendar.html", "Calendar"), ("careers", "careers.html", "Careers")]

SEARCH_JS = """\
    const searchInput = document.getElementById('search');
    searchInput.addEventListener('input', () => {
      const q = searchInput.value.toLowerCase().trim();
      document.querySelectorAll('[data-section]').forEach(section => {
        let shown = 0;
        section.querySelectorAll('.card, .wire-item, .recap-card').forEach(item => {
          const match = !q || item.textContent.toLowerCase().includes(q);
          item.style.display = match ? '' : 'none';
          if (match) shown++;
        });
        section.style.display = shown === 0 && q ? 'none' : '';
      });
    });
    document.addEventListener('keydown', e => {
      if (e.target === searchInput) {
        if (e.key === 'Escape') {
          searchInput.value = '';
          searchInput.blur();
          searchInput.dispatchEvent(new Event('input'));
        }
        return;
      }
      if (e.key === '/' && !e.ctrlKey && !e.metaKey) { e.preventDefault(); searchInput.focus(); }
    });"""

PAGE_JS = """\
    const backTop = document.getElementById('back-top');
    window.addEventListener('scroll', () => {
      backTop.style.display = window.scrollY > 400 ? 'flex' : 'none';
    }, { passive: true });
    backTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));"""


def _page_title(heading: str, detail: str, placeholder: str | None = None) -> str:
    search = (f'<input id="search" type="search" placeholder="{placeholder}" autocomplete="off" '
              f'aria-label="{placeholder}">' if placeholder else "")
    return f'  <div class="page-title"><h1>{heading}</h1><span>{detail}</span>{search}</div>\n'


def _page(title: str, description: str, active: str, generated: datetime, markets, rates,
          main: str, footer: str = "", script: str = "") -> str:
    tabs = "".join(f'<a href="{href}"{" aria-current=page" if key == active else ""}>{label}</a>'
                   for key, href, label in TABS)
    announcement = ""
    if ANNOUNCEMENT:
        announcement = f'  <div class="announcement-banner"><span>{esc(ANNOUNCEMENT)}</span></div>\n'
    rate_note = f'2Y, 30Y and 2s10s are the Treasury close, {esc(rates["date"])}.' if rates else ""
    footer_lines = " &nbsp;|&nbsp; ".join(x for x in (footer, rate_note) if x)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{esc(description)}">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(description)}">
  <title>{esc(title)}</title>
{HEAD_ASSETS}
  <style>
{COMMON_STYLES}
  </style>
</head>
<body>
{announcement}
  <header class="hd">
    <div class="hd-row">
      <a class="logo" href="index.html">{LOGO_MARK}Finance News</a>
      {render_ticker(markets, rates)}
      <button id="theme-btn" title="Toggle light/dark mode" aria-label="Toggle light or dark mode">{THEME_ICONS}</button>
    </div>
    <div class="hd-tabs">
      <nav class="tabs">{tabs}</nav>
      <span class="updated">Updated {_et(generated).strftime("%-I:%M %p ET")}</span>
    </div>
  </header>

  <main>
{main}
  </main>

  <footer>{footer_lines}</footer>

  <button id="back-top" title="Back to top" aria-label="Back to top">↑</button>

  <script>
{THEME_JS}
{PAGE_JS}
{script}
  </script>
</body>
</html>"""


# ── Pages ─────────────────────────────────────────────────────────────────────
def build_html(sections: dict, top_stories: list[dict], generated: datetime, markets, rates,
               health: dict) -> str:
    date_str = _et(generated).strftime("%A, %B %-d, %Y")
    panels   = "".join(render_home_section(name, cfg["color"], arts)
                       for name, (cfg, arts) in sections.items())
    top_rows = "".join(render_row(a) for a in top_stories)
    counts: dict[str, int] = {}
    for a in top_stories + [a for _, arts in sections.values() for a in arts]:
        counts[a["source"]] = counts.get(a["source"], 0) + 1
    top_pubs = sorted(counts, key=counts.get, reverse=True)[:8]
    live     = sum(r["status"] == "ok" for r in health.values())
    main = f"""\
  <section class="panel panel-top" id="top-stories" style="--c:{TOP_COLOR}">
    <h2 class="panel-heading"><i></i>Top Stories<span>{date_str}</span></h2>
    <div class="top-rows">{top_rows}</div>
  </section>
  <div class="panels">
{panels}  </div>
  <p class="see-all"><a href="all.html">See every story</a></p>"""
    footer = (f"Sources today: {' &middot; '.join(esc(p) for p in top_pubs)} &amp; more"
              f" &nbsp;|&nbsp; {live}/{len(health)} feeds live")
    return _page(f"Finance News — {date_str}", DESCRIPTION, "", generated, markets, rates, main, footer)


def build_all_html(sections: dict, top_stories: list[dict], generated: datetime, markets, rates,
                   wire: list[dict]) -> str:
    jumps, sections_html = _render_sections_html(sections, top_stories, MAX_PER_SECTION)
    total = sum(len(arts) for _, arts in sections.values()) + len(top_stories)
    wire_jump = f'<a href="#wire" style="--c:{WIRE_COLOR}"><i></i>Wire</a>' if wire else ""
    main = f"""\
{_page_title("All Stories", f"{total} stories from the last 36 hours", "Search… (press / to focus)")}\
  <nav class="jump">{jumps}{wire_jump}<a href="#premium" style="--c:{PREMIUM_COLOR}"><i></i>Premium</a></nav>
{sections_html}{render_wire(wire)}
  <section class="premium-section" id="premium" style="--c:{PREMIUM_COLOR}">
    <h2 class="section-heading">Premium Sources</h2>
    <div class="premium-grid">
{render_premium_sites()}
    </div>
  </section>"""
    return _page("Finance News — All Stories", DESCRIPTION, "all", generated, markets, rates, main,
                 script=SEARCH_JS)


def build_week_html(sections: dict, top_stories: list[dict], generated: datetime, markets, rates) -> str:
    week_start = generated - timedelta(days=6)
    week_range = f"{_et(week_start).strftime('%b %-d')} – {_et(generated).strftime('%b %-d, %Y')}"
    jumps, sections_html = _render_sections_html(sections, top_stories, MAX_PER_SECTION_WEEK)
    main = f"""\
{_page_title("Weekly Digest", week_range, "Search… (press / to focus)")}\
  <nav class="jump">{jumps}</nav>
{sections_html}"""
    return _page(f"Finance News — Weekly Digest ({week_range})",
                 "Weekly finance digest — top stories from the past 7 days.", "week", generated,
                 markets, rates, main, script=SEARCH_JS)


def build_recaps_html(summaries: list, generated: datetime, markets, rates) -> str:
    """Render the weekly recaps archive page."""
    current_week = get_week_key(generated)
    sorted_sums  = sorted(summaries, key=lambda s: s["week"], reverse=True)

    cards_html = ""
    if not sorted_sums:
        cards_html = '<p class="empty" style="margin-top:24px">No past summaries yet — check back after the first full week of data is collected.</p>'
    for entry in sorted_sums:
        current_tag = '<span class="current-tag">This week</span>' if entry["week"] == current_week else ""
        bullets_html = ""
        for b in entry.get("bullets", []):
            bullets_html += (
                f'<li class="recap-bullet"><span class="recap-src">{esc(b.get("source", ""))}</span>'
                f'<a href="{esc(b.get("link", "#"))}" target="_blank" rel="noopener noreferrer">'
                f'{esc(b["headline"])}</a></li>\n')
        stats_html = "".join(f'<span class="recap-stat">{sec.split(" & ")[0].split(" ")[0]} {cnt}</span>\n'
                             for sec, cnt in entry.get("section_counts", {}).items())
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
    main = f"""\
  <div class="narrow">
{_page_title("Weekly Recaps", f"{len(sorted_sums)} weeks archived", "Search recaps…")}\
  <div data-section>
{cards_html}
  </div>
  </div>"""
    return _page("Finance News — Weekly Recaps", "Weekly finance news recaps — catch up on what you missed.",
                 "recaps", generated, markets, rates, main, script=SEARCH_JS)


def build_calendar_html(generated: datetime, markets, rates) -> str:
    main = f"""\
{_page_title("Economic Calendar", "Upcoming U.S. releases")}\
  <section class="section" id="economic-calendar" style="--c:{CALENDAR_COLOR}">
{CALENDAR_HTML}
  </section>"""
    return _page("Finance News — Economic Calendar", "Upcoming economic releases.", "calendar",
                 generated, markets, rates, main)


def build_careers_html(generated: datetime, markets, rates) -> str:
    main = f"""\
{_page_title("Careers &amp; Recruiting", "Finance internship and recruiting resources")}\
  <section class="section" id="careers-recruiting" style="--c:{CAREERS_COLOR}">
    <div class="career-grid">
{render_careers_section()}
    </div>
  </section>"""
    return _page("Finance News — Careers", "Finance internship and recruiting resources.", "careers",
                 generated, markets, rates, main)
