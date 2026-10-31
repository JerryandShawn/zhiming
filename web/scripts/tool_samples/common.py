"""Shared typed evidence checks; source values never appear in errors."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path

WEB = Path(__file__).resolve().parents[2]
REPOSITORY = WEB.parent
SOURCE_REF = "origin/v4/p8-calc"
PREFIX = "docs/v4/contracts/samples/"
FILES = (
    "window-search-ayuan-contract-20261021-27.json",
    "window-search-ayuan-page2.json",
    "window-search-ayuan-empty.json",
    "synastry-ayuan-xiaohe.json",
)
PURPOSES = ("签约", "面试", "搬家", "出行", "表白", "开业")
STEMS, BRANCHES, ELEMENTS = "甲乙丙丁戊己庚辛壬癸", "子丑寅卯辰巳午未申酉戌亥", "木火土金水"
PILLARS = ("year", "month", "day", "hour")
PLANETS = ("太阳", "月亮", "水星", "金星", "火星", "木星", "土星", "天王", "海王", "冥王")
ASPECTS = {"合相": 0, "六合": 60, "刑相": 90, "拱相": 120, "冲相": 180}
LABELS = {
    "bazi_relation": ("六冲", "六合", "三刑", "自刑", "六害", "六破", "天干五合", "天干相克", "三合", "三会"),
    "bazi_ten_god": ("比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印"),
    "ziwei_mutagen": ("禄", "权", "科", "忌"),
    "astro_aspect": tuple(ASPECTS),
}
LIMITS = [
    "仅离线合成样例，不是你的资料或本次实时计算。",
    "依据短别名只对当前结果有效，不能跨结果借用。",
    "盘面结构不证明现实预测有效；本页没有保存、发送或调用模型。",
]
INVALID_SOURCE = (KeyError, IndexError, TypeError, ValueError, OverflowError, AttributeError)


def need(condition: bool) -> None:
    if not condition:
        raise ValueError("tool_public_projection_invalid")


def digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf8")).hexdigest()


def integer(value: object, low: int = 0, high: int | None = None) -> int:
    need(type(value) is int and low <= value and (high is None or value <= high))
    return value


def number(value: object, low: float, high: float) -> float:
    need(type(value) in (int, float) and math.isfinite(value) and low <= value <= high)
    return value


def day(value: object) -> str:
    need(isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is not None)
    need(1901 <= date.fromisoformat(value).year <= 2099)
    return value


def tokens(values: object, allowed: object, maximum: int = 100) -> list:
    choices = frozenset(allowed)
    need(isinstance(values, list) and len(values) <= maximum)
    need(all(isinstance(item, str) and item in choices for item in values))
    return list(values)


def chinese(value: object) -> str:
    need(isinstance(value, str) and re.fullmatch(r"[\u3400-\u9fff]{1,12}", value) is not None)
    return value


def pillars(value: dict) -> dict:
    need(isinstance(value, dict) and set(value) == set(PILLARS))
    for item in value.values():
        need(isinstance(item, str) and len(item) == 2 and item[0] in STEMS and item[1] in BRANCHES)
    return {key: value[key] for key in PILLARS}


def pointer(value: object, path: str) -> object:
    need(isinstance(path, str) and path.startswith("/") and re.search(r"~(?![01])", path) is None)
    for part in path[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            need(re.fullmatch(r"0|[1-9][0-9]*", key) is not None and int(key) < len(value))
            value = value[int(key)]
        else:
            need(isinstance(value, dict) and key in value)
            value = value[key]
    return value


def verify_scope(scope: dict, version: str) -> None:
    names = ("subject_id", "revision", "operation_id")
    if version == "p8-synastry-v1":
        names = ("subject_ids", "revisions", "operation_ids")
    need(isinstance(scope, dict) and set(scope) == {"owner_user_id", *names})
    need(isinstance(scope["owner_user_id"], str) and scope["owner_user_id"].startswith("synthetic-"))
    for key in names:
        values = scope[key] if key.endswith("s") else [scope[key]]
        need(isinstance(values, list) and len(values) == (2 if key.endswith("s") else 1))
        for value in values:
            if key in ("revision", "revisions"):
                integer(value)
            else:
                need(isinstance(value, str) and value.startswith("synthetic-"))


def verify_aliases(root: dict) -> None:
    aliases = root["aliases"]
    need(isinstance(aliases, dict) and set(aliases) == {"c", "r"})
    for hit in root["rule_hits"]:
        need(isinstance(hit, dict) and isinstance(hit.get("evidence_paths"), list))
        need(bool(hit["evidence_paths"]) and all(isinstance(path, str) for path in hit["evidence_paths"]))
        need(isinstance(hit.get("rule_id"), str) and bool(hit["rule_id"]))
    paths = sorted({path for hit in root["rule_hits"] for path in hit["evidence_paths"]})
    need(isinstance(aliases["c"], list) and isinstance(aliases["r"], list))
    need(len(aliases["c"]) == len(paths) and len(aliases["r"]) == len(root["rule_hits"]))
    names = {}
    for index, (path, alias) in enumerate(zip(paths, aliases["c"], strict=True), 1):
        need(path.startswith("/data/") and alias["path"] == path and alias["alias"] == f"c{index}")
        names[path] = alias["alias"]
    for index, (hit, alias) in enumerate(zip(root["rule_hits"], aliases["r"], strict=True)):
        need(hit["met"] is True and bool(hit["school"]) and bool(hit["source"]))
        need(alias["path"] == f"/rule_hits/{index}" and alias["alias"] == f"r{index + 1}")
        need(alias["rule_id"] == hit["rule_id"])
        need(alias["evidence_aliases"] == [names[path] for path in hit["evidence_paths"]])
    for alias in aliases["c"] + aliases["r"]:
        value_hash = digest(pointer(root, alias["path"]))
        need(value_hash == alias["value_sha256"])
        need(alias["claim_id"] == "claim-" + digest([root["document_id"], alias["path"], value_hash]))


def verify(root: dict, version: str) -> None:
    keys = {"version", "scope", "data", "rule_hits", "sources", "document_id", "aliases", "effects", "limits"}
    need(isinstance(root, dict) and set(root) == keys)
    need(root["version"] == version and isinstance(root["rule_hits"], list) and isinstance(root["data"], dict))
    need(isinstance(root["sources"], list) and bool(root["sources"]))
    body = {key: root[key] for key in ("version", "scope", "data", "rule_hits", "sources")}
    need(root["document_id"] == "tool-" + digest(body))
    effects = root["effects"]
    need(effects == {"model_calls": 0, "writes": 0, "alias_registry": "ephemeral_only"})
    need(type(effects["model_calls"]) is int and type(effects["writes"]) is int)
    verify_scope(root["scope"], version)
    verify_aliases(root)


def ref(root: dict, alias: str) -> dict:
    return {"document_id": root["document_id"], "alias": alias}


def unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        need(key not in result)
        result[key] = value
    return result
