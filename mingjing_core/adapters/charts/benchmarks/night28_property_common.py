"""Evidence integrity properties; canonical hashes are software consistency only."""

from __future__ import annotations

from ..tool_evidence import content_hash, pointer


def alias_checks(result: dict) -> bool:
    root = {
        key: result[key] for key in ("version", "scope", "data", "rule_hits", "sources")
    }
    if result["document_id"] != "tool-" + content_hash(root):
        return False
    names = {row["alias"] for row in result["aliases"]["c"]}
    for kind in ("c", "r"):
        for alias in result["aliases"][kind]:
            if content_hash(pointer(result, alias["path"])) != alias["value_sha256"]:
                return False
            if kind == "r" and not set(alias["evidence_aliases"]) <= names:
                return False
    return result["effects"]["model_calls"] == result["effects"]["writes"] == 0
