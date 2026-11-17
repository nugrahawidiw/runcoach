"""Spot the same run cached twice, once from Strava and once from a Garmin FIT import.

Why it matters: a run present under both keys is counted twice by `load` and `weekly`, which inflates CTL
and weekly distance. Matching follows the roadmap: start times within a couple of minutes and a similar
distance.

Two choices the roadmap leaves open, both stated here rather than buried:

  * **Distance tolerance.** The roadmap says "and distance" without a number. A pair matches when the
    distance differs by no more than 100 m, or 1% of the longer run, whichever is more generous. Garmin and
    Strava routinely disagree by a few tens of metres on the same run; 1% keeps that proportional on a half
    marathon without being loose on a 5 km.
  * **Which copy wins.** Strava, by default, because it carries `suffer_score`, which is what `load`
    prefers for Relative Effort. Pass `prefer="garmin"` to keep the FIT copy instead.

Nothing is deleted from the cache. These functions only report and filter; the cached files stay where they
are, so a wrong match costs nothing but a line of output.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence

DEFAULT_MINUTES = 2.0
DEFAULT_TOL_M = 100.0
DEFAULT_TOL_PCT = 1.0

Entry = tuple[str, dict]


def source_of(key: str) -> str:
    """Where a cached activity came from, read from its cache key (`fit-...` is a FIT import)."""
    return "garmin" if str(key).startswith("fit-") else "strava"


def _start(act: dict) -> dt.datetime | None:
    stamp = act.get("start_date_local")
    if not stamp:
        return None
    try:
        return dt.datetime.fromisoformat(str(stamp).rstrip("Z"))
    except ValueError:
        return None


def _distances_match(a: float, b: float, tol_m: float, tol_pct: float) -> bool:
    return abs(a - b) <= max(tol_m, max(a, b) * tol_pct / 100.0)


def find_duplicate_groups(entries: Iterable[Entry], minutes: float = DEFAULT_MINUTES,
                          tol_m: float = DEFAULT_TOL_M, tol_pct: float = DEFAULT_TOL_PCT) -> list[list[Entry]]:
    """Groups of entries that look like the same run seen from different sources.

    Only cross-source pairs are considered: two Strava rows at the same time are a cache problem, not a
    duplicated import, and silently dropping one would hide it.
    """
    usable = [(k, a) for k, a in entries if _start(a) is not None and a.get("distance")]
    usable.sort(key=lambda e: (_start(e[1]), str(e[0])))
    window = dt.timedelta(minutes=minutes)

    groups: list[list[Entry]] = []
    taken: set[str] = set()
    for i, (key, act) in enumerate(usable):
        if key in taken:
            continue
        group = [(key, act)]
        for other_key, other in usable[i + 1:]:
            if other_key in taken or source_of(other_key) == source_of(key):
                continue
            if abs(_start(other) - _start(act)) > window:
                break
            if _distances_match(float(act["distance"]), float(other["distance"]), tol_m, tol_pct):
                group.append((other_key, other))
                taken.add(other_key)
        if len(group) > 1:
            taken.add(key)
            groups.append(group)
    return groups


def resolve(entries: Sequence[Entry], prefer: str = "strava", minutes: float = DEFAULT_MINUTES,
            tol_m: float = DEFAULT_TOL_M, tol_pct: float = DEFAULT_TOL_PCT
            ) -> tuple[list[Entry], list[Entry], list[list[Entry]]]:
    """Return (kept, dropped, groups). Entries that match nothing are always kept."""
    groups = find_duplicate_groups(entries, minutes, tol_m, tol_pct)
    dropped_keys = set()
    for group in groups:
        winner = next((e for e in group if source_of(e[0]) == prefer), group[0])
        dropped_keys.update(k for k, _ in group if k != winner[0])
    kept = [(k, a) for k, a in entries if k not in dropped_keys]
    dropped = [(k, a) for k, a in entries if k in dropped_keys]
    return kept, dropped, groups


def render_markdown(groups: list[list[Entry]], prefer: str = "strava") -> str:
    if not groups:
        return "No duplicates found: no run is cached from both Strava and a Garmin FIT import."
    lines = ["| Start | Source | Cache key | Distance | Kept |", "|---|---|---|---|---|"]
    for group in groups:
        winner = next((e for e in group if source_of(e[0]) == prefer), group[0])
        for key, act in group:
            lines.append(f"| {act.get('start_date_local')} | {source_of(key)} | {key} "
                         f"| {float(act['distance']) / 1000.0:.2f} km "
                         f"| {'yes' if key == winner[0] else 'no'} |")
    lines.append("")
    lines.append(f"{len(groups)} duplicated run(s). Nothing was deleted: `load` and `weekly` simply count "
                 f"the {prefer} copy once.")
    return "\n".join(lines)
