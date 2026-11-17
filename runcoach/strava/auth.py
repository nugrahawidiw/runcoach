"""Strava OAuth2: authorize once in a browser, then refresh tokens automatically."""
from __future__ import annotations

import json
import os
import time
import webbrowser
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from .errors import AuthError

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
DEFAULT_SCOPE = "read,activity:read_all"


@dataclass
class Tokens:
    access_token: str
    refresh_token: str
    expires_at: float          # epoch seconds

    def expired(self, now: float | None = None, margin: float = 60.0) -> bool:
        return (now if now is not None else time.time()) >= self.expires_at - margin


class TokenStore:
    """Tokens live in one JSON file with owner-only permissions."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> Tokens | None:
        if not self.path.exists():
            return None
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return Tokens(raw["access_token"], raw["refresh_token"], float(raw["expires_at"]))

    def save(self, tokens: Tokens) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(tokens)), encoding="utf-8")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass


def authorize_url(client_id: str, redirect_uri: str, scope: str = DEFAULT_SCOPE) -> str:
    query = urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "approval_prompt": "auto",
        "scope": scope,
    })
    return f"{AUTHORIZE_URL}?{query}"


def _token_request(payload: dict, session) -> Tokens:
    resp = session.post(TOKEN_URL, data=payload, timeout=30)
    if resp.status_code != 200:
        raise AuthError(f"Token request failed ({resp.status_code}): {resp.text[:200]}")
    data = resp.json()
    return Tokens(data["access_token"], data["refresh_token"], float(data["expires_at"]))


def exchange_code(client_id: str, client_secret: str, code: str, session=None) -> Tokens:
    return _token_request({
        "client_id": client_id, "client_secret": client_secret,
        "code": code, "grant_type": "authorization_code",
    }, session or requests)


def refresh_tokens(client_id: str, client_secret: str, refresh_token: str, session=None) -> Tokens:
    """Strava issues a NEW refresh token on every refresh; always store the result."""
    return _token_request({
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    }, session or requests)


def run_local_flow(client_id: str, client_secret: str, redirect_uri: str, store: TokenStore,
                   scope: str = DEFAULT_SCOPE, open_browser: bool = True, session=None) -> Tokens:
    """Open the consent page, catch the redirect on localhost, exchange the code, save tokens."""
    parsed = urlparse(redirect_uri)
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        raise AuthError("STRAVA_REDIRECT_URI must point at localhost for the built-in flow.")
    port = parsed.port or 80
    captured: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            if parsed.path and url.path != parsed.path:
                self.send_response(404); self.end_headers(); return
            q = parse_qs(url.query)
            captured["code"] = q.get("code", [None])[0]
            captured["error"] = q.get("error", [None])[0]
            captured["scope"] = q.get("scope", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"runcoach: authorization received. You can close this tab.")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    url = authorize_url(client_id, redirect_uri, scope)
    print(f"Open this URL if the browser does not start:\n{url}\n")
    if open_browser:
        webbrowser.open(url)
    server.timeout = 300
    for _ in range(5):                       # a browser may also request /favicon.ico
        server.handle_request()
        if captured.get("code") or captured.get("error"):
            break
    server.server_close()

    if captured.get("error") or not captured.get("code"):
        raise AuthError(f"Authorization failed: {captured.get('error') or 'no code returned'}")
    if "activity:read" not in captured.get("scope", ""):
        raise AuthError("Strava did not grant activity access. Tick 'View data about your activities' and retry.")
    tokens = exchange_code(client_id, client_secret, captured["code"], session)
    store.save(tokens)
    return tokens
