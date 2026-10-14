"""HTML page builders."""
from __future__ import annotations

import re
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ANNOUNCEMENT, INTERNSHIP_RESOURCES, MAX_PER_SECTION, MAX_PER_SECTION_WEEK, PREMIUM_SITES
from .recaps import get_week_key


# ── TradingView Economic Calendar (plain string — outside f-string) ──────────
CALENDAR_HTML = """\
  <div class="tradingview-widget-container" style="min-height:450px">
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
  </div>"""
# Shared CSS lives in static/styles.css (inlined into each page)
COMMON_STYLES = (Path(__file__).parent / "static" / "styles.css").read_text(encoding="utf-8")


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
def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_card(article: dict, color: str | None = None) -> str:
    t         = esc(article["title"])
    lk        = esc(article["link"])
    src       = esc(article["source"])
    ts        = time_ago(article["pub"])
    c         = color or article.get("color", "#22c55e")
    age_cls   = article.get("age_class", "age-old")
    new_badge = '<span class="new-badge">NEW</span>' if article.get("is_new") else ""
    s         = esc(article.get("summary_short") or article["summary"])
    via       = (f' <span class="card-via">— {esc(article["summary_via"])}</span>'
                 if article.get("summary_via") and article["summary_via"] != article["source"] else "")
    summary_html = f'<p class="card-summary">{s}{via}</p>' if s else ""
    co_attr   = f' data-co="{esc("|".join(article["companies"]))}"' if article.get("companies") else ""
    return f"""\
    <a class="card {age_cls}" href="{lk}" target="_blank" rel="noopener noreferrer"{co_attr}>
      <div class="card-meta">
        <span class="badge" style="border-color:{c};color:{c}">{src}</span>
        <span class="ts">{new_badge}{ts}</span>
      </div>
      <p class="card-title">{t}</p>
      {summary_html}
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
    et     = generated.astimezone(ZoneInfo("America/New_York"))
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
    et    = generated.astimezone(ZoneInfo("America/New_York"))
    label = "Morning Brief" if et.hour < 12 else "Afternoon Brief" if et.hour < 17 else "Evening Brief"
    items = "".join(
        f'<li><a href="{esc(b["article"]["link"])}" target="_blank" rel="noopener noreferrer">'
        f'<strong>{esc(b["headline"])}</strong></a> {esc(b["detail"])} '
        f'<span class="brief-src">{esc(b["article"]["source"])}</span></li>'
        for b in brief)
    return f"""\
  <section class="brief" id="brief">
    <h2 class="section-heading" style="color:var(--text)">{label}
      <span class="brief-time">{et.strftime("%-I:%M %p ET")}</span></h2>
    <ol class="brief-list">{items}</ol>
    <p class="brief-note">Written by Claude (AI) from today's headlines and publisher summaries.
      It can make mistakes — open the linked articles for the full story.</p>
  </section>
"""


def render_trending_bar(trending: list[tuple[str, int]]) -> str:
    if not trending:
        return ""
    chips = "".join(
        f'<button class="chip" data-co="{esc(t)}" onclick="filterByChip(this)" '
        f'title="{c} {"story" if c == 1 else "stories"} on this page">'
        f'{esc(t)}<span class="chip-count">{c}</span></button>'
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
    key_num     = 1
    section_ids = []
    nav_items   = ""

    if top_stories:
        nav_items += f'<a class="nav-item" href="#top-stories">🔥 Top Stories <kbd>{key_num}</kbd></a>\n'
        section_ids.append("top-stories")
        key_num += 1

    for name in sections:
        sid   = slugify(name)
        first = name.split(" & ")[0].split(" ")[0]
        icon  = sections[name][0]["icon"]
        nav_items += f'    <a class="nav-item" href="#{sid}">{icon} {first} <kbd>{key_num}</kbd></a>\n'
        section_ids.append(sid)
        key_num += 1
        if name == "Investment Banking & Deals":
            nav_items += f'    <a class="nav-item" href="#careers-recruiting">💼 Careers <kbd>{key_num}</kbd></a>\n'
            section_ids.append("careers-recruiting")
            key_num += 1
        if name == "Earnings & Results":
            nav_items += f'    <a class="nav-item" href="#economic-calendar">📅 Calendar <kbd>{key_num}</kbd></a>\n'
            section_ids.append("economic-calendar")
            key_num += 1

    nav_items += f'    <a class="nav-item" href="#premium">🔒 Premium <kbd>{key_num}</kbd></a>\n'
    section_ids.append("premium")

    # ── Build section HTML ───────────────────────────────────────────────────
    sections_html = ""
    if top_stories:
        top_cards = "\n".join(render_card(a) for a in top_stories)
        sections_html += f"""\
  <section class="section" id="top-stories" data-section>
    <h2 class="section-heading" style="color:#f97316">
      🔥 Top Stories <span class="pill">{len(top_stories)}</span>
    </h2>
    <div class="grid">
{top_cards}
    </div>
  </section>
