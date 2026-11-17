import datetime as dt

import pytest

from runcoach.fit.reader import FIT_EPOCH, Message, fit_seconds
from runcoach.fit.wellness import monitoring_samples, stage_minutes, summarize_messages

UTC = dt.UTC
START = dt.datetime(2026, 10, 11, 15, 22, 6, tzinfo=UTC)      # 22:22 local (+7)
END = dt.datetime(2026, 10, 11, 21, 39, 6, tzinfo=UTC)         # 04:39 local


def night_messages(file="SLEEP.fit"):
    t0 = dt.datetime(2026, 10, 11, 17, 0, tzinfo=UTC)
    msgs = [
        Message("monitoring_info", {"timestamp": t0, "local_timestamp": t0 + dt.timedelta(hours=7)}, "W.fit"),
        Message("unknown_521", {"unknown_3": fit_seconds(START), "unknown_5": fit_seconds(END),
                                "unknown_9": 1767, "unknown_1": 75}, file),
        Message("sleep_assessment", {"overall_sleep_score": 75, "deep_sleep_score": 100,
                                     "average_stress_during_sleep": 17.57}, file),
        Message("hrv_status_summary", {"timestamp": END + dt.timedelta(minutes=1), "weekly_average": 27.0,
                                       "last_night_average": 30.0, "status": "balanced",
                                       "baseline_low_upper": 25.0, "baseline_balanced_lower": 27.0,
                                       "baseline_balanced_upper": 34.0, "last_night_5_min_high": 53.0}, "H.fit"),
        Message("monitoring_hr_data", {"timestamp": t0, "resting_heart_rate": 60,
                                       "current_day_resting_heart_rate": 58}, "W.fit"),
        Message("unknown_407", {"unknown_253": fit_seconds(START), "unknown_1": 377, "unknown_2": 51}, file),
        Message("stress_level", {"stress_level_time": t0, "stress_level_value": 20}, "W.fit"),
        Message("stress_level", {"stress_level_time": t0, "stress_level_value": -1}, "W.fit"),   # unmeasurable
        Message("respiration_rate", {"timestamp": t0, "respiration_rate": 17.0}, "W.fit"),
    ]
    # sleep stages: timestamp = end of stage (see stage_minutes)
    for minutes, level in ((8, "light"), (35, "deep"), (28, "light"), (7, "awake")):
        pass
    t = START
    for minutes, level in ((8, "light"), (35, "deep"), (28, "light"), (7, "awake"), (299, "light")):
        t += dt.timedelta(minutes=minutes)
        msgs.append(Message("sleep_level", {"timestamp": t, "sleep_level": level}, file))
    # heart rate: first sample carries a full timestamp, the rest only timestamp_16
    base = START + dt.timedelta(minutes=30)
    msgs.append(Message("monitoring", {"timestamp": base, "heart_rate": 59}, "W.fit"))
    base_secs = fit_seconds(base)
    for i, hr in enumerate((57, 56, 58, 56, 56, 56, 61, 70), start=1):
        msgs.append(Message("monitoring", {"timestamp_16": (base_secs + 60 * i) & 0xFFFF, "heart_rate": hr}, "W.fit"))
    return msgs


def test_full_night_summary():
    (night,) = summarize_messages(night_messages())
    assert night.wake_date == dt.date(2026, 10, 12)               # local wake date, device offset +7 h
    assert night.sleep_start == dt.datetime(2026, 10, 11, 22, 22, 6)
    assert night.duration_min == 377.0 and night.score == 75
    assert night.awake_min_summary == pytest.approx(29.45, abs=0.06)
    assert night.hrv_last_night == 30.0 and night.hrv_weekly == 27.0 and night.hrv_status == "balanced"
    assert night.hrv_baseline == (25.0, 27.0, 34.0)
    assert night.sleep_low_hr == 56                                # median of the 5 lowest samples
    assert (night.garmin_rhr, night.garmin_rhr_today) == (60, 58)
    assert night.stress_sleep_avg == 17.57 and night.stress_export_avg == 20.0   # -1 ignored
    assert night.body_battery_delta == 51 and night.resp_avg == 17.0
    assert night.stage_min["deep"] == 35 and night.stage_min["awake"] == 7


def test_naps_are_excluded():
    msgs = [Message("unknown_521", {"unknown_3": fit_seconds(START),
                                    "unknown_5": fit_seconds(START + dt.timedelta(minutes=45))}, "NAP.fit")]
    assert summarize_messages(msgs) == []


def test_timestamp_16_expansion_across_rollover():
    base = FIT_EPOCH + dt.timedelta(seconds=(5 << 16) + 65530)
    msgs = [Message("monitoring", {"timestamp": base, "heart_rate": 60}, "f"),
            Message("monitoring", {"timestamp_16": 65534, "heart_rate": 61}, "f"),
            Message("monitoring", {"timestamp_16": 4, "heart_rate": 62}, "f")]      # 16-bit counter wrapped
    times = [t for t, _ in monitoring_samples(msgs)]
    assert [(t - base).total_seconds() for t in times] == [0, 4, 10]


def test_stage_minutes_assumption_documented_in_behaviour():
    lv = [(START + dt.timedelta(minutes=10), "light"), (START + dt.timedelta(minutes=40), "deep")]
    out = stage_minutes(lv, START, START + dt.timedelta(minutes=50))
    assert out == {"light": 10.0, "deep": 30.0, "unassigned": 10.0}


def test_wellness_table_shows_the_hrv_low_baseline(monkeypatch, capsys):
    """The markdown table reports baseline_low_upper, not only the balanced range."""
    from runcoach import cli

    monkeypatch.setattr(cli, "iter_groups", lambda path: [("SLEEP.fit", night_messages())])
    assert cli.main(["wellness", "unused-path"]) == 0
    out = capsys.readouterr().out
    assert "HRV baseline low / balanced" in out
    assert "25 / 27-34" in out
