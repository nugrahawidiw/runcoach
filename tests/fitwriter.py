"""Minimal FIT file writer for tests (activity: file records, laps, session, activity message)."""
from __future__ import annotations

import datetime as dt
import struct

FIT_EPOCH = dt.datetime(1989, 12, 31, tzinfo=dt.UTC)
U8, ENUM, U16, U32 = 0x02, 0x00, 0x84, 0x86
_SIZE = {U8: 1, ENUM: 1, U16: 2, U32: 4}
_FMT = {U8: "B", ENUM: "B", U16: "<H", U32: "<I"}
_CRC = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
        0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]


def crc16(data: bytes) -> int:
    crc = 0
    for byte in data:
        tmp = _CRC[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC[byte & 0xF]
        tmp = _CRC[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC[(byte >> 4) & 0xF]
    return crc


def secs(ts: dt.datetime) -> int:
    return int((ts - FIT_EPOCH).total_seconds())


class FitBuilder:
    def __init__(self):
        self.body = bytearray()
        self._defs: dict[int, tuple] = {}

    def define(self, local: int, global_num: int, fields: list[tuple[int, int]]):
        """fields: [(field_def_number, base_type), ...]"""
        self.body += bytes([0x40 | local, 0, 0]) + struct.pack("<H", global_num) + bytes([len(fields)])
        for num, base in fields:
            self.body += bytes([num, _SIZE[base], base])
        self._defs[local] = tuple(fields)

    def data(self, local: int, values: list[int]):
        self.body += bytes([local])
        for (num, base), value in zip(self._defs[local], values):
            self.body += struct.pack(_FMT[base], int(value))

    def to_bytes(self) -> bytes:
        header = struct.pack("<BBHI4s", 14, 0x20, 2000, len(self.body), b".FIT")
        header += struct.pack("<H", crc16(header))
        payload = header + bytes(self.body)
        return payload + struct.pack("<H", crc16(payload))


def synthetic_run(start_utc: dt.datetime, utc_offset_h: int = 7) -> bytes:
    """600 s run: lap 1 (300 s, 3.0 m/s, +3% grade), lap 2 (300 s, 3.3 m/s, flat). 1 Hz records."""
    fb = FitBuilder()
    fb.define(0, 34, [(253, U32), (5, U32)])                                   # activity
    fb.data(0, [secs(start_utc) + 600, secs(start_utc) + 600 + utc_offset_h * 3600])
    fb.define(1, 20, [(253, U32), (5, U32), (73, U32), (3, U8), (4, U8), (78, U32)])  # record
    dist, alt = 0.0, 100.0
    for i in range(600):
        speed = 3.0 if i < 300 else 3.3
        grade = 0.03 if i < 300 else 0.0
        dist += speed
        alt += speed * grade
        hr = 130 + 30 * i / 599
        fb.data(1, [secs(start_utc) + i, dist * 100, speed * 1000, hr, 86, (alt + 500) * 5])
    # real Garmin laps carry sport=running (field 25), which renames avg_cadence to avg_running_cadence
    fb.define(2, 19, [(253, U32), (2, U32), (7, U32), (8, U32), (9, U32), (15, U8), (17, U8), (25, ENUM)])  # lap
    fb.data(2, [secs(start_utc) + 300, secs(start_utc), 300_000, 300_000, 90_000, 138, 86, 1])
    fb.data(2, [secs(start_utc) + 600, secs(start_utc) + 300, 300_000, 300_000, 99_000, 152, 86, 1])
    fb.define(3, 18, [(253, U32), (2, U32), (5, ENUM), (7, U32), (8, U32), (9, U32), (16, U8), (17, U8), (18, U8), (22, U16)])
    fb.data(3, [secs(start_utc) + 600, secs(start_utc), 1, 600_000, 600_000, 189_000, 145, 160, 86, 9])
    return fb.to_bytes()
