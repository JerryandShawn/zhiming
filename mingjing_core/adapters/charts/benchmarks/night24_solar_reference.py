"""Bounded offline EOT research helpers; the production NOAA method stays unchanged."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import math
import os
from calendar import isleap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..time_basis_solar import equation_of_time

THRESHOLD_SECONDS = 5.0
DATES = (
    (1, 1),
    (2, 11),
    (3, 20),
    (4, 15),
    (6, 21),
    (7, 26),
    (9, 22),
    (11, 3),
    (12, 21),
    (12, 31),
)
TIMES = ((0, 0, 0), (6, 0, 0), (12, 0, 0), (23, 59, 59))
SOURCES = {
    "swiss_manual": "https://www.astro.com/swisseph/swephprg.htm",
    "swiss_versioned_source": "https://raw.githubusercontent.com/aloistr/swisseph/v2.10.03/sweph.c",
    "noaa_method": "https://gml.noaa.gov/grad/solcalc/calcdetails.html",
}


def iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def grid() -> list[datetime]:
    moments = []
    for year in range(1901, 2100):
        days = (*DATES, (2, 29)) if isleap(year) else DATES
        moments.extend(
            datetime(year, month, day, *clock, tzinfo=UTC)
            for month, day in days
            for clock in TIMES
        )
    return sorted(moments)


def summarize(values: list[float]) -> dict[str, float | int | bool]:
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("研究统计须为非空有限数值")
    absolute = sorted(abs(value) for value in values)
    return {
        "count": len(values),
        "max_abs_seconds": absolute[-1],
        "p95_abs_seconds_nearest_rank": absolute[math.ceil(0.95 * len(values)) - 1],
        "rms_seconds": math.sqrt(sum(value * value for value in values) / len(values)),
        "mean_signed_seconds": sum(values) / len(values),
        "over_fixed_5_second_alarm": sum(
            value > THRESHOLD_SECONDS for value in absolute
        ),
        "sampled_research_alarm_clear": absolute[-1] <= THRESHOLD_SECONDS,
    }


class SwissReference:
    """Separate solar-RA/sidereal-time implementation with explicit fallback evidence."""

    def __init__(self) -> None:
        os.environ.pop("SE_EPHE_PATH", None)
        self.swe = importlib.import_module("swisseph")
        absent = Path(__file__).parent / "_night24_absent_ephemeris"
        if absent.exists():
            raise ValueError("研究空历表路径已存在，不能保证参考实现使用Moshier")
        self.swe.close()
        self.swe.set_ephe_path(str(absent.resolve()))
        self.swe.set_tid_acc(self.swe.TIDAL_MOSEPH)
        self.swe.set_delta_t_userdef(self.swe.DELTAT_AUTOMATIC)
        self.flags_seen: set[int] = set()

    def compare(self, moment: datetime) -> dict[str, Any]:
        utc = moment.astimezone(UTC)
        seconds = utc.second + utc.microsecond / 1e6
        jd_tt, jd_ut1 = self.swe.utc_to_jd(
            utc.year,
            utc.month,
            utc.day,
            utc.hour,
            utc.minute,
            seconds,
            self.swe.GREG_CAL,
        )
        jd_label = self.swe.julday(
            utc.year, utc.month, utc.day, utc.hour + utc.minute / 60 + seconds / 3600
        )
        noaa = equation_of_time(utc)
        physical, same_label = (
            self.swe.time_equ(jd_ut1) * 1440,
            self.swe.time_equ(jd_label) * 1440,
        )
        _, flags = self.swe.calc_ut(jd_ut1, self.swe.SUN, self.swe.FLG_EQUATORIAL)
        if (
            flags & (self.swe.FLG_JPLEPH | self.swe.FLG_SWIEPH | self.swe.FLG_MOSEPH)
            != self.swe.FLG_MOSEPH
        ):
            raise ValueError("Swiss参考旁证未返回显式要求的Moshier历表")
        self.flags_seen.add(int(flags))
        dut1 = (jd_ut1 - jd_label) * 86400
        return {
            "actual_UTC": iso(utc),
            "noaa_eot_minutes": noaa,
            "swiss_eot_at_UT1_minutes": physical,
            "swiss_eot_at_UTC_label_as_UT_minutes": same_label,
            "noaa_minus_swiss_eot_seconds": (noaa - physical) * 60,
            "noaa_minus_swiss_same_label_seconds": (noaa - same_label) * 60,
            "swiss_label_minus_UT1_eot_seconds": (same_label - physical) * 60,
            "swiss_inferred_UT1_minus_UTC_seconds": dut1,
            "noaa_minus_swiss_apparent_clock_seconds": (noaa - physical) * 60 - dut1,
            "JD_TT": jd_tt,
            "JD_UT1": jd_ut1,
            "JD_UTC_label_as_UT": jd_label,
        }

    def metadata(self) -> dict[str, Any]:
        return {
            "swisseph_version": str(self.swe.version),
            "pyswisseph_package_version": importlib.metadata.version("pyswisseph"),
            "reference_function": "swisseph.time_equ(JD_UT1) * 1440 minutes",
            "unit": "days converted to minutes",
            "sign": "local_apparent_minus_local_mean",
            "method": "apparent sidereal time minus apparent solar right ascension",
            "tidal_acceleration": float(self.swe.TIDAL_MOSEPH),
            "delta_t": "Swiss automatic model",
            "companion_calc_ut_flags": sorted(self.flags_seen),
            "flags_limit": "time_equ itself has no flags argument or returned flags; these are companion-call evidence",
            "time_scale_limit": "Swiss-inferred UT1, not IERS observations; pre1972 and future UTC caveats apply",
            "source_files_sha256": source_hashes(self.swe),
        }


def source_hashes(swe: Any) -> dict[str, str]:
    root = Path(__file__).resolve().parents[4]
    files = [Path(__file__), *Path(__file__).parent.glob("night24_solar*.py")]
    files.append(root / "mingjing_core/adapters/charts/time_basis_solar.py")
    result = {
        path.relative_to(root).as_posix(): hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for path in sorted(set(files))
    }
    result["installed_swisseph_extension_binary"] = hashlib.sha256(
        Path(swe.__file__).read_bytes()
    ).hexdigest()
    return result
