"""Map an authorized confirmed profile snapshot to the native P8 request."""

from __future__ import annotations

from datetime import date, datetime
import math
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mingjing_core.domain.contracts import EvidenceError, ScopeError


class P8InputsRequired(EvidenceError):
    code = "MISSING_INPUT"

    def __init__(self, fields: list[str]) -> None:
        self.fields = tuple(fields)
        super().__init__("请先通过资料确认流程补充或核对出生资料")


def natal_request(
    snapshot: dict[str, Any], *, owner: str, subject: str, operation_id: str, as_of: str
) -> dict[str, Any]:
    """Only consume a server-prepared snapshot; no birth or consent model input."""
    if snapshot.get("owner_user_id") != owner or snapshot.get("subject_id") != subject:
        raise ScopeError("P8出生资料快照归属不符")
    revision = snapshot.get("revision")
    if type(revision) is not int or revision < 0 or not isinstance(operation_id, str) or not operation_id:
        raise EvidenceError("P8出生资料调用身份无效")
    if not isinstance(as_of, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of) is None:
        raise EvidenceError("P8计算需要Clock提供明确目标日期")
    try:
        target = date.fromisoformat(as_of)
    except ValueError:
        raise EvidenceError("P8计算目标日期无效") from None
    profile = snapshot.get("profile")
    if not isinstance(profile, dict):
        raise P8InputsRequired(["birth.solar_datetime"])
    required = (
        "gender",
        "birth.solar_datetime",
        "birth.location.lng",
        "birth.location.lat",
        "birth.location.tz",
        "birth.clock_basis",
        "birth.precision",
    )
    missing = [key for key in required if key not in profile or profile[key] is None]
    missing.extend(key for key in snapshot.get("profile_conflicts", []) if key in required and key not in missing)
    if missing:
        raise P8InputsRequired(missing)
    _precision(profile)
    moment = _moment(profile["birth.solar_datetime"], target)
    place = _place(profile)
    if profile["gender"] not in ("男", "女"):
        raise P8InputsRequired(["gender"])
    if profile["birth.clock_basis"] not in ("clock", "standard", "unknown"):
        raise P8InputsRequired(["birth.clock_basis"])
    return {
        "owner_user_id": owner,
        "subject_id": subject,
        "revision": revision,
        "operation_id": operation_id,
        "as_of_date": as_of,
        "birth": {
            "date": moment.date().isoformat(),
            "reported_time": moment.time().isoformat(),
            "gender": profile["gender"],
            "place": place,
            "clock_basis": profile["birth.clock_basis"],
            "precision": "reported",
        },
    }


def _precision(profile: dict[str, Any]) -> None:
    if profile["birth.precision"] != "exact" or profile.get("birth.time_unknown") is True:
        raise P8InputsRequired(["birth.precision"])
    uncertainty = profile.get("birth.time_uncertainty_minutes")
    if uncertainty is not None and (type(uncertainty) not in (int, float) or uncertainty != 0):
        raise P8InputsRequired(["birth.time_uncertainty_minutes"])
    if profile.get("birth.interval_start") or profile.get("birth.interval_end"):
        raise P8InputsRequired(["birth.precision"])


def _moment(value: Any, target: date) -> datetime:
    if not isinstance(value, str) or re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value) is None:
        raise P8InputsRequired(["birth.solar_datetime"])
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise P8InputsRequired(["birth.solar_datetime"]) from None
    if moment.date() > target:
        raise P8InputsRequired(["birth.solar_datetime"])
    return moment


def _place(profile: dict[str, Any]) -> dict[str, Any]:
    zone = profile["birth.location.tz"]
    if not isinstance(zone, str):
        raise P8InputsRequired(["birth.location.tz"])
    try:
        ZoneInfo(zone)
    except (ValueError, ZoneInfoNotFoundError):
        raise P8InputsRequired(["birth.location.tz"]) from None
    result: dict[str, Any] = {"tz": zone}
    for field, key, low, high in (("lng", "lon", -180, 180), ("lat", "lat", -90, 90)):
        value = profile["birth.location." + field]
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not low <= value <= high
            or field == "lat"
            and abs(value) == 90
        ):
            raise P8InputsRequired(["birth.location." + field])
        result[key] = value
    return result
