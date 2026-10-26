"""Read current U12 assessments and a bounded grammar without changing charts."""

from __future__ import annotations

import re
from copy import deepcopy

from ..adapters.charts.rules.registry import load_registry
from ..adapters.charts.tool_evidence import content_hash
from .consistency_text import ALIASES
from .learning_input import resolve_ref

SHORT_NAMES = {
    "伤官见官": "u12-combo-hurting-officer-officer",
    "官杀混杂": "u12-combo-officer-killer",
    "枭食同透": "u12-combo-indirect-seal-output",
    "食杀同透": "u12-combo-output-killer",
    "伤官印绶同透": "u12-combo-hurting-officer-seal",
}
CONDITIONS = {
    "pattern_condition",
    "extra_pattern",
    "exposed_combination",
    "wealth_weak",
    "climate_missing",
    "palace_activation",
}


def _identity(rows: list[dict], field: str, value: str) -> int:
    return sum(isinstance(row, dict) and row.get(field) == value for row in rows)


def _invalid(
    row: dict, assessments: list[dict], hits: list[dict], version: str, registry: dict
) -> str | None:
    if version != registry["version"]:
        return "u12_version_unsupported"
    if (
        not isinstance(row.get("rule_id"), str)
        or not re.fullmatch(r"u12-[a-z0-9]+(?:-[a-z0-9]+)*", row["rule_id"])
        or not isinstance(row.get("name"), str)
        or not 1 <= len(row["name"]) <= 240
        or _identity(assessments, "rule_id", row["rule_id"]) != 1
        or _identity(assessments, "name", row["name"]) != 1
    ):
        return "u12_identity_ambiguous"
    if type(row.get("met")) is not bool:
        return "u12_met_not_boolean"
    if row.get("condition_ref") not in CONDITIONS or not isinstance(
        row.get("details"), dict
    ):
        return "u12_assessment_incomplete"
    registered = next(
        (item for item in registry["rules"] if item["rule_id"] == row["rule_id"]), None
    )
    if registered is None:
        return "u12_rule_unregistered"
    if content_hash({key: row.get(key) for key in registered}) != content_hash(
        registered
    ):
        return "u12_registry_metadata_mismatch"
    matching = [
        hit
        for hit in hits
        if isinstance(hit, dict) and hit.get("rule_id") == row["rule_id"]
    ]
    if row["met"]:
        if len(matching) != 1 or content_hash(matching[0]) != content_hash(row):
            return "u12_hit_assessment_mismatch"
    elif matching:
        return "u12_false_has_hit"
    paths = row.get("evidence_paths")
    if not isinstance(paths, list) or any(
        not isinstance(path, str) or not path.startswith("/data/") for path in paths
    ):
        return "u12_evidence_paths_invalid"
    return None


def _row(row: dict, index: int, p8: dict, ref: dict, registry: dict) -> dict:
    return {
        "field": "u12_rule",
        "key": row.get("rule_id"),
        "value": row.get("met"),
        "ref": {
            "document_id": ref["document_id"],
            "path": ref["path"] + f"/p8/rule_assessments/{index}",
        },
        "root_ref": deepcopy(ref),
        "name": row.get("name"),
        "rules_version": p8.get("rules_version"),
        "invalid_reason": _invalid(
            row,
            p8["rule_assessments"],
            p8["rule_hits"],
            p8.get("rules_version"),
            registry,
        ),
        "assessment": deepcopy(row),
    }


def assessment_facts(chart: dict, documents: dict) -> list[dict]:
    if chart["request"]["system"] != "bazi":
        return []
    facts, registry = [], load_registry()
    for ref in chart["view"]["primary"]:
        data = resolve_ref(documents, ref)
        p8 = data.get("p8", {})
        rows, hits = p8.get("rule_assessments"), p8.get("rule_hits")
        if (
            not isinstance(rows, list)
            or not isinstance(hits, list)
            or not 1 <= len(rows) <= 40
            or any(not isinstance(row, dict) for row in rows)
        ):
            facts.append(
                {
                    "invalid_reason": "u12_assessment_incomplete",
                    "key": None,
                    "name": None,
                }
            )
            continue
        for index, row in enumerate(rows):
            if isinstance(row, dict):
                facts.append(_row(row, index, p8, ref, registry))
    return facts


def masked_labels(text: str, facts: list[dict]) -> str:
    """Native labels contain semicolons and '流年'; those are identifiers, not scope."""
    labels = {
        row["name"]
        for row in facts
        if row.get("invalid_reason") is None and isinstance(row.get("name"), str)
    }
    for label in sorted(labels, key=len, reverse=True):
        text = text.replace(label, "¤" * len(label))
    return text


def looks_like_rule(text: str, facts: list[dict]) -> bool:
    if re.search(
        r"规则|u12-|条件(?:未)?命中|枭神夺食|完整夺食|有效制杀|制杀有效|夺食有效|食神制杀|伤官配印|已成格|已经成格",
        text,
    ):
        return True
    return any(name in text for name in SHORT_NAMES) or any(
        row.get("invalid_reason") is None
        and isinstance(row.get("name"), str)
        and row["name"] in text
        for row in facts
    )


def _body(text: str, display_name: str) -> tuple[str, list[str]]:
    names = ALIASES.findall(text)
    body = ALIASES.sub("", text).strip()
    owners = [
        "你的",
        "你",
        "本盘的",
        "本盘",
        "此盘的",
        "此盘",
        "该盘的",
        "该盘",
        "我的",
        "我",
    ]
    if display_name:
        owners[:0] = [display_name + "的", display_name]
    for owner in owners:
        if body.startswith(owner):
            body = body[len(owner) :].strip().lstrip("：:").strip()
            break
    return body, names


def parse_rule(text: str, display_name: str) -> tuple[dict, list[str]]:
    body, names = _body(text, display_name)
    if re.search(
        r"完整夺食|枭神夺食|食神制杀|有效制杀|制杀有效|夺食有效|已成格|已经成格|格局成立|伤官配印",
        body,
    ):
        return {"reason": "u12_effectiveness_not_evaluated"}, names
    match = re.fullmatch(
        r"规则\[(?P<key>[^\]\r\n]{1,240})\](?:的)?条件(?P<state>未命中|命中)", body
    )
    if not match:
        match = re.fullmatch(
            r"(?P<key>.{1,240}?)(?:的)?条件(?P<state>未命中|命中)", body
        )
    if match:
        return {"key": match["key"], "value": match["state"] == "命中"}, names
    short = "|".join(re.escape(name) for name in SHORT_NAMES)
    match = re.fullmatch(
        rf"(?P<op>这是|这不是|这并非|不是|并非|是|出现|没有出现)(?P<key>{short})", body
    )
    if match:
        return {
            "key": SHORT_NAMES[match["key"]],
            "value": match["op"]
            not in ("不是", "并非", "这不是", "这并非", "没有出现"),
        }, names
    return {"reason": "u12_assertion_not_explicit"}, names
