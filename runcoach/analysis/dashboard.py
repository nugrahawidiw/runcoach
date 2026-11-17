"""Static HTML dashboard fed by the cache (roadmap P2).

One self-contained file: inline CSS, inline SVG, no scripts, no fonts, no network. It opens from disk and
survives being emailed or copied to a phone, which a page that fetches a chart library does not.

The roadmap names the previous hand-made dashboard as a design reference. That page is not in the
repository, so this is built from what the code already produces rather than from a copy of it: the weekly
table, the CTL/ATL/TSB series, and the most recent run's pace and cadence chart.
"""

from __future__ import annotations

import datetime as dt
import html

from ..config import Profile
from ..metrics.pace import fmt_pace, fmt_time
from .charts import pace_cadence_svg

W, H = 900, 220
PAD_L, PAD_R, PAD_T, PAD_B = 48, 16, 16, 34

CSS = """
:root { --ink:#1b1b1b; --muted:#6b6b6b; --line:#e2e2e2; --bg:#ffffff; --accent:#1f4f82; }
* { box-sizing: border-box; }
body { margin:0; padding:24px; background:var(--bg); color:var(--ink);
       font:14px/1.5 -apple-system, Segoe UI, Roboto, sans-serif; }
h1 { font-size:20px; margin:0 0 2px; }
h2 { font-size:15px; margin:28px 0 8px; font-weight:600; }
.sub { color:var(--muted); margin:0 0 8px; }
table { border-collapse:collapse; width:100%; max-width:900px; }
th, td { text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); white-space:nowrap; }
th { color:var(--muted); font-weight:600; }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
.card { border:1px solid var(--line); border-radius:8px; padding:12px 16px; margin:0 12px 12px 0;
        display:inline-block; min-width:128px; }
.card .k { color:var(--muted); font-size:12px; }
.card .v { font-size:22px; font-variant-numeric:tabular-nums; }
footer { color:var(--muted); margin-top:28px; font-size:12px; }
svg { max-width:100%; height:auto; }
"""


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def load_svg(points: list) -> str:
    """CTL, ATL and TSB over time. `points` are LoadPoint records from metrics.load.load_series."""
    if not points:
        return "<p class='sub'>No load data.</p>"
    values = [v for p in points for v in (p.ctl, p.atl, p.tsb)]
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    lo, hi = lo - span * 0.1, hi + span * 0.1

    def x(i: int) -> float:
        return PAD_L + i * (W - PAD_L - PAD_R) / max(len(points) - 1, 1)

    def y(v: float) -> float:
        return (H - PAD_B) - (v - lo) * (H - PAD_B - PAD_T) / (hi - lo)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="CTL, ATL and TSB over time"><rect width="{W}" height="{H}" fill="#ffffff"/>']
    # Only draw the zero line when zero is actually in range. Otherwise it lands outside the plot and
    # strikes through the legend, which is what the first rendering of this chart did.
    if lo <= 0 <= hi:
        out.append(f'<line x1="{PAD_L}" y1="{y(0):.1f}" x2="{W - PAD_R}" y2="{y(0):.1f}" stroke="#cccccc" '
                   f'stroke-dasharray="4 4"/>')
        out.append(f'<text x="{PAD_L - 6}" y="{y(0) + 4:.1f}" text-anchor="end" font-size="10" '
                   f'fill="#999999">0</text>')
    for attr, colour, dash in (("ctl", "#1f4f82", ""), ("atl", "#9a3a2a", 'stroke-dasharray="6 4"'),
                               ("tsb", "#2f7a46", 'stroke-dasharray="2 3"')):
        pts = " ".join(f"{x(i):.1f},{y(getattr(p, attr)):.1f}" for i, p in enumerate(points))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{colour}" stroke-width="2" {dash}/>')
    out.append(f'<text x="{PAD_L}" y="{H - 8}" font-size="11" fill="#1f4f82">CTL</text>'
               f'<text x="{PAD_L + 36}" y="{H - 8}" font-size="11" fill="#9a3a2a">ATL</text>'
               f'<text x="{PAD_L + 74}" y="{H - 8}" font-size="11" fill="#2f7a46">TSB</text>'
               f'<text x="{W - PAD_R}" y="{H - 8}" font-size="11" text-anchor="end" fill="#999999">'
               f'{_esc(points[0].day)} to {_esc(points[-1].day)}</text>')
    out.append("</svg>")
    return "".join(out)


