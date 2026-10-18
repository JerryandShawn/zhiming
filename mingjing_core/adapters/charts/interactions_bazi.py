"""Versioned U2 structure graph; never changes the legacy chart calculation."""

from __future__ import annotations

import hashlib
import json
from itertools import combinations
from pathlib import Path
from typing import Any

from ...calculations.bazi.elements import (
    BRANCHES,
    HIDDEN,
    STEMS,
    element,
    ten_god,
    validate_pillars,
)
from .rules.interaction_metadata import enrich_relations
from .rules.registry import interaction_policy

RULES = Path(__file__).resolve().parents[2] / "knowledge" / "p8_interactions.json"
LAYERS = ("decadal", "yearly", "monthly", "daily")
CONTROLS = dict(zip("木火土金水", "土金水木火", strict=True))


def _rule_table() -> dict[str, Any]:
    return json.loads(RULES.read_text(encoding="utf-8"))


def _node(
    ident: str, value: str, master: str, hidden: dict[str, str]
) -> dict[str, Any]:
    if (
        not isinstance(value, str)
        or len(value) != 2
        or value[0] not in STEMS
        or value[1] not in BRANCHES
    ):
        raise ValueError("交互柱干支无效")
    if STEMS.index(value[0]) % 2 != BRANCHES.index(value[1]) % 2:
        raise ValueError("交互柱干支阴阳配对无效")
    return {
        "id": ident,
        "ganzhi": value,
        "stem": value[0],
        "branch": value[1],
        "stem_ten_god": ten_god(master, value[0]),
        "hidden_ten_gods": [
            {"stem": stem, "ten_god": ten_god(master, stem)}
            for stem in hidden[value[1]]
        ],
    }


def _relation(
    kind: str, nodes: list[dict[str, Any]], required: str, **extra: Any
) -> dict[str, Any]:
    members = [
        {key: node[key] for key in ("id", "ganzhi", "branch", "stem")} for node in nodes
    ]
    canonical = json.dumps(
        [kind, required, members, extra], ensure_ascii=False, sort_keys=True
    ).encode()
    return {
        "id": "u2-" + hashlib.sha256(canonical).hexdigest()[:24],
        "kind": kind,
        "members": members,
        "transformation_established": False,
        **extra,
    }


def _pairs(nodes: list[dict[str, Any]], rules: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for left, right in combinations(nodes, 2):
        if all(row["id"].startswith("natal.") for row in (left, right)):
            continue
        for kind, pairs in rules["pair_relations"].items():
            key = "stem" if kind == "天干五合" else "branch"
            actual = frozenset((left[key], right[key]))
            for pair in pairs:
                if actual == frozenset(pair):
                    rows.append(
                        _relation(
                            kind,
                            [left, right],
                            pair,
                            required_members=list(pair),
                            complete=True,
                        )
                    )
        for source, target in ((left, right), (right, left)):
            if CONTROLS[element(source["stem"])] == element(target["stem"]):
                rows.append(
                    _relation(
                        "天干相克",
                        [source, target],
                        "",
                        source=source["id"],
                        target=target["id"],
                    )
                )
        if (
            left["branch"] == right["branch"]
            and left["branch"] in rules["self_punishment"]
        ):
            rows.append(_relation("自刑", [left, right], left["branch"], complete=True))
    return rows


def _groups(nodes: list[dict[str, Any]], rules: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for kind, groups in rules["group_relations"].items():
        for group in groups:
            members = [node for node in nodes if node["branch"] in group]
            present = {node["branch"] for node in members}
            if len(present) < 2 or not any(
                node["id"].startswith("target.") for node in members
            ):
                continue
            missing = [branch for branch in group if branch not in present]
            row = _relation(
                kind,
                members,
                group,
                required_members=list(group),
                present_branches=[branch for branch in group if branch in present],
                missing_branches=missing,
                complete=not missing,
                status="complete_members" if not missing else "incomplete_members",
            )
            if kind == "三刑":
                row["directed_pairs"] = [
                    {"source": left["id"], "target": right["id"]}
                    for left in members
                    for right in members
                    if left["id"] != right["id"]
                    and left["branch"] + right["branch"]
                    in rules["punishment_directions"]
                ]
            rows.append(row)
    return rows


def bazi_interactions(
    natal: dict[str, str],
    layers: dict[str, str],
    *,
    hidden_stems: dict[str, str] | None = None,
    school: str = "子平",
) -> dict[str, Any]:
    """Link actual natal and target pillars; callers select calendar layers first."""
    validate_pillars(natal)
    if not layers or not set(layers) <= set(LAYERS):
        raise ValueError("需要明确的大运/流年/流月/流日柱")
    hidden = dict(HIDDEN if hidden_stems is None else hidden_stems)
    if set(hidden) != set(BRANCHES) or any(
        not isinstance(value, str)
        or not value
        or any(stem not in STEMS for stem in value)
        for value in hidden.values()
    ):
        raise ValueError("需要完整有效的具名藏干表")
    master = natal["day"][0]
    nodes = [
        _node("natal." + name, natal[name], master, hidden)
        for name in ("year", "month", "day", "hour")
    ]
    nodes += [
        _node("target." + name, layers[name], master, hidden)
        for name in LAYERS
        if name in layers
    ]
    rules = _rule_table()
    policy = interaction_policy()
    relationships = enrich_relations(
        _pairs(nodes, rules) + _groups(nodes, rules), nodes, policy, school
    )
    return {
        "version": rules["version"],
        "method": "p8-layered-structural-graph-v1",
        "school": rules["school"],
        "ordering_school": school,
        "annotation_version": "p8-u12-interaction-labels-v1",
        "annotation_status": policy["status"],
        "day_master": master,
        "nodes": nodes,
        "relations": relationships,
        "source_refs": rules["sources"],
        "limits": rules["limits"],
        "hidden_stems": hidden,
        "natal_only_relations_included": False,
    }
