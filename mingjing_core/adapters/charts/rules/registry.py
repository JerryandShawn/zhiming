"""Versioned metadata validation, kept apart from pure condition functions."""

from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from .conditions import CONDITIONS

SCHOOLS = ("子平", "通用")
DOMAINS = ("事业", "财运", "婚恋", "六亲", "健康", "学业", "性格", "年运")
PATH = Path(__file__).resolve().parents[3] / "knowledge" / "p8_bazi" / "rules_v1.json"


def validate_registry(value: dict[str, Any]) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("version"), str):
        raise ValueError("规则注册表需要版本")
    rows = value.get("rules")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 40:
        raise ValueError("首批八字规则须为1至40条")
    ids: set[str] = set()
    required = {
        "rule_id",
        "school",
        "name",
        "condition_ref",
        "parameters",
        "evidence_fields",
        "priority",
        "domains",
        "time_scale",
        "source",
        "claim_kind",
        "notes",
    }
    for row in rows:
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError("规则注册表字段不匹配")
        if (
            not isinstance(row["rule_id"], str)
            or not row["rule_id"]
            or row["rule_id"] in ids
        ):
            raise ValueError("规则标识必须唯一")
        ids.add(row["rule_id"])
        _validate_row(row)


def _validate_row(row: dict[str, Any]) -> None:
    if (
        row["school"] not in SCHOOLS
        or not isinstance(row["condition_ref"], str)
        or row["condition_ref"] not in CONDITIONS
    ):
        raise ValueError("未登记的流派或纯条件函数")
    if row["claim_kind"] != "traditional" or row["time_scale"] not in (
        "natal",
        "decade",
        "year",
        "month",
        "day",
    ):
        raise ValueError("规则类型或时间尺度不匹配")
    priority = row["priority"]
    if not isinstance(priority, dict) or set(priority) != set(SCHOOLS):
        raise ValueError("优先级需要全部具名口径")
    if any(type(v) is not int or not 1 <= v <= 5 for v in priority.values()):
        raise ValueError("优先级须逐流派登记为1至5的项目口径")
    if (
        not isinstance(row["domains"], list)
        or not row["domains"]
        or not set(row["domains"]) <= set(DOMAINS)
    ):
        raise ValueError("规则领域未登记")
    fields = row["evidence_fields"]
    if (
        not isinstance(fields, list)
        or not fields
        or any(not isinstance(p, str) or not p.startswith("/data/") for p in fields)
    ):
        raise ValueError("规则依据须为产物JSON Pointer")
    if not isinstance(row["parameters"], dict) or not all(
        isinstance(row[k], str) and row[k] for k in ("name", "notes")
    ):
        raise ValueError("规则需要参数、名称与边界说明")
    source = row["source"]
    if source is not None and (
        not isinstance(source, dict)
        or not all(source.get(k) for k in ("book", "chapter"))
    ):
        raise ValueError("传统来源必须包含书名和章节")
    _validate_parameters(row["condition_ref"], row["parameters"])


def _validate_parameters(condition: str, params: dict[str, Any]) -> None:
    if condition == "pattern_condition":
        if (
            set(params)
            not in ({"god", "condition_index"}, {"god", "condition_index", "qi_rank"})
            or params["god"]
            not in ("正官", "七杀", "正印", "偏印", "正财", "偏财", "食神", "伤官")
            or type(params["condition_index"]) is not int
            or params["condition_index"] not in (0, 1, 2)
        ):
            raise ValueError("格局条件参数无效")
        if "qi_rank" in params and (
            params["condition_index"] != 0
            or params["qi_rank"] not in ("any", "本气", "中气", "余气")
        ):
            raise ValueError("气位筛选只能用于月藏条件")
    elif condition == "extra_pattern":
        if set(params) != {"pattern"} or params["pattern"] not in (
            "建禄",
            "月劫",
            "阳刃",
        ):
            raise ValueError("增补格局需具名")
    elif condition == "exposed_combination":
        gods = params.get("gods")
        if (
            set(params) != {"gods"}
            or not isinstance(gods, list)
            or len(gods) != 2
            or len(set(gods)) != 2
        ):
            raise ValueError("十神组合需要两个不同标签")
    elif condition == "palace_activation":
        if set(params) != {"palace"} or params["palace"] not in (
            "year",
            "month",
            "day",
            "hour",
        ):
            raise ValueError("冲合规则必须指向原局柱")
    elif params:
        raise ValueError("该条件不接受额外参数")


@lru_cache(maxsize=1)
def _loaded() -> dict[str, Any]:
    value = json.loads(PATH.read_text(encoding="utf-8"))
    validate_registry(value)
    return value


def load_registry() -> dict[str, Any]:
    return deepcopy(_loaded())


def interaction_policy() -> dict[str, Any]:
    return deepcopy(_loaded()["interaction_mapping"])
