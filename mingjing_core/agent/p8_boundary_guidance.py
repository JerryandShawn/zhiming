"""Render boundary wording only through the current attested reference registry."""

from __future__ import annotations

from typing import Any

from mingjing_core.skills.boundary_messages import PILLARS, render_boundary


def boundary_guidance(data: dict[str, Any], aliases: dict[str, dict]) -> list[dict]:
    if data.get("adapter_mode") != "p8_v1_1" or data.get("tool_name"):
        return []
    documents = {row["document_id"]: row["payload"] for row in data.get("documents", [])}
    indexed = {}
    for view in data.get("reference_views", []):
        matches = [
            name
            for name, row in aliases.items()
            if row.get("native_id") == view["native_id"]
            and row.get("kind") == ("interpretive_claim" if view["kind"] == "rule" else "artifact")
        ]
        if len(matches) == 1:
            indexed[(view["document_id"], view["pointer"])] = (matches[0], view)
    result = []
    for (document_id, path), (alias, view) in indexed.items():
        if view["kind"] != "rule" or not path.startswith("/boundary_alerts/"):
            continue
        needed = [(document_id, pointer) for pointer in view["evidence_pointers"]]
        if document_id not in documents or any(key not in indexed for key in needed):
            continue
        evidence = [{"alias": indexed[key][0], "path": key[1]} for key in needed]
        rule = {"alias": alias, "path": path, "evidence_aliases": [row["alias"] for row in evidence]}
        full = render_boundary(documents[document_id], rule, evidence, used_pillars=set(PILLARS))
        if full is not None:
            brief = render_boundary(documents[document_id], rule, evidence, used_pillars=set(PILLARS), brief=True)
            result.append(dict(full, brief_text=brief["text"], use_only_if_answer_uses=full["affected_pillars"]))
    return result
