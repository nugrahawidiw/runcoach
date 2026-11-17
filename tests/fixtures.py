"""Real laps from this coaching session, reshaped like Strava REST /activities/{id}/laps."""

# (moving_s, distance_m, grade_pct, avg_hr, cadence_rpm_one_foot)
OCT8_EASY = [
    (415, 1000, 0.139665, 128.681, 84.1598), (419, 1000, -0.040032, 140.010, 83.9356),
    (421, 1000, -0.0601263, 144.657, 84.1262), (421, 1000, 0.0200743, 147.505, 83.7850),
    (411, 1000, -0.0200702, 151.612, 83.6561), (312, 738.15, -0.163376, 150.498, 83.5402),
]
OCT11_LONG = [
    (454, 1000, -1.19713, 118.526, 83.2754), (463, 1000, -1.80198, 123.898, 83.1239),
    (392, 1000, -1.90228, 135.906, 85.8087), (404, 1000, -0.601323, 140.060, 85.6658),
    (418, 1000, -0.0802005, 143.990, 85.8585), (415, 1000, -0.0601383, 145.828, 85.1453),
    (411, 1000, 0.100361, 146.822, 86.6244), (421, 1000, 1.04156, 150.076, 85.4157),
    (411, 1000, 0.381335, 150.385, 85.2146), (397, 1000, 1.1022, 154.212, 85.3030),
]


def rest_laps(rows):
    """REST-shaped laps with start/end indices into 1 Hz streams."""
    laps, idx = [], 0
    for secs, dist, _grade, hr, cad in rows:
        laps.append({
            "distance": dist, "moving_time": secs, "elapsed_time": secs,
            "average_heartrate": hr, "average_cadence": cad,
            "start_index": idx, "end_index": idx + secs - 1,
        })
        idx += secs
    return laps


def streams_for(rows):
    """1 Hz grade and cadence streams that reproduce each lap's average."""
    grade, cadence, heartrate = [], [], []
    for secs, _dist, g, hr, cad in rows:
        grade += [g] * secs
        cadence += [cad] * secs
        heartrate += [hr] * secs
    return {"grade_smooth": {"data": grade}, "cadence": {"data": cadence},
            "heartrate": {"data": heartrate}}


def laps_for_decoupling(rows):
    return [{"moving_time": s, "distance": d, "avg_hr": hr, "grade_pct": g} for s, d, g, hr, _c in rows]


def activity_for(rows, day, name="Run", suffer=None):
    """A Strava-shaped activity whose totals are the sum of these laps (nothing hand-typed)."""
    act = {
        "name": name,
        "start_date_local": f"{day}T06:00:00Z",
        "distance": sum(r[1] for r in rows),
        "moving_time": sum(r[0] for r in rows),
    }
    if suffer is not None:
        act["suffer_score"] = suffer
    return act


# Real laps from Strava for the two structured sessions (roadmap P1.2), fetched 2026-11-17.
# Sanitized: laps only. No GPS, no segment or place names, no gear, no activity ids.
# Same column order as the fixtures above: (moving_s, distance_m, grade_pct, avg_hr, cadence_rpm_one_foot)
# Self-checking: tests/test_session.py reproduces the documented golden numbers from these rows, so a
# transcription slip would fail the suite rather than go unnoticed.
OCT7_INTERVALS = [
    (426, 1000.0, -0.0998602, 124.421, 83.7106),    # warm-up
    (174, 423.26, 0.0943174, 135.201, 84.454),      # warm-up
    (324, 1000.0, -0.160562, 153.613, 86.483),      # rep 1
    (36, 113.44, 0.365631, 158.029, 86.4),          # rep 1 (remainder of the 6:00 block)
    (120, 241.43, -0.0846382, 149.941, 81.161),     # recovery
    (327, 1000.0, -0.120361, 158.132, 85.4663),     # rep 2
    (33, 99.95, 0.40568, 161.697, 84.6667),         # rep 2
    (120, 252.83, 0.241449, 155.273, 80.8547),      # recovery
    (327, 1000.0, -0.120084, 161.165, 84.9388),     # rep 3
    (33, 101.27, 0.199203, 163.25, 85.4688),        # rep 3
    (414, 1000.0, 0.100705, 157.918, 83.1501),      # cool-down
    (306, 754.73, -0.584718, 158.296, 83.6809),     # cool-down
]

OCT9_STRIDES = [
    (417, 1000.0, 0.179748, 129.254, 84.6859),
    (407, 1000.0, 0.060048, 139.436, 85.6773),
    (181, 435.85, 0.0460405, 141.589, 85.9833),
    (20, 85.18, -0.495663, 146.611, 93.1111),       # stride 1
    (45, 107.72, -0.385356, 154.545, 85.25),
    (20, 97.51, -0.42735, 154.684, 96.8421),        # stride 2
    (45, 114.36, -0.182149, 158.977, 83.3182),
    (20, 86.86, 2.82686, 159.263, 94.7368),         # stride 3
    (45, 105.7, 0.604839, 160.636, 82.3409),
    (20, 86.96, 0.962696, 159.053, 92.6842),        # stride 4
    (45, 93.04, 0.669643, 161.409, 81.4545),
    (20, 89.59, 1.39211, 156.789, 91.7895),         # stride 5
    (45, 95.71, 0.870511, 157.698, 81.186),
    (20, 90.66, -0.685714, 161.368, 91.8947),       # stride 6
    (424, 1000.0, -0.442478, 150.668, 82.3007),
    (410, 1000.0, 0.30027, 151.839, 83.3985),
    (216, 516.0, -0.389105, 151.606, 83.3005),
]
