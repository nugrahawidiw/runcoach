"""The training plan as data: load it, compare it with what was actually run, export it as .ics.

TOML rather than YAML: `tomllib` is in the standard library and `profile.toml` already uses it, so the plan
costs no new dependency. Only the .ics export needs one (`icalendar`, the `ics` extra), and it is imported
lazily so everything else works without it. The roadmap asks for that library by name because a hand-built
.ics previously broke on line folding.
"""

from __future__ import annotations

import datetime as dt
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..metrics.pace import fmt_pace, parse_time

MATCH_KM = 0.25        # a planned session matches an activity on the same day; distance is only reported


@dataclass(frozen=True)
class PlannedSession:
    date: dt.date
    kind: str
    title: str = ""
    distance_km: float | None = None
    target_pace: float | None = None        # seconds per km
    notes: str = ""

    def to_dict(self) -> dict:
        return {"date": self.date.isoformat(), "kind": self.kind, "title": self.title,
                "distance_km": self.distance_km, "target_pace": self.target_pace, "notes": self.notes}


@dataclass
class PlanComparison:
    rows: list[dict] = field(default_factory=list)

    @property
    def done(self) -> int:
        return sum(1 for r in self.rows if r["status"] == "done")

    @property
    def missed(self) -> int:
        return sum(1 for r in self.rows if r["status"] == "missed")

    @property
    def unplanned(self) -> int:
        return sum(1 for r in self.rows if r["status"] == "unplanned")


def load_plan(path: str | Path) -> list[PlannedSession]:
    """Read plan.toml. Raises ValueError on an unknown key or a bad pace, rather than ignoring it."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No plan file at {p}")
    with p.open("rb") as fh:
        raw = tomllib.load(fh)
    known = {"date", "kind", "title", "distance_km", "target_pace", "notes"}
    sessions = []
    for i, item in enumerate(raw.get("session", []), 1):
        unknown = set(item) - known
        if unknown:
            raise ValueError(f"session {i}: unknown key(s) {', '.join(sorted(unknown))}")
        if "date" not in item or "kind" not in item:
            raise ValueError(f"session {i}: both 'date' and 'kind' are required")
        pace = item.get("target_pace")
        sessions.append(PlannedSession(
            date=item["date"], kind=str(item["kind"]), title=str(item.get("title", "")),
            distance_km=item.get("distance_km"),
            target_pace=float(parse_time(pace)) if pace is not None else None,
            notes=str(item.get("notes", "")),
        ))
    return sorted(sessions, key=lambda s: (s.date, s.kind))


def compare(plan: list[PlannedSession], activities: list[dict]) -> PlanComparison:
    """Match planned sessions to activities by date. Deterministic; no clock involved.

    A planned session with an activity that day is `done`, without one it is `missed`, and an activity on a
    day with nothing planned is `unplanned`. Nothing is inferred about *which* session a run satisfied
    beyond the date: that would need session-structure detection (roadmap P1.2).
    """
    by_day: dict[dt.date, list[dict]] = {}
    for act in activities:
        stamp = act.get("start_date_local")
        if stamp:
            by_day.setdefault(dt.date.fromisoformat(stamp[:10]), []).append(act)

    rows = []
    planned_days = set()
    for s in plan:
        planned_days.add(s.date)
        acts = by_day.get(s.date, [])
        actual_km = sum(float(a.get("distance") or 0.0) for a in acts) / 1000.0 if acts else None
        actual_s = sum(int(a.get("moving_time") or 0) for a in acts) if acts else None
        rows.append({
            "date": s.date.isoformat(), "kind": s.kind, "title": s.title, "status": "done" if acts else "missed",
            "planned_km": s.distance_km, "actual_km": actual_km,
            "planned_pace": s.target_pace,
            "actual_pace": (actual_s / actual_km) if actual_km and actual_s else None,
        })
    for day in sorted(set(by_day) - planned_days):
        acts = by_day[day]
        actual_km = sum(float(a.get("distance") or 0.0) for a in acts) / 1000.0
        actual_s = sum(int(a.get("moving_time") or 0) for a in acts)
        rows.append({
            "date": day.isoformat(), "kind": "-", "title": acts[0].get("name") or "", "status": "unplanned",
            "planned_km": None, "actual_km": actual_km, "planned_pace": None,
            "actual_pace": (actual_s / actual_km) if actual_km else None,
        })
    rows.sort(key=lambda r: (r["date"], r["kind"]))
    return PlanComparison(rows)


def to_ics(plan: list[PlannedSession], calendar_name: str = "runcoach plan") -> bytes:
    """All-day events, one per planned session, via the icalendar library (it handles line folding)."""
    try:
        from icalendar import Calendar, Event
    except ModuleNotFoundError as exc:       # pragma: no cover - depends on the install extras
        raise ModuleNotFoundError(
            "The .ics export needs the 'icalendar' package: pip install -e \".[ics]\"") from exc

    cal = Calendar()
    cal.add("prodid", "-//runcoach//plan//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", calendar_name)
    for s in plan:
        ev = Event()
        summary = f"{s.kind}: {s.title}" if s.title else s.kind
        ev.add("summary", summary)
        ev.add("dtstart", s.date)                      # a date, not a datetime, makes it an all-day event
        ev.add("dtend", s.date + dt.timedelta(days=1))
        ev.add("uid", f"{s.date.isoformat()}-{s.kind}@runcoach")
        details = []
        if s.distance_km is not None:
            details.append(f"{s.distance_km:g} km")
        if s.target_pace is not None:
            details.append(f"target {fmt_pace(s.target_pace)}/km")
        if s.notes:
            details.append(s.notes)
        if details:
            ev.add("description", "; ".join(details))
        cal.add_component(ev)
    return cal.to_ical()


def render_markdown(comparison: PlanComparison) -> str:
    """Plan vs actual, one row per planned session plus any unplanned runs."""
    if not comparison.rows:
        return "Plan is empty."
    lines = [
        "| Date | Planned | Status | Planned km | Actual km | Target pace | Actual pace |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in comparison.rows:
        if r["status"] == "unplanned":
            planned = r["title"] or "(unplanned run)"
        else:
            planned = f"{r['kind']}: {r['title']}" if r["title"] else r["kind"]
        pk = f"{r['planned_km']:g}" if r["planned_km"] is not None else "-"
        ak = f"{r['actual_km']:.2f}" if r["actual_km"] is not None else "-"
        pp = fmt_pace(r["planned_pace"]) if r["planned_pace"] else "-"
        ap = fmt_pace(r["actual_pace"]) if r["actual_pace"] else "-"
        lines.append(f"| {r['date']} | {planned} | {r['status'].upper()} | {pk} | {ak} | {pp} | {ap} |")
    lines.append("")
    lines.append(f"{comparison.done} done, {comparison.missed} missed, {comparison.unplanned} unplanned.")
    return "\n".join(lines)
