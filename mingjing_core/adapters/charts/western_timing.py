"""Scoped read-only dispatch to declared western timing techniques in Charts."""

from __future__ import annotations

from typing import Any

from ...domain.json_values import ensure_finite_json

PARAMETERS = {
    "secondary_progressions": ({"birth_at", "target_at"}, {"orb"}),
    "solar_return": ({"birth_at", "return_year", "longitude", "latitude"}, {"orb"}),
}


def validate_timing_request(request: dict[str, Any], owner: str | None = None) -> None:
    if not isinstance(request, dict):
        raise ValueError("西占时序请求必须为对象")
    ensure_finite_json(request)
    keys = {
        "owner_user_id",
        "subject_id",
        "revision",
        "operation_id",
        "technique",
        "args",
    }
    if set(request) != keys:
        raise ValueError("西占时序需要明确归属、版本、操作和登记的计算参数")
    for key in ("owner_user_id", "subject_id", "operation_id"):
        if not isinstance(request[key], str) or not request[key].strip():
            raise ValueError("西占时序请求缺少归属标识")
    if owner is not None and request["owner_user_id"] != owner:
        raise ValueError("西占时序请求归属不匹配")
    if type(request["revision"]) is not int or request["revision"] < 0:
        raise ValueError("西占时序需要有效的资料修订版本")
    technique, args = request["technique"], request["args"]
    if (
        not isinstance(technique, str)
        or technique not in PARAMETERS
        or not isinstance(args, dict)
    ):
        raise ValueError("西占时序只支持登记的计算方法")
    required, optional = PARAMETERS[technique]
    if not required <= args.keys() or set(args) - required - optional:
        raise ValueError("西占时序参数缺失或未登记")


def calculate_western_timing(request: dict[str, Any]) -> dict[str, Any]:
    from .astro_progressions import secondary_progressions
    from .astro_returns import solar_return
    from .p8_worker import source_hashes

    validate_timing_request(request)
    methods = {
        "secondary_progressions": secondary_progressions,
        "solar_return": solar_return,
    }
    data = methods[request["technique"]](**request["args"])
    return {
        "version": "p8-western-timing-readonly-v1",
        **{
            key: request[key]
            for key in (
                "owner_user_id",
                "subject_id",
                "revision",
                "operation_id",
                "technique",
            )
        },
        "data": data,
        "source_sha256": source_hashes(),
        "time_basis": "actual_UTC_not_true_solar",
        "profile_update_allowed": False,
        "prediction_validity": "not_established",
        "model_calls": 0,
        "writes": 0,
    }
