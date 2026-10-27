"""Compare only explicit U12 condition claims, never their alleged effectiveness."""

from __future__ import annotations

from copy import deepcopy

from .consistency_eval import deferred
from .consistency_facts import covering_alias
from .consistency_u12_input import SHORT_NAMES
from .learning_input import resolve_ref


def _select(key: str, facts: list[dict]) -> list[dict]:
    key = SHORT_NAMES.get(key, key)
    matched = [row for row in facts if row.get("key") == key or row.get("name") == key]
    ids = {row["key"] for row in matched}
    return [row for row in facts if row.get("key") in ids]


def _references(fact: dict, documents: dict) -> list[dict]:
    refs = [
        {
            "document_id": fact["ref"]["document_id"],
            "path": fact["root_ref"]["path"] + path.removeprefix("/data"),
        }
        for path in fact["assessment"]["evidence_paths"]
    ]
    for ref in refs:
        resolve_ref(documents, ref)
    return refs


def _native_rule(name: str, fact: dict, aliases: dict) -> bool:
    row = aliases[name]
    return (
        name.startswith("r")
        and fact["value"] is True
        and row.get("rule_id") == fact["key"]
        and row.get("rules_version") == fact["rules_version"]
        and row["ref"]["document_id"] == fact["ref"]["document_id"]
        and row["ref"]["path"].startswith(fact["root_ref"]["path"] + "/p8/rule_hits/")
    )


def _citation(name: str, selected: list[dict], aliases: dict, refs: list[dict]) -> bool:
    if name.startswith("r"):
        return any(_native_rule(name, fact, aliases) for fact in selected)
    ref = aliases[name]["ref"]
    targets = [row["ref"] for row in selected] + refs
    return any(
        ref["document_id"] == target["document_id"]
        and (
            ref["path"] == target["path"]
            or target["path"].startswith(ref["path"] + "/")
        )
        for target in targets
    )


def _review(reason: str, *, outcome: str = "needs_review") -> dict:
    return deferred(reason, outcome=outcome, field="u12_rule")


def _proof(selected: list[dict], aliases: dict) -> tuple[list[str], list[str]]:
    c_names = [covering_alias(aliases, row["ref"]) for row in selected]
    if any(name is None for name in c_names):
        return [], []
    r_names = [
        name
        for name in aliases
        if any(_native_rule(name, fact, aliases) for fact in selected)
    ]
    for name in r_names:
        c_names.extend(aliases[name]["evidence_aliases"])
    return list(dict.fromkeys(c_names)), list(dict.fromkeys(r_names))


def _checked(
    query: dict,
    selected: list[dict],
    c_names: list[str],
    r_names: list[str],
    refs: list[dict],
) -> dict:
    matched = selected[0]["value"] is query["value"]
    return {
        "field": "u12_rule",
        "outcome": "matched" if matched else "contradiction",
        "reason_code": "value_matches" if matched else "value_differs",
        "assertion": {
            "field": "u12_rule",
            "key": selected[0]["key"],
            "value": query["value"],
        },
        "expected_values": [row["value"] for row in selected],
        "source_refs": [
            {
                "document_id": row["ref"]["document_id"],
                "path": row["ref"]["path"] + "/met",
            }
            for row in selected
        ],
        "input_c_aliases": c_names,
        "input_r_aliases": r_names,
        "input_citations": "".join("〔" + name + "〕" for name in c_names + r_names),
        "fact_sources": [
            {
                "school": row["assessment"].get("school") or "school_unavailable",
                "source": deepcopy(row["assessment"].get("source"))
                or {"status": "source_unavailable"},
            }
            for row in selected
        ],
        "assessments": [
            {
                "ref": deepcopy(row["ref"]),
                "rule_id": row["key"],
                "name": row["name"],
                "rules_version": row["rules_version"],
                "met": row["value"],
                "condition_ref": row["assessment"]["condition_ref"],
                "condition_scope": row["assessment"]["details"].get(
                    "scope", "scope_unavailable"
                ),
                "notes": row["assessment"].get("notes", ""),
                "meaning": "只核本条计算条件，不授权已成格、完整夺食或制杀有效",
            }
            for row in selected
        ],
        "evidence_refs": deepcopy(refs),
    }


def evaluate_u12(
    query: dict, facts: list[dict], aliases: dict, cited: list[str], documents: dict
) -> dict:
    if "reason" in query:
        return _review(query["reason"])
    if any(name not in aliases for name in cited):
        return _review("citation_missing")
    if any(row.get("key") is None for row in facts):
        return _review("u12_assessment_incomplete")
    selected = _select(query["key"], facts)
    if not selected:
        missing = any(row.get("key") is None for row in facts)
        return _review(
            "u12_assessment_incomplete" if missing else "u12_rule_unknown",
            outcome="needs_review" if missing else "not_checked",
        )
    invalid = next(
        (row["invalid_reason"] for row in selected if row["invalid_reason"]), None
    )
    if invalid:
        return _review(invalid)
    if (
        len({row["key"] for row in selected}) != 1
        or len({row["value"] for row in selected}) != 1
    ):
        return _review("multiple_methods_or_branches")
    try:
        refs = [ref for row in selected for ref in _references(row, documents)]
    except (ValueError, KeyError, IndexError, TypeError):
        return _review("u12_evidence_paths_invalid")
    if any(not _citation(name, selected, aliases, refs) for name in cited):
        return _review("citation_not_supporting_field")
    c_names, r_names = _proof(selected, aliases)
    if not c_names:
        return _review("field_evidence_missing", outcome="not_checked")
    return _checked(query, selected, c_names, r_names, refs)
