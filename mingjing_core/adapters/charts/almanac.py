"""Read-only named lunar-python almanac, independent of the host timezone."""

from __future__ import annotations

import hashlib
import importlib.metadata
import inspect
import json
import re
from datetime import date as Date
from functools import lru_cache
from pathlib import Path
from typing import Any

from .tool_evidence import evidence_result

VERSION = "p8-almanac-v1"
SUPPORTED_LIBRARY_VERSION = "1.4.8"
SOURCE = "https://6tail.cn/calendar/api.html"
CODE_SOURCE = "https://github.com/6tail/lunar-python"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
SCHOOL = "lunar-python-day-almanac-sect1"


def almanac_date(value: str) -> Date:
    """A civil date is not an instant and must never use the host zone."""
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
    ):
        raise ValueError("almanac_date_invalid：需要YYYY-MM-DD公历日期")
    try:
        parsed = Date.fromisoformat(value)
    except ValueError:
        raise ValueError("almanac_date_invalid：公历日期无效") from None
    if not 1901 <= parsed.year <= 2099:
        raise ValueError("almanac_date_out_of_range：当前范围为1901至2099年")
    return parsed


@lru_cache(maxsize=1)
def _package_identity() -> tuple[str, str, tuple[tuple[str, str], ...]]:
    version = importlib.metadata.version("lunar-python")
    if version != SUPPORTED_LIBRARY_VERSION:
        raise ValueError("almanac_library_version_unsupported")
    from lunar_python import Lunar

    package = Path(inspect.getfile(Lunar)).parent
    files = tuple(
        (
            path.relative_to(package).as_posix(),
            hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        )
        for path in sorted(package.rglob("*.py"))
    )
    encoded = json.dumps(dict(files), sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(encoded.encode("utf8")).hexdigest()
    return version, fingerprint, files


def _method() -> dict[str, Any]:
    version, fingerprint, files = _package_identity()
    return {
        "library": "lunar-python",
        "library_version": version,
        "library_source_sha256": fingerprint,
        "source_files_sha256": dict(files),
        "fingerprint_method": "sha256-canonical-sorted-relative-file-map-lf",
        "school": SCHOOL,
        "yi_ji_sect": 1,
        "month_boundary": "library-date-level-jie-month-for-almanac-sect1",
        "day_boundary": "civil-midnight",
        "date_timezone": "Asia/Shanghai",
        "solar_time_applied": False,
        "source_status": "library_output_original_edition_collation_pending",
    }


def _calendar_fields(lunar: Any, day: str) -> dict[str, Any]:
    return {
        "date": day,
        "calendar": "gregorian",
        "timezone": "Asia/Shanghai",
        "sample_at": day + "T12:00:00+08:00",
        "lunar": {
            "year": lunar.getYear(),
            "month": lunar.getMonth(),
            "day": lunar.getDay(),
            "is_leap_month": lunar.getMonth() < 0,
            "display": lunar.toString(),
        },
        "ganzhi": {
            "year": lunar.getYearInGanZhiByLiChun(),
            "month": lunar.getMonthInGanZhi(),
            "day": lunar.getDayInGanZhi(),
        },
        "yi": lunar.getDayYi(1),
        "ji": lunar.getDayJi(1),
        "chong_sha": {
            "branch": lunar.getDayChong(),
            "stem": lunar.getDayChongGan(),
            "zodiac": lunar.getDayChongShengXiao(),
            "display": lunar.getDayChongDesc(),
            "sha_direction": lunar.getDaySha(),
        },
    }


def _traditional_fields(lunar: Any) -> dict[str, Any]:
    return {
        "duty": {
            "deity": lunar.getDayTianShen(),
            "category": lunar.getDayTianShenType(),
            "luck": lunar.getDayTianShenLuck(),
            "officer": lunar.getZhiXing(),
        },
        "mansion": {
            "name": lunar.getXiu(),
            "luminary": lunar.getZheng(),
            "animal": lunar.getAnimal(),
            "luck": lunar.getXiuLuck(),
        },
        "pengzu": {"stem": lunar.getPengZuGan(), "branch": lunar.getPengZuZhi()},
    }


def _hits(data: dict[str, Any]) -> list[dict[str, Any]]:
    definitions = (
        ("yi", "库内宜事项", "Lunar.getDayYi(sect=1)"),
        ("ji", "库内忌事项", "Lunar.getDayJi(sect=1)"),
        ("duty", "值神与建除值星", "Lunar.getDayTianShen/getZhiXing"),
        ("mansion", "二十八宿", "Lunar.getXiu"),
        ("pengzu", "彭祖百忌", "Lunar.getPengZuGan/getPengZuZhi"),
        ("chong_sha", "日支冲煞结构", "Lunar.getDayChong/getDaySha"),
    )
    return [
        {
            "rule_id": "p8-almanac-" + key.replace("_", "-"),
            "met": True,
            "name": name,
            "school": SCHOOL,
            "source": {
                "title": "lunar-python每日黄历接口",
                "url": SOURCE,
                "locator": locator,
                "status": "named_library_fields_not_event_prediction",
            },
            "evidence_paths": ["/data/" + key, "/data/method"],
            "claim_kind": "traditional_calendar_label",
        }
        for key, name, locator in definitions
        if data[key]
    ]


def almanac_data(day: str) -> tuple[dict, list[dict], list[dict]]:
    """Keep library values unchanged; metadata states the chosen date convention."""
    parsed = almanac_date(day)
    method = _method()
    from lunar_python import Solar

    lunar = Solar.fromYmdHms(parsed.year, parsed.month, parsed.day, 12, 0, 0).getLunar()
    data = {
        **_calendar_fields(lunar, day),
        **_traditional_fields(lunar),
        "method": method,
    }
    opposite = BRANCHES[(BRANCHES.index(data["ganzhi"]["day"][1]) + 6) % 12]
    if data["chong_sha"]["branch"] != opposite:
        raise ValueError("almanac_library_inconsistent：冲支与日支不一致")
    sources = [
        {"title": "lunar官方API文档", "url": SOURCE},
        {
            "title": "lunar-python实际安装包源码",
            "url": CODE_SOURCE,
            "version": data["method"]["library_version"],
            "sha256": data["method"]["library_source_sha256"],
            "status": "original_edition_collation_pending",
        },
    ]
    return data, _hits(data), sources


def almanac(day: str) -> dict[str, Any]:
    data, hits, sources = almanac_data(day)
    result = evidence_result(VERSION, data, hits, sources)
    result["limits"] += [
        "宜忌、值神和宿等是具名历法库的传统标签，不是现实结果的承诺。",
        "库内古籍表的具体刻本与页码尚未校勘，不冒称已经核对某一版通书。",
        "黄历日期采用北京时间民用日，不对普通日期进行出生真太阳时换算。",
    ]
    return result
