"""Content-bound ephemeral evidence for P8 pure tools, without a ledger write."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

from ...domain.json_values import ensure_finite_json


def content_hash(value: Any) -> str:
    ensure_finite_json(value)
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf8")).hexdigest()


def pointer(value: Any, path: str) -> Any:
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("tool_evidence_pointer_invalid")
    current = value
    for token in path[1:].split("/"):
        if re.search(r"~(?![01])", token):
            raise ValueError("tool_evidence_pointer_escape_invalid")
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list) and re.fullmatch(r"0|[1-9][0-9]*", key):
            if int(key) >= len(current):
                raise ValueError("tool_evidence_pointer_missing")
            current = current[int(key)]
        elif isinstance(current, dict) and key in current:
            current = current[key]
        else:
            raise ValueError("tool_evidence_pointer_missing")
    return current


def _chart_aliases(root: dict, document_id: str) -> tuple[list[dict], dict]:
    paths = sorted(
        {path for hit in root["rule_hits"] for path in hit["evidence_paths"]}
    )
    rows, names = [], {}
    for index, path in enumerate(paths, 1):
        if not path.startswith("/data/"):
            raise ValueError("tool_evidence_data_pointer_required")
        digest = content_hash(pointer(root, path))
        name = f"c{index}"
        rows.append(
            {
                "alias": name,
                "path": path,
                "value_sha256": digest,
                "claim_id": "claim-" + content_hash([document_id, path, digest]),
            }
        )
        names[path] = name
    return rows, names


def _rule_aliases(root: dict, document_id: str, names: dict) -> list[dict]:
    rows = []
    for index, hit in enumerate(root["rule_hits"], 1):
        if hit.get("met") is not True or not all(
            hit.get(key)
            for key in (
                "rule_id",
                "school",
                "source",
                "evidence_paths",
            )
        ):
            raise ValueError("tool_evidence_true_sourced_hit_required")
        path = f"/rule_hits/{index - 1}"
        digest = content_hash(hit)
        rows.append(
            {
                "alias": f"r{index}",
                "path": path,
                "rule_id": hit["rule_id"],
                "value_sha256": digest,
                "claim_id": "claim-" + content_hash([document_id, path, digest]),
                "evidence_aliases": [names[item] for item in hit["evidence_paths"]],
            }
        )
    return rows


def evidence_result(
    version: str,
    data: dict,
    hits: list[dict],
    sources: list,
    scope: dict | None = None,
) -> dict:
    """Return a fresh read-only result; aliases are local to this content scope."""
    root = deepcopy(
        {
            "version": version,
            "scope": scope,
            "data": data,
            "rule_hits": hits,
            "sources": sources,
        }
    )
    document_id = "tool-" + content_hash(root)
    charts, names = _chart_aliases(root, document_id)
    rules = _rule_aliases(root, document_id, names)
    return {
        **root,
        "document_id": document_id,
        "aliases": {"c": charts, "r": rules},
        "effects": {"model_calls": 0, "writes": 0, "alias_registry": "ephemeral_only"},
        "limits": [
            "短别名仅此结果有效，主线接入时须登记到当前上下文，不是持久化依据账本。",
            "传统条件及数值计算不证明现实预测有效；没有确认或写入出生资料。",
        ],
    }
