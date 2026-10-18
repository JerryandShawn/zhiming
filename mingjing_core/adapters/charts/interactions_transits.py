"""Bounded transit windows using real Swiss Ephemeris positions in Charts only."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Any

ASPECTS = {"合相": 0, "六合": 60, "刑相": 90, "拱相": 120, "冲相": 180}
BODIES = (
    "太阳",
    "月亮",
    "水星",
    "金星",
    "火星",
    "木星",
    "土星",
    "天王",
    "海王",
    "冥王",
)
ROOT_SECONDS = 2


def _utc(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("行运区间必须带明确时区")
    return result.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _number(value: float, lower: float, upper: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not isfinite(value)
    ):
        raise ValueError("行运数值必须有限")
    if not lower <= value <= upper:
        raise ValueError("行运数值超出搜索范围")
    return float(value)


def _error(longitude: float, center: float) -> float:
    return (longitude - center + 180) % 360 - 180


def _bisect(
    function: Callable[[datetime], float], left: datetime, right: datetime
) -> datetime:
    initial = function(left)
    if initial == 0:
        return left
    if function(right) == 0:
        return right
    while (right - left).total_seconds() > ROOT_SECONDS:
        middle = left + (right - left) / 2
        value = function(middle)
        if value == 0:
            return middle
        if initial * value <= 0:
            right = middle
        else:
            left, initial = middle, value
    return left + (right - left) / 2


def _roots(
    function: Callable[[datetime], float],
    points: list[datetime],
    *,
    wrap_filter: bool = False,
) -> list[datetime]:
    roots: list[datetime] = []
    for left, right in zip(points[:-1], points[1:], strict=True):
        a, b = function(left), function(right)
        if wrap_filter and max(abs(a), abs(b)) >= 90:
            continue
        if a * b <= 0:
            found = _bisect(function, left, right)
            if not roots or (found - roots[-1]).total_seconds() > ROOT_SECONDS:
                roots.append(found)
    return roots


def _windows(
    error: Callable[[datetime], float],
    points: list[datetime],
    orb: float,
    stations: list[datetime],
) -> list[dict[str, Any]]:
    edges = [points[0], points[-1]]
    for limit in (-orb, orb):
        edges += _roots(
            lambda moment, limit=limit: error(moment) - limit, points, wrap_filter=True
        )
    edges = sorted(set(edges))
    exact = _roots(error, points, wrap_filter=True)
    windows = []
    for left, right in zip(edges[:-1], edges[1:], strict=True):
        if abs(error(left + (right - left) / 2)) > orb:
            continue
        exact_points = [_iso(moment) for moment in exact if left <= moment <= right]
        windows.append(
            {
                "entry_at": None
                if left == points[0] and abs(error(left)) < orb
                else _iso(left),
                "window_start": _iso(left),
                "exact_at": exact_points,
                "window_end": _iso(right),
                "exit_at": None
                if right == points[-1] and abs(error(right)) < orb
                else _iso(right),
                "start_clipped": left == points[0] and abs(error(left)) < orb,
                "end_clipped": right == points[-1] and abs(error(right)) < orb,
                "phases": _phases(error, left, right, sorted(set(exact + stations))),
            }
        )
    return windows


def _phases(
    error: Callable[[datetime], float],
    left: datetime,
    right: datetime,
    exact: list[datetime],
) -> list[dict[str, Any]]:
    points = [left] + [point for point in exact if left < point < right] + [right]
    phases = []
    for start, end in zip(points[:-1], points[1:], strict=True):
        before, after = (
            abs(error(start + (end - start) / 4)),
            abs(error(start + (end - start) * 3 / 4)),
        )
        phases.append(
            {
                "start": _iso(start),
                "end": _iso(end),
                "phase": "入相" if after < before else "出相",
            }
        )
    return phases


def _position_reader(
    body: str,
) -> tuple[Callable[[datetime], tuple[float, float]], set[int], str]:
    swe = importlib.import_module("swisseph")
    flags_seen: set[int] = set()
    cache: dict[datetime, tuple[float, float]] = {}
    swe.set_ephe_path(None)

    def position(moment: datetime) -> tuple[float, float]:
        if moment not in cache:
            hour = (
                moment.hour
                + moment.minute / 60
                + (moment.second + moment.microsecond / 1e6) / 3600
            )
            jd = swe.julday(moment.year, moment.month, moment.day, hour)
            values, flags = swe.calc_ut(
                jd, BODIES.index(body), swe.FLG_MOSEPH | swe.FLG_SPEED
            )
            longitude, speed = values[0], values[3]
            if not isfinite(longitude) or not isfinite(speed):
                raise ValueError("历表返回非有限位置")
            if (
                flags & (swe.FLG_JPLEPH | swe.FLG_SWIEPH | swe.FLG_MOSEPH)
                != swe.FLG_MOSEPH
            ):
                raise ValueError("行运历表偏离显式Moshier口径")
            flags_seen.add(int(flags))
            cache[moment] = (longitude, speed)
        return cache[moment]

    return position, flags_seen, str(swe.version)


def _body_windows(
    body: str,
    natal_longitudes: dict[str, float],
    points: list[datetime],
    orb: float,
) -> tuple[list[dict[str, Any]], list[int], str]:
    position, seen, version = _position_reader(body)
    stations = _roots(lambda moment: position(moment)[1], points)
    samples = sorted(set(points + stations))
    rows = []
    for natal, longitude in natal_longitudes.items():
        rows += _aspect_rows(body, natal, longitude, position, samples, orb, stations)
    return rows, sorted(seen), version


def transit_windows(
    natal_longitudes: dict[str, float],
    start_at: str,
    end_at: str,
    *,
    moving_bodies: tuple[str, ...] = BODIES,
    orb: float = 2,
    step_hours: float = 1,
) -> dict[str, Any]:
    """Search a supplied period, retaining retrograde passes and clipped windows."""
    start, end = _utc(start_at), _utc(end_at)
    if not start < end or (end - start).total_seconds() > 366 * 86400:
        raise ValueError("行运区间须大于0且不超过366日")
    if (
        not natal_longitudes
        or len(natal_longitudes) > 10
        or not moving_bodies
        or len(set(moving_bodies)) != len(moving_bodies)
    ):
        raise ValueError("需要唯一的行运行星和本命位置")
    if not set(moving_bodies) <= set(BODIES):
        raise ValueError("行运行星不受支持")
    orb, step = _number(orb, 0.01, 10), _number(step_hours, 0.1, 6)
    for longitude in natal_longitudes.values():
        _number(longitude, 0, 360)
    points = [
        start + timedelta(hours=step * index)
        for index in range(int((end - start).total_seconds() / 3600 / step) + 1)
    ]
    points = sorted(set(points + [end]))
    rows, flag_sets, versions = [], {}, set()
    for body in moving_bodies:
        body_rows, flag_sets[body], version = _body_windows(
            body, natal_longitudes, points, orb
        )
        rows += body_rows
        versions.add(version)
    return {
        "version": "p8-transit-windows-v1",
        "method": "Moshier-tropical-geocentric-longitude-root-search",
        "requested_interval": {"start": _iso(start), "end": _iso(end)},
        "orb_degrees": orb,
        "sampling_step_hours": step,
        "root_bracket_seconds": ROOT_SECONDS,
        "swisseph_versions": sorted(versions),
        "returned_flags": flag_sets,
        "windows": rows,
        "source_refs": ["https://www.astro.com/swisseph/swephprg.htm"],
        "limits": [
            "有限步长搜索含速度变号驻点细分；不是连续数学完备性证明，切触或极短窗口仍可能遗漏。",
            "精确表示所用黄经相位方程的数值根；2秒是求根括区间，不是历表或民用UTC的准确度。",
            "只计算行运对固定本命黄经；不计算推运、回归盘或现实事件概率，不改变Placidus行为。",
        ],
    }


def _aspect_rows(
    body: str,
    natal: str,
    longitude: float,
    position: Callable[[datetime], tuple[float, float]],
    points: list[datetime],
    orb: float,
    stations: list[datetime],
) -> list[dict[str, Any]]:
    rows = []
    for label, angle in ASPECTS.items():
        for offset in sorted({angle % 360, (-angle) % 360}):
            center = (longitude + offset) % 360
            windows = _windows(
                lambda moment, center=center: _error(position(moment)[0], center),
                points,
                orb,
                stations,
            )
            rows += [
                {
                    "from": body,
                    "to": natal,
                    "aspect": label,
                    "angle": angle,
                    "oriented_offset": offset,
                    **row,
                }
                for row in windows
            ]
    return rows
