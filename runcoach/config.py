"""Athlete profile and environment handling."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Profile:
    easy_band: tuple[float, float] = (399.0, 436.0)      # 6:39-7:16 /km, seconds
    goal_band: tuple[float, float] = (355.0, 367.0)      # 5:55-6:07
    tempo_band: tuple[float, float] = (336.0, 348.0)     # 5:36-5:48
    stride_cadence: tuple[int, int] = (181, 191)         # steps per minute
    easy_hr_guide: int = 145
    lthr: int = 169
    hr_rest: int = 55
    hr_max: int = 178
    sex: str = "male"


def load_profile(path: str | Path | None = None) -> Profile:
    """Load profile.toml if present; otherwise use the defaults."""
    p = Path(path) if path else Path("profile.toml")
    if not p.exists():
        return Profile()
    with p.open("rb") as fh:
        raw = tomllib.load(fh)
    known = {f.name for f in fields(Profile)}
    kwargs = {}
    for key, value in raw.items():
        if key not in known:
            raise ValueError(f"Unknown profile key: {key}")
        kwargs[key] = tuple(value) if isinstance(value, list) else value
    return Profile(**kwargs)


def load_env(path: str | Path = ".env") -> None:
    """Minimal .env loader (no extra dependency). Existing variables win."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def data_dir() -> Path:
    d = Path(os.environ.get("RUNCOACH_DATA", "./data"))
    d.mkdir(parents=True, exist_ok=True)
    return d