"""

    for name, (config, articles) in sections.items():
        color = config["color"]
        icon  = config["icon"]
        sid   = slugify(name)
        shown = articles[:max_per]
        count = len(shown)
        cards = "\n".join(render_card(a, color) for a in shown) if shown else \
                '<p class="empty">No articles found for this period.</p>'
        sections_html += f"""\
  <section class="section" id="{sid}" data-section>
    <h2 class="section-heading" style="color:{color}">
      {icon} {name} <span class="pill">{count}</span>
    </h2>
    <div class="grid">
{cards}
    </div>
  </section>
"""
        if name == "Investment Banking & Deals":
            sections_html += f"""\
  <section class="section" id="careers-recruiting" data-section>
    <h2 class="section-heading" style="color:#f97316">
      \U0001f4bc Careers &amp; Recruiting <span class="pill">{len(INTERNSHIP_RESOURCES)}</span>
    </h2>
    <div class="career-grid">
{render_careers_section()}
    </div>
  </section>
"""
        if name == "Earnings & Results":
            sections_html += f"""\
  <section class="section" id="economic-calendar" data-section>
    <h2 class="section-heading" style="color:#f59e0b">
      \U0001f4c5 Economic Calendar
    </h2>
{CALENDAR_HTML}
  </section>
"""

    return nav_items, sections_html, section_ids


def build_html(sections: dict, top_stories: list[dict], generated: datetime,
               markets: list[dict] | None, trending: list[tuple[str, int]], health: dict,
               brief: list[dict] | None = None) -> str:
    date_str  = generated.strftime("%A, %B %-d, %Y")
    time_str  = generated.strftime("%-I:%M %p UTC")
    total     = sum(len(arts) for _, arts in sections.values()) + len(top_stories)

    nav_items, sections_html, section_ids = _render_sections_html(
        sections, top_stories, MAX_PER_SECTION
    )
    nav_items += '    <a class="nav-item nav-ext" href="week.html">📅 Weekly</a>\n'
    nav_items += '    <a class="nav-item nav-ext" href="recaps.html">📋 Recaps</a>\n'

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
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="3600">
  <meta name="description" content="Live finance news — markets, deals, macro, real estate, earnings & careers.">
  <meta property="og:title" content="Finance News Feed">
  <meta property="og:description" content="Live finance news — markets, deals, macro, real estate, earnings & careers.">
  <title>Finance News — {date_str} ({total} articles)</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📈</text></svg>">
  <style>
{COMMON_STYLES}
  </style>
</head>
<body>

{announcement_html}{market_strip}

  <header>
    <div class="header-row">
      <div class="logo">Finance <em>News</em></div>
      <div class="search-wrap">
        <input id="search" type="search" placeholder="Search… (press / to focus)" autocomplete="off">
      </div>
      <button id="theme-btn" title="Toggle light/dark mode">☀️</button>
      <div class="header-meta">
        <div class="date">{date_str}</div>
        <div class="updated">Updated {time_str} · auto-refreshes hourly</div>
      </div>
    </div>
    <nav class="section-nav">
    {nav_items}
    </nav>
  </header>

{trending_bar}
  <main>
{brief_html}{sections_html}
  <section class="premium-section" id="premium">
    <h2 class="section-heading" style="color:var(--gold)">
      🔒 Premium Sources <span class="pill">{len(PREMIUM_SITES)}</span>
    </h2>
    <div class="premium-grid">
{premium_html}
    </div>
  </section>
  </main>

  <footer>
    {footer_sources} &nbsp;|&nbsp;
    Regenerates 3&times; daily &nbsp;|&nbsp;
    <a href="week.html" style="color:inherit">📅 Weekly</a> &nbsp;|&nbsp;
    <a href="recaps.html" style="color:inherit">📋 Recaps</a>
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

    // ── Light / Dark Mode ────────────────────────────────────────────────────
    const html     = document.documentElement;
    const themeBtn = document.getElementById('theme-btn');
    const saved    = localStorage.getItem('theme') || 'dark';
    html.setAttribute('data-theme', saved);
    themeBtn.textContent = saved === 'dark' ? '☀️' : '🌙';
    themeBtn.addEventListener('click', () => {{
      const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      html.setAttribute('data-theme', next);
      themeBtn.textContent = next === 'dark' ? '☀️' : '🌙';
      localStorage.setItem('theme', next);
    }});

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
    time_str   = generated.strftime("%-I:%M %p UTC")
    week_start = generated - timedelta(days=6)
    week_range = f"{week_start.strftime('%b %-d')} – {generated.strftime('%b %-d, %Y')}"
    total      = sum(len(arts) for _, arts in sections.values()) + len(top_stories)

    nav_items, sections_html, section_ids = _render_sections_html(
        sections, top_stories, MAX_PER_SECTION_WEEK
    )
    nav_items += '    <a class="nav-item nav-ext" href="index.html">← Today</a>\n'
    nav_items += '    <a class="nav-item nav-ext" href="recaps.html">📋 Recaps</a>\n'

    market_strip   = render_market_strip(markets, generated)
    premium_html   = render_premium_sites()
    section_ids_js = json.dumps(section_ids)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Weekly finance digest — top stories from the past 7 days.">
  <meta property="og:title" content="Finance News — Weekly Digest">
  <title>Finance News — Weekly Digest ({week_range})</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📅</text></svg>">
  <style>
{COMMON_STYLES}
  </style>
</head>
<body>

{market_strip}

  <header>
    <div class="header-row">
      <div class="logo">Finance <em>News</em> <span class="week-badge">7-DAY DIGEST</span></div>
      <div class="search-wrap">
        <input id="search" type="search" placeholder="Search… (press / to focus)" autocomplete="off">
      </div>
      <button id="theme-btn" title="Toggle light/dark mode">☀️</button>
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
  <section class="premium-section" id="premium">
    <h2 class="section-heading" style="color:var(--gold)">
      🔒 Premium Sources <span class="pill">{len(PREMIUM_SITES)}</span>
    </h2>
    <div class="premium-grid">
{premium_html}
    </div>
  </section>
  </main>

  <footer>
    Weekly Digest covers the past 7 days &nbsp;|&nbsp;
    <a href="index.html" style="color:inherit">← Back to Today's Feed</a> &nbsp;|&nbsp;
    <a href="recaps.html" style="color:inherit">📋 Past Recaps</a>
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

    const html     = document.documentElement;
    const themeBtn = document.getElementById('theme-btn');
    const saved    = localStorage.getItem('theme') || 'dark';
    html.setAttribute('data-theme', saved);
    themeBtn.textContent = saved === 'dark' ? '☀️' : '🌙';
    themeBtn.addEventListener('click', () => {{
      const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      html.setAttribute('data-theme', next);
      themeBtn.textContent = next === 'dark' ? '☀️' : '🌙';
      localStorage.setItem('theme', next);
    }});

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
    date_str      = generated.strftime("%B %-d, %Y")
    time_str      = generated.strftime("%-I:%M %p UTC")
    market_strip  = render_market_strip(markets, generated)
    current_week  = get_week_key(generated)
    sorted_sums   = sorted(summaries, key=lambda s: s["week"], reverse=True)

    cards_html = ""
    if not sorted_sums:
        cards_html = '<p class="empty" style="margin-top:24px">No past summaries yet — check back after the first full week of data is collected.</p>'
    else:
        for entry in sorted_sums:
            is_current = entry["week"] == current_week
            current_tag = '<span class="current-tag">THIS WEEK</span>' if is_current else ""
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
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Weekly finance news recaps — catch up on what you missed.">
  <meta property="og:title" content="Finance News — Weekly Recaps">
  <title>Finance News — Weekly Recaps</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📋</text></svg>">
  <style>
{COMMON_STYLES}
  </style>
</head>
<body>

{market_strip}

  <header>
    <div class="header-row">
      <div class="logo">Finance <em>News</em> <span class="week-badge">RECAPS</span></div>
      <div class="search-wrap">
        <input id="search" type="search" placeholder="Search recaps…" autocomplete="off">
      </div>
      <button id="theme-btn" title="Toggle light/dark mode">☀️</button>
      <div class="header-meta">
        <div class="date">Weekly Recaps</div>
        <div class="updated">Updated {time_str} · {len(sorted_sums)} weeks archived</div>
      </div>
    </div>
    <nav class="section-nav">
      <a class="nav-item nav-ext" href="index.html">← Today</a>
      <a class="nav-item nav-ext" href="week.html">📅 This Week</a>
    </nav>
  </header>

  <main style="max-width:860px">
    <h2 class="section-heading" style="color:#818cf8;margin-bottom:24px">
      📋 Weekly Recaps <span class="pill">{len(sorted_sums)} weeks</span>
    </h2>
    <p style="color:var(--muted);font-size:.82rem;margin-bottom:28px">
      Catch up on what you missed. Each recap shows the week's top cross-source stories
      and article counts per section. New entries are added automatically each week.
    </p>
{cards_html}
  </main>

  <footer>
    <a href="index.html" style="color:inherit">← Today's Feed</a> &nbsp;|&nbsp;
    <a href="week.html" style="color:inherit">📅 Weekly Digest</a> &nbsp;|&nbsp;
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

    const html     = document.documentElement;
    const themeBtn = document.getElementById('theme-btn');
    const saved    = localStorage.getItem('theme') || 'dark';
    html.setAttribute('data-theme', saved);
    themeBtn.textContent = saved === 'dark' ? '☀️' : '🌙';
    themeBtn.addEventListener('click', () => {{
      const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      html.setAttribute('data-theme', next);
      themeBtn.textContent = next === 'dark' ? '☀️' : '🌙';
      localStorage.setItem('theme', next);
    }});

    const backTop = document.getElementById('back-top');
    window.addEventListener('scroll', () => {{
      backTop.style.display = window.scrollY > 300 ? 'flex' : 'none';
    }}, {{ passive: true }});
    backTop.addEventListener('click', () => window.scrollTo({{ top: 0, behavior: 'smooth' }}));
  </script>
</body>
</html>"""
