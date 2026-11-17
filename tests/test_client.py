import pytest

from runcoach.strava.auth import Tokens, TokenStore
from runcoach.strava.cache import Cache
from runcoach.strava.client import StravaClient
from runcoach.strava.errors import AuthError, RateLimitError
from runcoach.strava.sync import sync_recent


class Resp:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code, self._p, self.headers, self.text = status, payload, headers or {}, str(payload)

    def json(self):
        return self._p


class FakeSession:
    """Routes calls to a handler(method, url, params) -> Resp and records them."""
    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def request(self, method, url, params=None, headers=None, timeout=None):
        self.calls.append((method, url, params, headers))
        return self.handler(method, url, params)

    def post(self, url, data=None, timeout=None):
        self.calls.append(("POST", url, data, None))
        return self.handler("POST", url, data)


def _store(tmp_path, expires_at):
    s = TokenStore(tmp_path / "tokens.json")
    s.save(Tokens("old-access", "old-refresh", expires_at))
    return s


def _refresh_resp():
    return Resp(200, {"access_token": "new-access", "refresh_token": "new-refresh", "expires_at": 9_999_999_999})


def test_expired_token_is_refreshed_and_saved(tmp_path):
    def handler(method, url, params):
        return _refresh_resp() if method == "POST" else Resp(200, [])
    store = _store(tmp_path, expires_at=100)
    client = StravaClient("id", "secret", store, FakeSession(handler), clock=lambda: 1000)
    assert client.list_activities() == []
    assert store.load().refresh_token == "new-refresh"
    assert client.session.calls[1][3]["Authorization"] == "Bearer new-access"


def test_401_triggers_one_refresh_then_retry(tmp_path):
    state = {"gets": 0}
    def handler(method, url, params):
        if method == "POST":
            return _refresh_resp()
        state["gets"] += 1
        return Resp(401, {}) if state["gets"] == 1 else Resp(200, [{"id": 1}])
    client = StravaClient("id", "secret", _store(tmp_path, 9_999_999_999), FakeSession(handler))
    assert client.list_activities() == [{"id": 1}]


def test_second_401_raises_auth_error(tmp_path):
    def handler(m, u, p):
        return _refresh_resp() if m == "POST" else Resp(401, {})

    client = StravaClient("id", "secret", _store(tmp_path, 9_999_999_999), FakeSession(handler))
    with pytest.raises(AuthError):
        client.get_activity(1)


def test_429_raises_rate_limit_and_usage_is_tracked(tmp_path):
    headers = {"X-RateLimit-Limit": "100,1000", "X-RateLimit-Usage": "100,500"}
    client = StravaClient("id", "secret", _store(tmp_path, 9_999_999_999),
                          FakeSession(lambda m, u, p: Resp(429, {}, headers)))
    with pytest.raises(RateLimitError):
        client.get_laps(1)
    assert client.usage == (100, 500) and client.limit == (100, 1000)


def test_pagination_stops_on_short_page(tmp_path):
    pages = {1: [{"id": 1}, {"id": 2}], 2: [{"id": 3}]}
    client = StravaClient("id", "secret", _store(tmp_path, 9_999_999_999),
                          FakeSession(lambda m, u, p: Resp(200, pages[p["page"]])))
    assert [a["id"] for a in client.list_activities(per_page=2)] == [1, 2, 3]
    assert len(client.session.calls) == 2


def test_streams_request_uses_key_by_type(tmp_path):
    client = StravaClient("id", "secret", _store(tmp_path, 9_999_999_999),
                          FakeSession(lambda m, u, p: Resp(200, {"time": {"data": [0, 1]}})))
    assert client.get_streams(5)["time"]["data"] == [0, 1]
    params = client.session.calls[0][2]
    assert params["key_by_type"] == "true" and "velocity_smooth" in params["keys"]


def test_sync_fetches_runs_only_and_skips_cached(tmp_path):
    listing = [
        {"id": 10, "sport_type": "Run", "start_date_local": "2026-10-08T16:25:48Z"},
        {"id": 11, "sport_type": "Walk", "start_date_local": "2026-10-09T08:12:16Z"},
    ]
    def handler(method, url, params):
        if url.endswith("/athlete/activities"):
            return Resp(200, listing)
        if url.endswith("/activities/10"):
            return Resp(200, {"id": 10, "name": "Afternoon Run"})
        if url.endswith("/laps"):
            return Resp(200, [{"distance": 1000}])
        if url.endswith("/streams"):
            return Resp(200, {"time": {"data": [0]}})
        return Resp(404, {})
    client = StravaClient("id", "secret", _store(tmp_path, 9_999_999_999), FakeSession(handler))
    cache = Cache(tmp_path / "cache")
    first = sync_recent(client, cache, days=14, now=1_790_000_000)
    assert (first.fetched, first.skipped) == (1, 0) and cache.ids("activity") == ["10"]
    second = sync_recent(client, cache, days=14, now=1_790_000_000)
    assert (second.fetched, second.skipped) == (0, 1)


def test_sync_stops_cleanly_on_rate_limit(tmp_path):
    listing = [{"id": 1, "sport_type": "Run", "start_date_local": "2026-10-01T06:00:00Z"}]
    def handler(method, url, params):
        return Resp(200, listing) if url.endswith("/athlete/activities") else Resp(429, {})
    client = StravaClient("id", "secret", _store(tmp_path, 9_999_999_999), FakeSession(handler))
    res = sync_recent(client, Cache(tmp_path / "c"), days=7, now=1_790_000_000)
    assert res.stopped_by_rate_limit and res.fetched == 0


def test_read_rate_limit_headers_are_tracked_separately(tmp_path):
    headers = {"X-RateLimit-Limit": "200,2000", "X-RateLimit-Usage": "10,28",
               "X-ReadRateLimit-Limit": "100,1000", "X-ReadRateLimit-Usage": "90,300"}
    client = StravaClient("id", "secret", _store(tmp_path, 9_999_999_999),
                          FakeSession(lambda m, u, p: Resp(200, [], headers)))
    client.list_activities()
    assert client.limit == (200, 2000) and client.read_limit == (100, 1000) and client.read_usage == (90, 300)
