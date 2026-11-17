"""Pace and cadence chart for one run, as inline SVG.

The roadmap allows matplotlib or inline SVG. Inline SVG is used because it needs no dependency at all
(CLAUDE.md: keep dependencies minimal), renders in any browser, and diffs as text. The trade-off is that
there is no PNG: if a raster image is ever needed, open the SVG and export it, or swap this module for
matplotlib behind the same function signature.

Input is the report dict from analysis.run_report.build_report, so the chart takes the same inputs as the
report. Output is a self-contained string: no external fonts, scripts or images.
"""

from __future__ import annotations

from ..config import Profile
from ..metrics.pace import fmt_pace

W, H = 900, 440
PAD_L, PAD_R, PAD_T, PAD_B = 70, 70, 40, 54

BANDS = (                       # (attribute on Profile, label, fill)
    ("tempo_band", "Tempo", "#cfe8d4"),
    ("goal_band", "Goal", "#d7e3f4"),
    ("easy_band", "Easy", "#f0e6cf"),
)


def _scale(value: float, lo: float, hi: float, out_lo: float, out_hi: float) -> float:
    if hi == lo:
        return (out_lo + out_hi) / 2.0
    return out_lo + (value - lo) * (out_hi - out_lo) / (hi - lo)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pace_cadence_svg(report: dict, profile: Profile | None = None) -> str:
    """Pace (left axis, faster upwards) and cadence (right axis) per lap, with the pace bands shaded."""
    profile = profile or Profile()
    laps = [r for r in report.get("laps") or [] if r.get("pace")]
    if not laps:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
                f'<rect width="{W}" height="{H}" fill="#ffffff"/>'
                f'<text x="{W // 2}" y="{H // 2}" text-anchor="middle" font-family="sans-serif" '
                f'font-size="16" fill="#333333">No laps with pace data</text></svg>')

    paces = [r["pace"] for r in laps]
    band_values = [v for name, _, _ in BANDS for v in getattr(profile, name)]
    p_lo, p_hi = min(paces + band_values), max(paces + band_values)
    span = (p_hi - p_lo) or 30.0
    p_lo, p_hi = p_lo - span * 0.08, p_hi + span * 0.08

    cads = [r["cadence_spm"] for r in laps if r.get("cadence_spm")]
    c_lo, c_hi = (min(cads) - 4, max(cads) + 4) if cads else (160.0, 190.0)

    x_lo, x_hi = PAD_L, W - PAD_R
    y_lo, y_hi = H - PAD_B, PAD_T          # faster pace (smaller seconds) is drawn higher

    def x_for(i: int) -> float:
        return _scale(i, 0, max(len(laps) - 1, 1), x_lo, x_hi)

    def y_pace(p: float) -> float:
        return _scale(p, p_lo, p_hi, y_hi, y_lo)

    def y_cad(c: float) -> float:
        return _scale(c, c_lo, c_hi, y_lo, y_hi)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'role="img" aria-label="Pace and cadence per lap">',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
           '<g font-family="sans-serif" font-size="11" fill="#333333">']

    title = f'{_esc(str(report.get("name") or "Run"))} - {_esc(str(report.get("date") or ""))}'
    out.append(f'<text x="{PAD_L}" y="24" font-size="15" font-weight="bold">{title}</text>')

    for name, label, fill in BANDS:                      # segment bands
        lo, hi = getattr(profile, name)
        top, bottom = y_pace(lo), y_pace(hi)
        out.append(f'<rect x="{x_lo}" y="{min(top, bottom):.1f}" width="{x_hi - x_lo}" '
                   f'height="{abs(bottom - top):.1f}" fill="{fill}"/>')
        out.append(f'<text x="{x_lo + 4}" y="{min(top, bottom) + 12:.1f}" fill="#666666">{label}</text>')

    out.append(f'<line x1="{x_lo}" y1="{y_lo}" x2="{x_hi}" y2="{y_lo}" stroke="#999999"/>')
    out.append(f'<line x1="{x_lo}" y1="{y_lo}" x2="{x_lo}" y2="{y_hi}" stroke="#999999"/>')
    out.append(f'<line x1="{x_hi}" y1="{y_lo}" x2="{x_hi}" y2="{y_hi}" stroke="#999999"/>')

    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):             # pace ticks, left
        p = p_lo + (p_hi - p_lo) * frac
        y = y_pace(p)
        out.append(f'<text x="{PAD_L - 8}" y="{y + 4:.1f}" text-anchor="end">{fmt_pace(p)}</text>')
    for frac in (0.0, 0.5, 1.0):                         # cadence ticks, right
        c = c_lo + (c_hi - c_lo) * frac
        out.append(f'<text x="{x_hi + 8}" y="{y_cad(c) + 4:.1f}">{c:.0f}</text>')

    for i, r in enumerate(laps):
        out.append(f'<text x="{x_for(i):.1f}" y="{y_lo + 16}" text-anchor="middle">{r["lap"]}</text>')
    out.append(f'<text x="{(x_lo + x_hi) / 2:.1f}" y="{H - 14}" text-anchor="middle">Lap</text>')
    out.append(f'<text x="{PAD_L - 8}" y="{PAD_T - 10}" text-anchor="end" fill="#1f4f82">Pace /km</text>')
    out.append(f'<text x="{W - 6}" y="{PAD_T - 10}" text-anchor="end" fill="#9a3a2a">Cadence spm</text>')

    pace_pts = " ".join(f"{x_for(i):.1f},{y_pace(r['pace']):.1f}" for i, r in enumerate(laps))
    out.append(f'<polyline points="{pace_pts}" fill="none" stroke="#1f4f82" stroke-width="2.5"/>')
    for i, r in enumerate(laps):
        out.append(f'<circle cx="{x_for(i):.1f}" cy="{y_pace(r["pace"]):.1f}" r="3" fill="#1f4f82"/>')

    cad_pts = " ".join(f"{x_for(i):.1f},{y_cad(r['cadence_spm']):.1f}"
                       for i, r in enumerate(laps) if r.get("cadence_spm"))
    if cad_pts:
        out.append(f'<polyline points="{cad_pts}" fill="none" stroke="#9a3a2a" stroke-width="2" '
                   f'stroke-dasharray="6 4"/>')

    out.append("</g></svg>")
    return "".join(out)
