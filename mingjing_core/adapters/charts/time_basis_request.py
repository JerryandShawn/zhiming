"""Scoped read-only time-basis entry; no life-event scoring or profile mutation."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from ...domain.json_values import ensure_finite_json
from .adapter import stable_id
from .boundary_alerts import boundary_alerts
from .p8_policy import release_policy
from .time_basis import time_basis_candidates
from .time_basis_chart import bazi_context, ziwei_column
from .time_basis_readout import attach_readout, rebase_column_evidence


def validate_request(request: dict[str, Any]) -> None:
    if not isinstance(request, dict):
        raise ValueError("时间口径核对请求必须为对象")
    ensure_finite_json(request)
    for key in ("owner_user_id", "subject_id", "operation_id"):
        if not isinstance(request.get(key), str) or not request[key].strip():
            raise ValueError("时间口径核对需要明确归属、人物和操作标识")
    if type(request.get("revision")) is not int or request["revision"] < 0:
        raise ValueError("时间口径核对需要有效的资料修订版本")
    if not isinstance(request.get("as_of_date"), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", request["as_of_date"]):
        raise ValueError("需要调用方Clock提供核对日期")
    date.fromisoformat(request["as_of_date"])
    birth = request.get("birth")
    if not isinstance(birth, dict) or birth.get("gender") not in ("男", "女"):
        raise ValueError("需要明确的出生资料和排盘性别参数")
    for key in ("owner_user_id", "subject_id"):
        if key in birth and birth[key] != request[key]:
            raise ValueError("出生资料归属或人物不匹配")
    if birth.get("precision", "reported") != "reported":
        raise ValueError("当前公开入口只核对已报告的准确时刻；未知时刻推断尚未接入")
    if date.fromisoformat(birth["date"]) > date.fromisoformat(request["as_of_date"]):
        raise ValueError("出生日期不能晚于核对日期")


def _charts(request: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    birth = request["birth"]
    variants = []
    for item in result["items"]:
        for candidate in item["source_variants"]:
            ident = stable_id(
                "time-chart-",
                [request["owner_user_id"], request["subject_id"], request["revision"], candidate],
            )
            data = bazi_context(candidate, request)
            column = ziwei_column(candidate, birth["gender"])
            rebase_column_evidence(column, f"/charts/{len(variants)}/ziwei_column")
            variants.append(
                dict(
                    id=ident,
                    candidate_group_id=item["id"],
                    time_basis=candidate,
                    data=data,
                    ziwei_column=column,
                )
            )
    return variants


def calculate_time_basis(request: dict[str, Any]) -> dict[str, Any]:
    from .p8_worker import source_hashes

    validate_request(request)
    birth = request["birth"]
    result = time_basis_candidates(
        birth["date"],
        birth.get("reported_time"),
        birth.get("place"),
        birth.get("clock_basis"),
        precision="reported",
        include_beijing=True,
    )
    variants = _charts(request, result)
    interpretation = attach_readout(result, variants)
    return {
        "version": "p8-time-basis-readonly-v2-review23",
        **{key: request[key] for key in ("owner_user_id", "subject_id", "revision", "operation_id")},
        "time_basis": result,
        "charts": variants,
        "boundary_alerts": boundary_alerts(result),
        "interpretation": interpretation,
        "profile_basis_record": {
            "basis": result["selected_basis"],
            "comparison_basis": "beijing_standard",
            "primary_chart_ids": interpretation["primary_chart_ids"],
            "method": "longitude_plus_NOAA_Meeus_equation_of_time",
            "policy_version": release_policy()["version"],
            "status": "readonly_proposal_not_persisted",
            "writes": 0,
        },
        "release_policy": release_policy(),
        "source_sha256": source_hashes(),
        "record_policy": "以记录为准；真太阳时主解读，按北京时间的不同结果并列；不改出生资料",
        "profile_update_allowed": False,
        "life_event_scoring_performed": False,
        "model_calls": 0,
        "writes": 0,
    }
