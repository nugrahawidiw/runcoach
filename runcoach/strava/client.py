"""Thin Strava API v3 client: automatic token refresh, 429 handling, rate-limit logging."""
from __future__ import annotations

import logging
import time

import requests

from .auth import Tokens, TokenStore, refresh_tokens
from .errors import AuthError, RateLimitError, StravaError
from .types import Activity, Lap, Streams

log = logging.getLogger("runcoach.strava")
API = "https://www.strava.com/api/v3"
STREAM_KEYS = ("time", "distance", "velocity_smooth", "heartrate", "cadence", "altitude", "grade_smooth")


class StravaClient:
    def __init__(self, client_id: str, client_secret: str, store: TokenStore,
                 session=None, clock=time.time):
        self.client_id = client_id
        self.client_secret = client_secret
        self.store = store
        self.session = session or requests.Session()
        self.clock = clock
        self.usage: tuple[int, int] | None = None     # overall (15-minute, daily) requests used
        self.limit: tuple[int, int] | None = None
        self.read_usage: tuple[int, int] | None = None  # read-only requests (usually the tighter limit)
        self.read_limit: tuple[int, int] | None = None

    # ---- auth -----------------------------------------------------------------
    def _tokens(self, force_refresh: bool = False) -> Tokens:
        tokens = self.store.load()
        if tokens is None:
            raise AuthError("No tokens found. Run `runcoach auth` first.")
        if force_refresh or tokens.expired(self.clock()):
            tokens = refresh_tokens(self.client_id, self.client_secret, tokens.refresh_token, self.session)
            self.store.save(tokens)
        return tokens

    # ---- low level ------------------------------------------------------------
    def _note_limits(self, resp) -> None:
        def pair(name):
            raw = resp.headers.get(name)
            if not raw:
                return None
            try:
                a, b = raw.split(",")
                return int(a), int(b)
            except ValueError:
                return None
        self.limit = pair("X-RateLimit-Limit") or self.limit
        self.usage = pair("X-RateLimit-Usage") or self.usage
        self.read_limit = pair("X-ReadRateLimit-Limit") or self.read_limit
        self.read_usage = pair("X-ReadRateLimit-Usage") or self.read_usage
        for label, limit, usage in (("overall", self.limit, self.usage), ("read", self.read_limit, self.read_usage)):
            if limit and usage and (usage[0] >= 0.8 * limit[0] or usage[1] >= 0.8 * limit[1]):
                log.warning("Strava %s rate limit nearly used: %s of %s", label, usage, limit)

    def _get(self, path: str, params: dict | None = None):
        token = self._tokens()
        for attempt in (0, 1):
            resp = self.session.request(
                "GET", f"{API}{path}", params=params, timeout=30,
                headers={"Authorization": f"Bearer {token.access_token}"},
            )
            self._note_limits(resp)
            if resp.status_code == 401 and attempt == 0:
                token = self._tokens(force_refresh=True)
                continue
            if resp.status_code == 401:
                raise AuthError("Strava rejected the token. Run `runcoach auth` again.")
            if resp.status_code == 429:
                raise RateLimitError(f"Rate limit hit (usage {self.usage} of {self.limit}). Wait and re-run sync.")
            if resp.status_code == 404:
                return None
            if resp.status_code >= 400:
                raise StravaError(f"GET {path} failed ({resp.status_code}): {resp.text[:200]}")
            return resp.json()
        return None

    # ---- endpoints --------------------------------------------------------------
    def list_activities(self, after: int | None = None, before: int | None = None,
                        per_page: int = 100, max_pages: int = 10) -> list[dict]:
        out: list[dict] = []
        for page in range(1, max_pages + 1):
            params = {"per_page": per_page, "page": page}
            if after is not None:
                params["after"] = int(after)
            if before is not None:
                params["before"] = int(before)
            batch = self._get("/athlete/activities", params) or []
            out.extend(batch)
            if len(batch) < per_page:
                break
        return out

    def get_activity(self, activity_id: int | str) -> Activity | None:
        return self._get(f"/activities/{activity_id}", {"include_all_efforts": "false"})

    def get_laps(self, activity_id: int | str) -> list[Lap]:
        return self._get(f"/activities/{activity_id}/laps") or []

    def get_streams(self, activity_id: int | str, keys=STREAM_KEYS) -> Streams:
        """Full-resolution streams keyed by type: {'time': {'data': [...]}, ...}."""
        data = self._get(f"/activities/{activity_id}/streams",
                         {"keys": ",".join(keys), "key_by_type": "true"})
        return data or {}

    def get_gear(self, gear_id: str) -> dict | None:
        return self._get(f"/gear/{gear_id}")
