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
    grade, cadence = [], []
    for secs, _dist, g, _hr, cad in rows:
        grade += [g] * secs
        cadence += [cad] * secs
    return {"grade_smooth": {"data": grade}, "cadence": {"data": cadence}}


def laps_for_decoupling(rows):
    return [{"moving_time": s, "distance": d, "avg_hr": hr, "grade_pct": g} for s, d, g, hr, _c in rows]
