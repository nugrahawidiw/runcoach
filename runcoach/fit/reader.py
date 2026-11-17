"""Read FIT files, zips of FIT files, or folders, into plain Message objects."""
from __future__ import annotations

import datetime as dt
import io
import logging
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import fitdecode

log = logging.getLogger("runcoach.fit")
FIT_EPOCH = dt.datetime(1989, 12, 31, tzinfo=dt.UTC)


@dataclass(frozen=True)
class Message:
    name: str
    fields: dict = field(default_factory=dict)
    file: str = ""

    def get(self, key, default=None):
        value = self.fields.get(key)
        return default if value is None else value


def fit_time(value) -> dt.datetime | None:
    """FIT timestamps arrive as datetimes (known fields) or epoch seconds (unknown fields)."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.UTC)
    return FIT_EPOCH + dt.timedelta(seconds=int(value))


def fit_seconds(value: dt.datetime) -> int:
    return int((value - FIT_EPOCH).total_seconds())


def iter_fit_bytes(data: bytes, name: str = "") -> Iterator[Message]:
    try:
        with fitdecode.FitReader(io.BytesIO(data), error_handling=fitdecode.ErrorHandling.IGNORE) as reader:
            for frame in reader:
                if frame.frame_type == fitdecode.FIT_FRAME_DATA:
                    yield Message(frame.name, {f.name: f.value for f in frame.fields}, name)
    except fitdecode.FitError as exc:
        log.warning("Skipping unreadable FIT file %s: %s", name or "<bytes>", exc)


def iter_path(path: str | Path) -> Iterator[Message]:
    """Messages from one .fit, one .zip of .fit files, or a folder of either (recursive)."""
    p = Path(path)
    if p.is_dir():
        for child in sorted(p.rglob("*")):
            if child.suffix.lower() in (".fit", ".zip"):
                yield from iter_path(child)
    elif p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as zf:
            for member in sorted(zf.namelist()):
                if member.lower().endswith(".fit"):
                    yield from iter_fit_bytes(zf.read(member), f"{p.name}:{member}")
    elif p.suffix.lower() == ".fit":
        yield from iter_fit_bytes(p.read_bytes(), p.name)
    else:
        raise ValueError(f"Not a .fit, .zip or folder: {p}")


def iter_groups(path: str | Path) -> Iterator[tuple[str, list[Message]]]:
    """Group messages per export. One zip = one group; a folder yields one group per zip."""
    p = Path(path)
    if p.is_dir():
        loose: list[Message] = []
        for child in sorted(p.iterdir()):
            if child.is_dir():
                yield from iter_groups(child)
            elif child.suffix.lower() == ".zip":
                yield child.stem, list(iter_path(child))
            elif child.suffix.lower() == ".fit":
                loose.extend(iter_path(child))
        if loose:
            yield p.name, loose
    else:
        yield p.stem, list(iter_path(p))
