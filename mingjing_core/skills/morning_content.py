"""Deterministic daily reading cards; no calculation, scheduling or delivery."""

from __future__ import annotations

from copy import deepcopy
from datetime import date

from ..adapters.charts.tool_evidence import content_hash, evidence_result

VERSION = "p8-morning-content-v1"
LAYERS = {"daily": "流日", "monthly": "流月", "yearly": "流年"}


def _verified(result: dict, scope: dict, target_date: str) -> dict:
    try:
        keys = {"owner_user_id", "subject_id", "revision", "operation_id"}
        if not isinstance(scope, dict) or set(scope) != keys:
            raise ValueError
        if type(scope["revision"]) is not int or scope["revision"] < 1:
            raise ValueError
        if any(
            not isinstance(scope[key], str) or not scope[key].strip()
            for key in keys - {"revision"}
        ):
            raise ValueError
        if date.fromisoformat(target_date).isoformat() != target_date:
            raise ValueError
        if result["version"] != "p8-daily-transit-v1":
            raise ValueError
        if (
            content_hash(result["scope"]) != content_hash(scope)
            or result["data"]["date"] != target_date
        ):
            raise ValueError
        rebuilt = evidence_result(
            result["version"],
            result["data"],
            result["rule_hits"],
            result["sources"],
            result["scope"],
        )
        if any(result[key] != rebuilt[key] for key in ("document_id", "aliases")):
            raise ValueError
        if result["data"]["snapshot_at"] != target_date + "T12:00:00+08:00":
            raise ValueError
        if result["data"]["snapshot_at_utc"] != target_date + "T04:00:00Z":
            raise ValueError
        return rebuilt
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        raise ValueError("morning_content_input_invalid") from exc


def _wording(context: dict) -> tuple[str, str]:
    system, kind = context["system"], context["kind"]
    layer = LAYERS.get(context.get("layer"), "时间层")
    if (system, kind) == ("bazi", "ten_god"):
        return (
            f"{layer}天干按本命日干比较，十神为{context['ten_god']}。",
            "先挑一件今天真实要做的事，把需要的准备写下来；十神本身不决定事情的结果。",
        )
    if (system, kind) == ("bazi", "relation"):
        state = "成员齐备" if context["complete"] else "成员未齐"
        return (
            f"原局与目标时间层有{context['relation']}结构，{state}；未据此判定合化或事件。",
            "有重要安排就再核对一次时间、参与者和现实条件，不把结构标签当作预警。",
        )
    if (system, kind) == ("ziwei", "mutagen"):
        return (
            f"按本次安装库口径，{layer}化{context['mutagen']}映射到本命{context['natal_palace']}。",
            "可以留意自己在相关话题上的感受；先看实际情况，再决定是否需要行动。",
        )
    if (system, kind) == ("astro", "aspect"):
        return (
            f"行运{context['from']}与本命{context['to']}形成{context['aspect']}相位，"
            f"偏离{context['orb_degrees']:.3f}°，本次容许度{context['orb_limit']:g}°。",
            "把它当作一次整理感受的提示；今天怎么安排，仍以日程、身体感受和他人意愿为准。",
        )
    raise ValueError("morning_content_context_unsupported")


def _card(root: dict, index: int) -> dict:
    hit = root["rule_hits"][index]
    rule = root["aliases"]["r"][index]
    observation, action = _wording(hit["context"])
    names = rule["evidence_aliases"] + [rule["alias"]]
    citations = "".join("〔" + name + "〕" for name in names)
    return {
        "system": hit["context"]["system"],
        "observation": observation,
        "reflection": action,
        "text": observation + citations + " " + action,
        "c_aliases": list(rule["evidence_aliases"]),
        "r_aliases": [rule["alias"]],
        "school": deepcopy(hit["school"]),
        "source": deepcopy(hit["source"]),
    }


def _cards(root: dict) -> list[dict]:
    cards = []
    try:
        indices = sorted(
            range(len(root["rule_hits"])),
            key=lambda i: (root["rule_hits"][i]["context"].get("layer") != "daily", i),
        )
        for system in ("bazi", "ziwei", "astro"):
            selected = next(
                (
                    i
                    for i in indices
                    if root["rule_hits"][i]["context"]["system"] == system
                ),
                None,
            )
            if selected is not None:
                cards.append(_card(root, selected))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError("morning_content_context_invalid") from exc
    return cards


def morning_content(result: dict, *, expected_scope: dict, target_date: str) -> dict:
    """Use at most one card per system, preferring the actual daily layer."""
    root = _verified(result, expected_scope, target_date)
    cards = _cards(root)
    used = {
        name
        for card in cards
        for key in ("c_aliases", "r_aliases")
        for name in card[key]
    }
    return {
        "version": VERSION,
        "status": "ready" if cards else "insufficient_evidence",
        "scope": deepcopy(root["scope"]),
        "date": target_date,
        "source_document_id": root["document_id"],
        "snapshot_at": root["data"]["snapshot_at"],
        "points": cards,
        "aliases": {
            key: [deepcopy(row) for row in root["aliases"][key] if row["alias"] in used]
            for key in ("c", "r")
        },
        "rule_hits": [
            deepcopy(root["rule_hits"][int(name[1:]) - 1])
            for name in sorted(used)
            if name.startswith("r")
        ],
        "effects": {"model_calls": 0, "writes": 0, "sends": 0},
        "limits": [
            "北京时间正午单点快照，不表示全天走势，也不代表早晨已经发生。",
            "只校验内容绑定，不验证来源授权；调用方须校验可信计算、owner、修订及撤销状态。",
            "别名沿用该日原结果；主线登记到当前上下文后才可用于对话，不跨日拼接。",
            "各体系仅并列观察，不合成吉凶分数，不证明现实预测有效。",
        ],
    }
