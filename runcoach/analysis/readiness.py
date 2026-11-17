"""Readiness recommendation from the latest wellness night plus the planned session.

The rules come from docs/COACHING_CONTEXT.md section 3, which records each one's status. That status is
carried through to the output verbatim, because a proposal must never be presented as an agreed rule:

  confirmed              agreed during the Oct 7 intervals session
  in_plan                written into the training plan
  suggested              suggested and not objected to (Oct 11 long run); not formally agreed
  proposed_not_confirmed proposed for the Oct 14 gate session and NOT confirmed

Nothing here guesses. If the sleep score or HRV status is missing, the decision is left undecided and says
which input it wanted, rather than assuming a value and producing a confident answer from nothing.
"""

from __future__ import annotations

from ..config import Profile
from ..fit.wellness import Night

SESSION_KINDS = ("intervals", "long", "strides", "gate")

SLEEP_FLOOR = 60            # "sleep score >= 60", COACHING_CONTEXT section 3
INTERVALS_HR_CAP = 172      # "stop at 2 reps if HR passes 172 before rep 3"

STATUS_LABELS = {
    "confirmed": "CONFIRMED",
    "in_plan": "IN THE PLAN",
    "suggested": "SUGGESTED (not objected to)",
    "proposed_not_confirmed": "PROPOSED, NOT CONFIRMED",
}


def _sleep_hrv_gate(night: Night) -> tuple[bool | None, str]:
    """Shared condition: sleep score >= 60 and HRV status not Unbalanced.

    Returns (ok, why). `ok` is None when an input is missing, and `why` always names what was used.
    """
    missing = []
    if night.score is None:
        missing.append("sleep score")
    if night.hrv_status is None:
        missing.append("HRV status")
    if missing:
        return None, f"missing {' and '.join(missing)}"

    unbalanced = night.hrv_status.strip().lower() == "unbalanced"
    slept = night.score >= SLEEP_FLOOR
    why = (f"sleep score {night.score} {'>=' if slept else '<'} {SLEEP_FLOOR}; "
           f"HRV status {night.hrv_status!r} {'is' if unbalanced else 'is not'} Unbalanced")
    return (slept and not unbalanced), why


def evaluate(night: Night, kind: str, legs_flat: bool = False, profile: Profile | None = None) -> dict:
    """Readiness for one planned session kind. Deterministic: same night and kind give the same result."""
    if kind not in SESSION_KINDS:
        raise ValueError(f"Unknown session kind: {kind!r} (expected one of {', '.join(SESSION_KINDS)})")
    profile = profile or Profile()
    ok, why = _sleep_hrv_gate(night)
    decisions: list[dict] = []
    watch: list[dict] = []

    if kind == "intervals":
        decisions.append({
            "rule": "intervals-reps", "status": "confirmed", "undecided": ok is None,
            "reps": None if ok is None else (3 if ok else 2), "why": why,
            "rule_text": f"run all 3 reps only if the sleep score is >= {SLEEP_FLOOR} and HRV status is not "
                         "Unbalanced, otherwise 2 reps",
            "recommendation": "cannot decide without the missing input" if ok is None
                              else ("run all 3 reps" if ok else "run 2 reps"),
        })
        watch.append({
            "rule": "intervals-hr-cap", "status": "confirmed",
            "note": f"stop at 2 reps if HR passes {INTERVALS_HR_CAP} before rep 3 (decide during the session, "
                    "not from last night's data)",
        })

    if kind == "long":
        decisions.append({
            "rule": "long-cut-60", "status": "suggested", "undecided": ok is None,
            "cut": None if ok is None else (not ok), "why": why,
            "rule_text": f"if the sleep score is < {SLEEP_FLOOR} or HRV reads Unbalanced, cut the long run to "
                         "60 minutes",
            "recommendation": "cannot decide without the missing input" if ok is None
                              else ("cut the long run to 60 minutes" if not ok else "run the long run as planned"),
        })
        watch.append({
            "rule": "long-hr-guide", "status": "suggested",
            "note": f"keep easy/long HR near or below about {profile.easy_hr_guide} bpm",
        })

    if kind == "strides":
        decisions.append({
            "rule": "strides-30", "status": "in_plan", "undecided": False,
            "shorten": bool(legs_flat), "why": f"legs reported {'flat' if legs_flat else 'not flat'}",
            "rule_text": "Friday strides can be shortened to Strides 30 if the legs feel flat",
            "recommendation": "shorten to Strides 30" if legs_flat else "strides as planned",
        })

    if kind == "gate":
        decisions.append({
            "rule": "gate-3-reps", "status": "proposed_not_confirmed", "undecided": ok is None,
            "reps": None if ok is None else (4 if ok else 3), "why": why,
            "rule_text": f"proposed only: 3 reps instead of 4 if the sleep score is < {SLEEP_FLOOR} or HRV reads "
                         "Unbalanced",
            "recommendation": "cannot decide without the missing input" if ok is None
                              else ("4 x 1 km as planned" if ok else "3 reps instead of 4"),
        })

    return {
        "kind": kind,
        "wake_date": night.wake_date.isoformat(),
        "sleep_score": night.score,
        "hrv_status": night.hrv_status,
        "legs_flat": bool(legs_flat),
        "decisions": decisions,
        "watch": watch,
    }


def render_markdown(result: dict) -> str:
    """Human-readable readiness note. Every line names the rule and its status."""
    score = "-" if result["sleep_score"] is None else result["sleep_score"]
    hrv = result["hrv_status"] or "-"
    lines = [
        f"## Readiness: {result['kind']} (night of {result['wake_date']})",
        "",
        f"Sleep score {score}, HRV status {hrv}",
        "",
    ]
    for d in result["decisions"]:
        label = STATUS_LABELS[d["status"]]
        head = "CANNOT DECIDE" if d["undecided"] else d["recommendation"].upper()
        lines.append(f"- {head}  [{label}, rule {d['rule']}]")
        lines.append(f"    rule: {d['rule_text']}")
        lines.append(f"    inputs: {d['why']}")
    for w in result["watch"]:
        lines.append(f"- WATCH  [{STATUS_LABELS[w['status']]}, rule {w['rule']}]")
        lines.append(f"    {w['note']}")
    return "\n".join(lines)
