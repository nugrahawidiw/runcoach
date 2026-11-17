"""Readiness rules (roadmap P1.1).

Every rule in COACHING_CONTEXT.md section 3 has a test here, including its status tier.
A proposal must never be reported as a confirmed rule.
"""

import datetime as dt

from runcoach.analysis.readiness import SESSION_KINDS, evaluate, render_markdown
from runcoach.fit.wellness import Night

UTC = dt.UTC


def night(score=75, hrv_status="balanced"):
    start = dt.datetime(2026, 10, 11, 22, 22)
    return Night(wake_date=dt.date(2026, 10, 12), sleep_start=start,
                 sleep_end=start + dt.timedelta(minutes=377), duration_min=377.0,
                 score=score, hrv_status=hrv_status)


def fired(result, rule_id):
    return next(d for d in result["decisions"] if d["rule"] == rule_id)


# ---- confirmed: Oct 7 intervals -------------------------------------------------------------
def test_intervals_all_three_reps_when_sleep_and_hrv_are_good():
    d = fired(evaluate(night(score=75, hrv_status="balanced"), "intervals"), "intervals-reps")
    assert d["status"] == "confirmed" and d["reps"] == 3
    assert "3 reps" in d["recommendation"]


def test_intervals_two_reps_when_sleep_score_is_below_60():
    d = fired(evaluate(night(score=59), "intervals"), "intervals-reps")
    assert d["reps"] == 2 and "sleep score 59" in d["why"]


def test_intervals_sleep_score_of_exactly_60_still_allows_three_reps():
    assert fired(evaluate(night(score=60), "intervals"), "intervals-reps")["reps"] == 3


def test_intervals_two_reps_when_hrv_is_unbalanced_whatever_the_sleep_score():
    d = fired(evaluate(night(score=90, hrv_status="Unbalanced"), "intervals"), "intervals-reps")
    assert d["reps"] == 2 and "unbalanced" in d["why"].lower()


def test_intervals_hr_cap_is_a_watch_item_not_a_decision():
    result = evaluate(night(), "intervals")
    assert not any(d["rule"] == "intervals-hr-cap" for d in result["decisions"])
    watch = next(w for w in result["watch"] if w["rule"] == "intervals-hr-cap")
    assert watch["status"] == "confirmed" and "172" in watch["note"]


# ---- suggested, not objected to: Oct 11 long run --------------------------------------------
def test_long_run_is_cut_to_60_minutes_on_poor_sleep_and_is_only_a_suggestion():
    d = fired(evaluate(night(score=55), "long"), "long-cut-60")
    assert d["status"] == "suggested" and "60 minutes" in d["recommendation"]


def test_long_run_is_not_cut_when_sleep_and_hrv_are_good():
    assert fired(evaluate(night(), "long"), "long-cut-60")["cut"] is False


def test_long_run_always_carries_the_hr_guide_advisory():
    w = next(w for w in evaluate(night(), "long")["watch"] if w["rule"] == "long-hr-guide")
    assert "145" in w["note"] and w["status"] == "suggested"


# ---- in the plan: Friday strides ------------------------------------------------------------
def test_strides_shortened_only_when_the_legs_are_reported_flat():
    assert fired(evaluate(night(), "strides", legs_flat=True), "strides-30")["shorten"] is True
    assert fired(evaluate(night(), "strides"), "strides-30")["shorten"] is False
    assert fired(evaluate(night(), "strides", legs_flat=True), "strides-30")["status"] == "in_plan"


# ---- proposed, NOT confirmed: Oct 14 gate session -------------------------------------------
def test_gate_session_three_reps_is_labelled_as_an_unconfirmed_proposal():
    d = fired(evaluate(night(score=50), "gate"), "gate-3-reps")
    assert d["status"] == "proposed_not_confirmed"
    assert d["reps"] == 3
    md = render_markdown(evaluate(night(score=50), "gate"))
    assert "PROPOSED, NOT CONFIRMED" in md


def test_gate_session_four_reps_when_sleep_and_hrv_are_good():
    assert fired(evaluate(night(), "gate"), "gate-3-reps")["reps"] == 4


# ---- missing data must not be guessed -------------------------------------------------------
def test_missing_sleep_score_blocks_the_decision_rather_than_assuming_one():
    d = fired(evaluate(night(score=None), "intervals"), "intervals-reps")
    assert d["reps"] is None and d["undecided"] is True
    assert "sleep score" in d["why"]
    assert "CANNOT DECIDE" in render_markdown(evaluate(night(score=None), "intervals"))


def test_missing_hrv_status_blocks_the_decision():
    d = fired(evaluate(night(hrv_status=None), "intervals"), "intervals-reps")
    assert d["undecided"] is True and "HRV status" in d["why"]


# ---- shape ----------------------------------------------------------------------------------
def test_only_rules_for_the_requested_kind_are_reported():
    ids = {d["rule"] for d in evaluate(night(), "intervals")["decisions"]}
    assert ids == {"intervals-reps"}
    assert "strides-30" not in ids


def test_every_session_kind_is_evaluable_and_names_the_night():
    for kind in SESSION_KINDS:
        result = evaluate(night(), kind)
        assert result["kind"] == kind and result["wake_date"] == "2026-10-12"
        assert render_markdown(result).startswith(f"## Readiness: {kind}")


def test_readiness_command_uses_the_latest_night_in_the_path(monkeypatch, capsys):
    """End to end through the CLI: the newest night wins, and the output names the rule."""
    from runcoach import cli
    from tests.test_fit_wellness import night_messages

    monkeypatch.setattr(cli, "iter_groups", lambda path: [("SLEEP.fit", night_messages())])
    assert cli.main(["readiness", "unused-path", "--kind", "intervals"]) == 0
    out = capsys.readouterr().out
    assert "## Readiness: intervals (night of 2026-10-12)" in out
    assert "RUN ALL 3 REPS  [CONFIRMED, rule intervals-reps]" in out


def test_readiness_command_rejects_an_unknown_session_kind(capsys):
    from runcoach import cli

    try:
        cli.main(["readiness", "unused-path", "--kind", "marathon"])
    except SystemExit as exc:
        assert exc.code == 2                      # argparse rejects it before any file is read
    assert "invalid choice" in capsys.readouterr().err
