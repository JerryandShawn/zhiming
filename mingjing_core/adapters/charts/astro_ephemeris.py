"""Explicit offline Moshier positions; UTC conversion belongs to Charts only."""

from __future__ import annotations

import importlib
import importlib.metadata
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Any

BODIES = ("太阳", "月亮", "水星", "金星", "火星", "木星", "土星", "天王", "海王", "冥王")
ASPECTS = {"合相": 0, "六合": 60, "刑相": 90, "拱相": 120, "冲相": 180}
SWISS_SOURCE = "https://www.astro.com/swisseph/swephprg.htm"


def finite(value: float, lower: float, upper: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("西占计算参数须为有限数值")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError("西占计算参数须为有限数值") from None
    if not isfinite(result):
        raise ValueError("西占计算参数须为有限数值")
    if not lower <= result <= upper:
        raise ValueError("西占计算参数超出支持范围")
    return result


def actual_utc(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError
        result = result.astimezone(UTC)
        if not 1800 <= result.year <= 2399:
            raise ValueError
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ValueError("西占时刻须带明确时区且在1800至2399年内") from None
    return result


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def signed_angle(longitude: float, center: float) -> float:
    return (longitude - center + 180) % 360 - 180


class Ephemeris:
    """A worker-local session with explicit Moshier tidal and automatic delta-T models."""

    def __init__(self) -> None:
        self.swe = importlib.import_module("swisseph")
        self.swe.set_ephe_path(None)
        # utc_to_jd has no ephemeris flag; pin its delta-T convention before conversion.
        self.swe.set_tid_acc(self.swe.TIDAL_MOSEPH)
        self.swe.set_delta_t_userdef(self.swe.DELTAT_AUTOMATIC)
        self.flags = self.swe.FLG_MOSEPH | self.swe.FLG_SPEED
        self.flags_seen: set[int] = set()

    def julian(self, moment: datetime) -> tuple[float, float]:
        utc = moment.astimezone(UTC)
        result = self.swe.utc_to_jd(
            utc.year,
            utc.month,
            utc.day,
            utc.hour,
            utc.minute,
            utc.second + utc.microsecond / 1e6,
            self.swe.GREG_CAL,
        )
        if not all(isfinite(value) for value in result):
            raise ValueError("历表返回非有限儒略日")
        return result

    def from_ut(self, jd_ut: float) -> datetime:
        year, month, day, hour, minute, second = self.swe.jdut1_to_utc(jd_ut, self.swe.GREG_CAL)
        # datetime has no leap-second representation; do not silently roll it forward.
        if second >= 60:
            raise ValueError("计算结果落在UTC闰秒内，当前输出不能表示")
        return datetime(year, month, day, hour, minute, tzinfo=UTC) + timedelta(seconds=second)

    def position(self, body: str, jd_ut: float) -> dict[str, Any]:
        if body not in BODIES:
            raise ValueError("不支持的西占天体")
        values, flags = self.swe.calc_ut(jd_ut, BODIES.index(body), self.flags)
        if not all(isfinite(value) for value in values):
            raise ValueError("历表返回非有限位置")
        mask = self.swe.FLG_JPLEPH | self.swe.FLG_SWIEPH | self.swe.FLG_MOSEPH
        if flags & mask != self.swe.FLG_MOSEPH:
            raise ValueError("历表偏离显式Moshier口径")
        self.flags_seen.add(int(flags))
        return {
            "longitude": values[0],
            "latitude": values[1],
            "distance_au": values[2],
            "speed_degrees_per_day": values[3],
            "retrograde": values[3] < 0,
            "returned_flags": int(flags),
        }

    def planets(self, jd_ut: float) -> dict[str, Any]:
        return {body: self.position(body, jd_ut) for body in BODIES}

    def metadata(self) -> dict[str, Any]:
        return {
            "engine": "pyswisseph",
            "swisseph_version": str(self.swe.version),
            "pyswisseph_version": importlib.metadata.version("pyswisseph"),
            "ephemeris": "Moshier",
            "requested_flags": int(self.flags),
            "returned_flags": sorted(self.flags_seen),
            "zodiac": "tropical",
            "coordinates": "geocentric apparent ecliptic longitude of date",
            "time_scale": "Swiss utc_to_jd: UTC -> TT and UT1; calc_ut uses UT1",
            "tidal_acceleration_arcsec_per_century_squared": float(self.swe.TIDAL_MOSEPH),
            "delta_t": "Swiss automatic model with explicit Moshier tidal acceleration; no user fixed delta-T",
            "utc_caveat": "1972年前由Swiss按UT1处理；未来UTC取决于其闰秒与Delta-T模型。",
            "legacy_difference": "v3以julday将民用UTC近似当UT；本入口不改动v3计算。",
        }


def aspects(left: dict[str, Any], right: dict[str, Any] | None, orb: float) -> list[dict[str, Any]]:
    limit = finite(orb, 0, 10)
    output = []
    for index, (body, position) in enumerate(left.items()):
        targets = list(right.items()) if right is not None else list(left.items())[index + 1 :]
        for target, natal in targets:
            separation = abs(signed_angle(position["longitude"], natal["longitude"]))
            for label, angle in ASPECTS.items():
                error = abs(separation - angle)
                if error <= limit:
                    output.append(
                        {
                            "from": body,
                            "to": target,
                            "aspect": label,
                            "angle": angle,
                            "orb_degrees": error,
                        }
                    )
    return sorted(output, key=lambda row: (row["orb_degrees"], row["from"], row["to"]))
