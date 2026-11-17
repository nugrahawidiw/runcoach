"""Command line: auth | sync | analyze | load | vdot | fit-analyze | fit-import | wellness"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import date, timedelta

from .analysis import charts as chart_svg
from .analysis import dashboard as dashboard_html
from .analysis import dedupe as dedupe_runs
from .analysis import plan as plan_data
from .analysis import readiness as readiness_rules
from .analysis import weekly as weekly_summary
from .analysis import wellness_trends
from .analysis.run_report import build_report, render_markdown
from .config import data_dir, load_env, load_profile
from .fit.activity import activity_from_messages, cache_id
from .fit.reader import iter_groups, iter_path
from .fit.wellness import summarize_messages
from .metrics.load import banister_trimp, load_series
from .metrics.pace import fmt_time, parse_time
from .metrics.vdot import riegel, time_for_vdot, vdot
from .strava.auth import TokenStore, run_local_flow
from .strava.cache import Cache
from .strava.client import StravaClient
from .strava.errors import StravaError
from .strava.sync import sync_recent


def _creds():
    cid, secret = os.environ.get("STRAVA_CLIENT_ID"), os.environ.get("STRAVA_CLIENT_SECRET")
    if not cid or not secret:
        sys.exit("Set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET in .env (see .env.example).")
    return cid, secret


def _store() -> TokenStore:
    return TokenStore(data_dir() / "tokens.json")


def _cache() -> Cache:
    return Cache(data_dir() / "cache")


def cmd_auth(args):
    cid, secret = _creds()
    redirect = os.environ.get("STRAVA_REDIRECT_URI", "http://localhost:8765/callback")
    run_local_flow(cid, secret, redirect, _store())
    print("Authorized. Tokens saved.")


def cmd_sync(args):
    cid, secret = _creds()
    client = StravaClient(cid, secret, _store())
    result = sync_recent(client, _cache(), days=args.days, force=args.force)
    print(f"fetched {result.fetched}, already cached {result.skipped}")
    if result.stopped_by_rate_limit:
        print("Stopped by the Strava rate limit. Wait ~15 minutes and run sync again; it resumes.")
    if client.usage and client.limit:
        print(f"API usage (overall): {client.usage} of {client.limit} (15 min, day)")
    if client.read_usage and client.read_limit:
        print(f"API usage (read):    {client.read_usage} of {client.read_limit} (15 min, day)")


def _latest_id(cache: Cache) -> str:
    best = None
    for aid in cache.ids("activity"):
        act = cache.get("activity", aid)
        key = act.get("start_date_local", "")
        if best is None or key > best[0]:
            best = (key, aid)
    if not best:
        sys.exit("Cache is empty. Run `runcoach sync` first.")
    return best[1]


def _write_chart(report, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(chart_svg.pace_cadence_svg(report, load_profile()))
    print(f"wrote {path}")


def cmd_analyze(args):
    cache = _cache()
    aid = _latest_id(cache) if args.activity == "latest" else args.activity
    activity = cache.get("activity", aid)
    if activity is None:
        sys.exit(f"Activity {aid} not cached. Run `runcoach sync --days N` first.")
    report = build_report(activity, cache.get("laps", aid) or [], cache.get("streams", aid) or {},
                          load_profile(), kind=args.kind)
    print(json.dumps(report, indent=2) if args.json else render_markdown(report))
    if args.chart:
        _write_chart(report, args.chart)


def _cached_activities(cache):
    """(kept, dropped) cached activities, with Strava/Garmin duplicates resolved (roadmap P1.5).

    Deduping here means `load`, `weekly` and `plan` cannot count one run twice just because it was imported
    from a FIT file as well as synced. Nothing is removed from the cache itself.
    """
    entries = [(aid, cache.get("activity", aid)) for aid in cache.ids("activity")]
    kept, dropped, _ = dedupe_runs.resolve([(k, a) for k, a in entries if a])
    return kept, dropped


def _duplicate_note(dropped) -> str:
    keys = ", ".join(k for k, _ in dropped)
    return (f"NOTE: {len(dropped)} duplicate run(s) ignored so they are not counted twice: {keys}. "
            "Run `runcoach dedupe` for detail.\n")


def _daily_loads(cache, profile, source: str) -> dict[date, float]:
    """Daily training load from the kept activities. Shared by `load` and `weekly` so the two always agree."""
    daily: dict[date, float] = defaultdict(float)
    kept, _ = _cached_activities(cache)
    for aid, act in kept:
        day = date.fromisoformat(act["start_date_local"][:10])
        if source == "suffer" and act.get("suffer_score") is not None:
            daily[day] += float(act["suffer_score"])
        else:
            st = cache.get("streams", aid) or {}
            hr = (st.get("heartrate") or {}).get("data")
            tm = (st.get("time") or {}).get("data")
            if hr and tm:
                daily[day] += banister_trimp(hr, tm, profile.hr_rest, profile.hr_max, profile.sex)
    return daily


def cmd_plan(args):
    plan = plan_data.load_plan(args.path)
    if args.ics:
        with open(args.ics, "wb") as fh:
            fh.write(plan_data.to_ics(plan))
        print(f"wrote {args.ics} ({len(plan)} sessions)")
        return
    cache = _cache()
    kept, _ = _cached_activities(cache)
    comparison = plan_data.compare(plan, [a for _, a in kept])
    if args.json:
        print(json.dumps(comparison.rows, indent=2))
    else:
        print(plan_data.render_markdown(comparison))


def cmd_weekly(args):
    cache, profile = _cache(), load_profile()
    kept, dropped = _cached_activities(cache)
    if dropped:
        print(_duplicate_note(dropped))
    activities = [a for _, a in kept]
    plan = plan_data.load_plan(args.plan) if args.plan else None
    summaries = weekly_summary.summarize_weeks(activities, _daily_loads(cache, profile, args.source),
                                               weeks=args.weeks, ctl0=args.ctl0, atl0=args.atl0, plan=plan)
    if not summaries:
        sys.exit("No cached runs. Run `runcoach sync` first.")
    if args.json:
        print(json.dumps(summaries, indent=2))
    else:
        print(weekly_summary.render_markdown(summaries))


def cmd_load(args):
    cache, profile = _cache(), load_profile()
    daily = _daily_loads(cache, profile, args.source)
    _, dropped = _cached_activities(cache)
    if dropped:
        print(_duplicate_note(dropped))
    if not daily:
        sys.exit("No cached runs with load data. Run `runcoach sync` first.")
    end = max(daily)
    start = end - timedelta(days=args.days)
    history_days = (end - min(daily)).days
    if args.ctl0 == 0 and args.atl0 == 0 and history_days < 42:
        print(f"NOTE: only {history_days} days of history are cached and the series starts from zero, so CTL/ATL are "
              "understated. Sync more history (e.g. --days 120, in chunks) or seed with --ctl0 and --atl0.\n")
    print("date        load   CTL   ATL   TSB")
    for p in load_series(daily, start, end, args.ctl0, args.atl0):
        print(f"{p.day}  {p.load:5.1f} {p.ctl:5.1f} {p.atl:5.1f} {p.tsb:+5.1f}")


def cmd_vdot(args):
    secs = parse_time(args.time)
    v = vdot(secs, args.distance_m)
    print(f"VDOT {v:.1f}")
    for name, dist in (("5K", 5000), ("10K", 10000), ("Half", 21097.5)):
        print(f"  {name:5} equivalent {fmt_time(time_for_vdot(v, dist))}   (Riegel {fmt_time(riegel(secs, args.distance_m, dist))})")


def _load_fit_run(path):
    return activity_from_messages(list(iter_path(path)))


def cmd_fit_analyze(args):
    run = _load_fit_run(args.path)
    report = build_report(run.activity, run.laps, run.streams, load_profile(), kind=args.kind)
    print(json.dumps(report, indent=2) if args.json else render_markdown(report))
    if args.chart:
        _write_chart(report, args.chart)


def cmd_fit_import(args):
    cache = _cache()
    for path in args.paths:
        run = _load_fit_run(path)
        key = cache_id(run)
        cache.put("activity", key, run.activity)
        cache.put("laps", key, run.laps)
        cache.put("streams", key, run.streams)
        print(f"imported {path} as {key} ({run.activity['distance'] / 1000:.2f} km)")


def _fmt(value, spec="", dash="-"):
    return dash if value is None else format(value, spec)


def cmd_dashboard(args):
    cache, profile = _cache(), load_profile()
    kept, dropped = _cached_activities(cache)
    if dropped:
        print(_duplicate_note(dropped))
    if not kept:
        sys.exit("No cached runs. Run `runcoach sync` first.")
    daily = _daily_loads(cache, profile, args.source)
    weeks = weekly_summary.summarize_weeks([a for _, a in kept], daily, weeks=args.weeks,
                                           ctl0=args.ctl0, atl0=args.atl0)
    points = list(load_series(daily, min(daily), max(daily), args.ctl0, args.atl0)) if daily else []

    latest = None
    aid = _latest_id(cache)
    activity = cache.get("activity", aid)
    if activity:
        latest = build_report(activity, cache.get("laps", aid) or [], cache.get("streams", aid) or {},
                              profile, kind=args.kind)
    page = dashboard_html.render_html(weeks, points, latest, profile, generated=date.today())
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"wrote {args.out} ({len(page) // 1024} KB, {len(weeks)} weeks)")


def cmd_dedupe(args):
    cache = _cache()
    entries = [(aid, cache.get("activity", aid)) for aid in cache.ids("activity")]
    groups = dedupe_runs.find_duplicate_groups([(k, a) for k, a in entries if a],
                                               minutes=args.minutes, tol_m=args.tolerance_m)
    if args.json:
        print(json.dumps([[{"key": k, "activity": a} for k, a in g] for g in groups], indent=2))
    else:
        print(dedupe_runs.render_markdown(groups, prefer=args.prefer))


def cmd_trends(args):
    nights = []
    for _label, msgs in iter_groups(args.path):
        nights.extend(summarize_messages(msgs))
    if not nights:
        sys.exit("No full night of sleep data found in that path.")
    result = wellness_trends.summarize(nights, window=args.window, weak_nights=args.weak_nights)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(wellness_trends.render_markdown(result))


def cmd_readiness(args):
    nights = []
    for _label, msgs in iter_groups(args.path):
        nights.extend(summarize_messages(msgs))
    if not nights:
        sys.exit("No full night of sleep data found in that path.")
    night = max(nights, key=lambda n: n.wake_date)
    result = readiness_rules.evaluate(night, args.kind, legs_flat=args.legs_flat, profile=load_profile())
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(readiness_rules.render_markdown(result))


def cmd_wellness(args):
    nights = []
    for _label, msgs in iter_groups(args.path):
        nights.extend(summarize_messages(msgs))
    if not nights:
        sys.exit("No full night of sleep data found in that path.")
    nights.sort(key=lambda n: n.wake_date)
    if args.json:
        print(json.dumps([n.to_dict() for n in nights], indent=2))
    else:
        print("| Wake date | Sleep | Dur | HRV last / 7d | HRV baseline low / balanced "
              "| Status | Low HR | Garmin RHR | Stress (sleep) | Battery |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for n in nights:
            h, m = divmod(int(round(n.duration_min)), 60)
            low, bal_lo, bal_hi = n.hrv_baseline[0], n.hrv_baseline[1], n.hrv_baseline[2]
            print(f"| {n.wake_date} | {_fmt(n.score)} | {h}h{m:02d} "
                  f"| {_fmt(n.hrv_last_night, '.0f')} / {_fmt(n.hrv_weekly, '.0f')} "
                  f"| {_fmt(low, '.0f')} / {_fmt(bal_lo, '.0f')}-{_fmt(bal_hi, '.0f')} "
                  f"| {_fmt(n.hrv_status)} | {_fmt(n.sleep_low_hr)} "
                  f"| {_fmt(n.garmin_rhr)} | {_fmt(n.stress_sleep_avg, '.0f')} "
                  f"| {_fmt(n.body_battery_delta, '+d')} |")
    if args.csv:
        import csv
        rows = [n.to_dict() for n in nights]
        for r in rows:
            for key in ("score_parts", "stage_min"):
                r[key] = json.dumps(r[key])
            r["hrv_baseline"] = "|".join("" if x is None else str(x) for x in r["hrv_baseline"])
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nwrote {args.csv}")


def main(argv=None) -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="runcoach")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("auth", help="authorize with Strava (one time)").set_defaults(fn=cmd_auth)

    s = sub.add_parser("sync", help="download recent runs into the local cache")
    s.add_argument("--days", type=int, default=14)
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_sync)

    a = sub.add_parser("analyze", help="deep dive on one run")
    a.add_argument("activity", nargs="?", default="latest")
    a.add_argument("--kind", choices=["easy", "long", "strides", "intervals"], default="easy")
    a.add_argument("--chart", metavar="OUT.svg", help="also write a pace/cadence chart")
    a.add_argument("--json", action="store_true")
    a.set_defaults(fn=cmd_analyze)

    l = sub.add_parser("load", help="CTL / ATL / TSB from cached runs")
    l.add_argument("--days", type=int, default=42)
    l.add_argument("--source", choices=["suffer", "trimp"], default="suffer")
    l.add_argument("--ctl0", type=float, default=0.0)
    l.add_argument("--atl0", type=float, default=0.0)
    l.set_defaults(fn=cmd_load)

    fa = sub.add_parser("fit-analyze", help="deep dive on a Garmin activity .fit file")
    fa.add_argument("path")
    fa.add_argument("--kind", choices=["easy", "long", "strides", "intervals"], default="easy")
    fa.add_argument("--chart", metavar="OUT.svg", help="also write a pace/cadence chart")
    fa.add_argument("--json", action="store_true")
    fa.set_defaults(fn=cmd_fit_analyze)

    fi = sub.add_parser("fit-import", help="add Garmin activity .fit files to the local cache")
    fi.add_argument("paths", nargs="+")
    fi.set_defaults(fn=cmd_fit_import)

    w = sub.add_parser("wellness", help="sleep, HRV, resting HR, stress from Garmin wellness FIT (file, zip or folder)")
    w.add_argument("path")
    w.add_argument("--json", action="store_true")
    w.add_argument("--csv", help="also write all nights to this CSV file")
    w.set_defaults(fn=cmd_wellness)

    r = sub.add_parser("readiness", help="recommendation for a planned session from the latest wellness night")
    r.add_argument("path", help="Garmin wellness FIT file, zip or folder (the latest night in it is used)")
    r.add_argument("--kind", required=True, choices=list(readiness_rules.SESSION_KINDS),
                   help="the planned session")
    r.add_argument("--legs-flat", action="store_true",
                   help="report the legs as flat (the strides rule has no data source for this)")
    r.add_argument("--json", action="store_true")
    r.set_defaults(fn=cmd_readiness)

    wk = sub.add_parser("weekly", help="per-week distance, time, runs and the CTL/ATL/TSB line")
    wk.add_argument("--weeks", type=int, default=4)
    wk.add_argument("--source", choices=["suffer", "trimp"], default="suffer")
    wk.add_argument("--ctl0", type=float, default=0.0)
    wk.add_argument("--atl0", type=float, default=0.0)
    wk.add_argument("--plan", help="plan.toml; adds planned runs and km per week")
    wk.add_argument("--json", action="store_true")
    wk.set_defaults(fn=cmd_weekly)

    pl = sub.add_parser("plan", help="plan vs actual from plan.toml, or export the plan as .ics")
    pl.add_argument("path", help="plan.toml (see plan.example.toml)")
    pl.add_argument("--ics", metavar="OUT.ics", help="write the plan as a calendar file instead of comparing")
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(fn=cmd_plan)

    tr = sub.add_parser("trends", help="rolling HRV, resting-HR trend and weak-night streak")
    tr.add_argument("path", help="Garmin wellness FIT file, zip or folder (all nights in it are used)")
    tr.add_argument("--window", type=int, default=wellness_trends.DEFAULT_WINDOW,
                    help="nights in the rolling HRV mean")
    tr.add_argument("--weak-nights", type=int, default=wellness_trends.DEFAULT_WEAK_NIGHTS,
                    help="consecutive weak nights that raise the alert")
    tr.add_argument("--json", action="store_true")
    tr.set_defaults(fn=cmd_trends)

    dd = sub.add_parser("dedupe", help="find runs cached from both Strava and a Garmin FIT import")
    dd.add_argument("--minutes", type=float, default=dedupe_runs.DEFAULT_MINUTES,
                    help="how far apart two start times may be")
    dd.add_argument("--tolerance-m", type=float, default=dedupe_runs.DEFAULT_TOL_M,
                    help="absolute distance tolerance; 1%% of the longer run is used when that is larger")
    dd.add_argument("--prefer", choices=["strava", "garmin"], default="strava")
    dd.add_argument("--json", action="store_true")
    dd.set_defaults(fn=cmd_dedupe)

    db = sub.add_parser("dashboard", help="write a self-contained HTML dashboard from the cache")
    db.add_argument("--out", default="dashboard.html")
    db.add_argument("--weeks", type=int, default=8)
    db.add_argument("--source", choices=["suffer", "trimp"], default="suffer")
    db.add_argument("--kind", choices=["easy", "long", "strides", "intervals"], default="easy",
                    help="kind of the latest run, for its chart")
    db.add_argument("--ctl0", type=float, default=0.0)
    db.add_argument("--atl0", type=float, default=0.0)
    db.set_defaults(fn=cmd_dashboard)

    v = sub.add_parser("vdot", help="VDOT and equivalent times")
    v.add_argument("time", help="e.g. 26:17 or 2:08:21")
    v.add_argument("distance_m", type=float, help="e.g. 5000 or 21097.5")
    v.set_defaults(fn=cmd_vdot)

    args = p.parse_args(argv)
    try:
        args.fn(args)
    except StravaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
