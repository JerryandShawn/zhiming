"""Deterministic learning points, reusing actual caller-visible evidence aliases."""

from __future__ import annotations

from copy import deepcopy

from .learning_input import resolve_ref, verified_input

VERSION = "p8-learning-outline-v1"


def _covering_alias(aliases: dict, ref: dict) -> str | None:
    candidates = [
        row
        for name, row in aliases.items()
        if name.startswith("c")
        and row["ref"]["document_id"] == ref["document_id"]
        and (
            ref["path"] == row["ref"]["path"]
            or ref["path"].startswith(row["ref"]["path"] + "/")
        )
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda row: len(row["ref"]["path"]))["alias"]


def _primary_cards(value: dict, documents: dict, aliases: dict) -> list[dict]:
    cards = []
    for ref in value["view"]["primary"]:
        data = resolve_ref(documents, ref)
        name = _covering_alias(aliases, ref)
        if not name:
            continue
        system = value["request"]["system"]
        if system == "bazi":
            observed = data["pillars"]["day"]
            title, text = (
                "先找日主",
                f"这张盘日柱是{observed['ganzhi']}，日干{observed['gan']}是十神比较的参照。",
            )
            school = data["p8"]["ten_gods"]["school"]
            source = data["p8"]["ten_gods"]["source"]
        elif system == "ziwei":
            observed = {
                key: data[key] for key in ("ming_gong", "shen_gong", "wuxing_ju")
            }
            title, text = (
                "分清宫名与地支格",
                f"这次命宫在{data['ming_gong']}、身宫在{data['shen_gong']}，宫名与地支格分开读。",
            )
            school, source = (
                "installed-py-iztro-default",
                "https://docs.iztro.com/posts/palace",
            )
        elif system == "astro":
            observed = data["planets"]
            title, text = (
                "先读计算位置",
                "先从实际行星位置读起，再核相位角距；所用历表、时标和宫制须连同方法栏看。",
            )
            school, source = (
                data["method"],
                "https://www.astro.com/swisseph/swephprg.htm",
            )
        else:
            raise ValueError("learning_system_unsupported")
        cards.append(
            {
                "kind": "orientation",
                "title": title,
                "text": text,
                "observed": deepcopy(observed),
                "c_aliases": [name],
                "r_aliases": [],
                "source_refs": [deepcopy(source)],
                "school": deepcopy(school),
                "source_ref": deepcopy(ref),
            }
        )
    return cards


def _rule_card(row: dict, hit: dict) -> dict:
    boundary = row["ref"]["path"].startswith("/boundary_alerts/")
    details = hit.get("details", {})
    title = "核对临界候选" if boundary else hit.get("name", hit["rule_id"])
    if boundary:
        text = "这个时刻靠近口径交界。把实际候选并列核对，保留记录和默认主盘，不据此倒推出生时辰。"
        observed = {
            key: hit[key]
            for key in ("current_pillars", "alternatives", "distance_seconds")
        }
    elif hit.get("condition_ref") == "pattern_condition":
        text = f"这次检查的是“{details['condition']}”。先看下面的实际输入；单项满足还不能跳过另外条件说已成格。"
        observed = details["observed"]
    else:
        text = "先对照这条命中的实际成员、参数和适用层，再看来源；盘面标签不等于现实事件已经发生。"
        observed = details
    return {
        "kind": "boundary" if boundary else "matched_condition",
        "title": title,
        "text": text,
        "observed": deepcopy(observed),
        "c_aliases": list(row["evidence_aliases"]),
        "r_aliases": [row["alias"]],
        "source_ref": deepcopy(row["ref"]),
        "source_refs": [deepcopy(hit["source"])],
        "school": deepcopy(hit["school"]),
        "limits": [hit.get("notes", "条件与实际效度分开核对")],
    }


def learning_outline(chart_compute: dict, *, limit: int = 12) -> dict:
    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("learning_limit_invalid")
    documents, aliases = verified_input(chart_compute)
    try:
        cards = _primary_cards(chart_compute, documents, aliases)
        rules = chart_compute["aliases"]["r"]
        cards += [_rule_card(row, resolve_ref(documents, row["ref"])) for row in rules]
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError("learning_input_invalid") from exc
    cards = cards[:limit]
    used = {
        name
        for card in cards
        for key in ("c_aliases", "r_aliases")
        for name in card[key]
    }
    selected = {
        key: [
            deepcopy(row)
            for row in chart_compute["aliases"][key]
            if row["alias"] in used
        ]
        for key in ("c", "r")
    }
    for index, card in enumerate(cards, 1):
        card["point_id"] = f"learning-{index}"
        card["citations"] = "".join(
            "〔" + name + "〕" for name in card["c_aliases"] + card["r_aliases"]
        )
    return {
        "version": VERSION,
        "status": "learning_only" if cards else "insufficient_evidence",
        "scope": deepcopy(chart_compute["scope"]),
        "points": cards,
        "aliases": selected,
        "rule_hits": [
            deepcopy(resolve_ref(documents, row["ref"])) for row in selected["r"]
        ],
        "source_document_ids": list(documents),
        "effects": {
            "model_calls": 0,
            "writes": 0,
            "alias_registry": "reuse_input_projection_no_registration",
        },
        "limits": [
            "复用传入信封本轮别名，不重编号；某c可能覆盖整个主盘，source_ref给出实际读取位置。",
            "hash只核内容，不核来源签名/真实授权；调用方须先验证来源、owner和资料未撤销。",
            "纯规则学习要点，不生成新命理结论、性格标签或现实结果承诺。",
        ],
    }
