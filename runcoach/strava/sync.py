"""Pull recent runs into the local cache (3 API calls per new run)."""
from __future__ import annotations

import time
from dataclasses import dataclass

from .cache import Cache
from .client import StravaClient
from .errors import RateLimitError

RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}


@dataclass
class SyncResult:
    fetched: int = 0
    skipped: int = 0
    stopped_by_rate_limit: bool = False


def sync_recent(client: StravaClient, cache: Cache, days: int = 14, force: bool = False,
                now: float | None = None) -> SyncResult:
    after = (now if now is not None else time.time()) - days * 86400
    result = SyncResult()
    listing = client.list_activities(after=after)
    runs = [a for a in listing if (a.get("sport_type") or a.get("type")) in RUN_TYPES]
    for summary in sorted(runs, key=lambda a: a["start_date_local"]):
        aid = summary["id"]
        done = all(cache.has(k, aid) for k in ("activity", "laps", "streams"))
        if done and not force:
            result.skipped += 1
            continue
        try:
            detail = client.get_activity(aid) or summary
            cache.put("activity", aid, detail)
            cache.put("laps", aid, client.get_laps(aid))
            cache.put("streams", aid, client.get_streams(aid))
            result.fetched += 1
        except RateLimitError:
            result.stopped_by_rate_limit = True
            break
    return result