def _cards(weeks: list[dict], points: list) -> str:
    latest = weeks[-1] if weeks else None
    cards = []
    if latest:
        cards.append(("This week", f"{latest['distance_m'] / 1000.0:.1f} km"))
        cards.append(("Runs", str(latest["runs"])))
        cards.append(("Time", fmt_time(latest["moving_s"])))
    if points:
        p = points[-1]
        cards += [("CTL", f"{p.ctl:.1f}"), ("ATL", f"{p.atl:.1f}"), ("TSB", f"{p.tsb:+.1f}")]
    return "".join(f"<div class='card'><div class='k'>{_esc(k)}</div><div class='v'>{_esc(v)}</div></div>"
                   for k, v in cards)


def _weeks_table(weeks: list[dict]) -> str:
    if not weeks:
        return "<p class='sub'>No weeks to show.</p>"
    head = ("<tr><th>Week (Mon-Sun)</th><th class='num'>Runs</th><th class='num'>Distance</th>"
            "<th class='num'>Time</th><th class='num'>Avg pace</th><th class='num'>Longest</th>"
            "<th class='num'>CTL</th><th class='num'>ATL</th><th class='num'>TSB</th></tr>")
    rows = []
    for w in weeks:
        pace = fmt_pace(w["avg_pace"]) if w["avg_pace"] else "-"
        nums = [str(w["runs"]), f"{w['distance_m'] / 1000.0:.2f} km", fmt_time(w["moving_s"]), pace,
                f"{w['longest_m'] / 1000.0:.2f} km",
                f"{w['ctl']:.1f}" if w["ctl"] is not None else "-",
                f"{w['atl']:.1f}" if w["atl"] is not None else "-",
                f"{w['tsb']:+.1f}" if w["tsb"] is not None else "-"]
        cells = "".join(f"<td class='num'>{_esc(n)}</td>" for n in nums)
        rows.append(f"<tr><td>{_esc(w['week_start'])}</td>{cells}</tr>")
    return f"<table>{head}{''.join(rows)}</table>"


def render_html(weeks: list[dict], points: list, latest_report: dict | None = None,
                profile: Profile | None = None, generated: dt.date | None = None) -> str:
    """The whole page. `generated` is passed in rather than read from the clock, so output is reproducible."""
    profile = profile or Profile()
    chart = pace_cadence_svg(latest_report, profile) if latest_report else ""
    latest_title = ""
    if latest_report:
        latest_title = (f"{_esc(latest_report.get('name'))} - {_esc(latest_report.get('date'))}, "
                        f"{latest_report['distance_km']:.2f} km in {_esc(latest_report['moving'])}")
    stamp = f"Generated {generated.isoformat()}" if generated else "Generated from the local cache"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>runcoach dashboard</title>"
        f"<style>{CSS}</style></head><body>"
        "<h1>runcoach</h1>"
        f"<p class='sub'>{_esc(stamp)}</p>"
        f"{_cards(weeks, points)}"
        "<h2>Training load</h2>"
        f"{load_svg(points)}"
        "<h2>Weeks</h2>"
        f"{_weeks_table(weeks)}"
        + (f"<h2>Latest run</h2><p class='sub'>{latest_title}</p>{chart}" if latest_report else "")
        + "<footer>Self-contained: no scripts, no external styles, no network. "
          "Built from the local cache by <code>runcoach dashboard</code>.</footer>"
          "</body></html>"
    )
