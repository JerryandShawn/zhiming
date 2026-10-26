"""Content-bound preview documents and strict, document-relative references."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

from ....domain.json_values import ensure_finite_json


def digest(value: Any) -> str:
    ensure_finite_json(value)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def resolve(payload: Any, path: str) -> Any:
    if path == "":
        return payload
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("preview_ref_invalid_pointer")
    current = payload
    for encoded in path[1:].split("/"):
        if re.search(r"~(?![01])", encoded):
            raise ValueError("preview_ref_invalid_escape")
        key = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", key) or int(key) >= len(current):
                raise ValueError("preview_ref_invalid_index")
            current = current[int(key)]
        elif isinstance(current, dict) and key in current:
            current = current[key]
        else:
            raise ValueError("preview_ref_missing_value")
    return current


def document_id(scope: dict, kind: str, source_sha256: dict, payload: dict) -> str:
    return "doc-" + digest(
        {
            "scope": scope,
            "kind": kind,
            "source_sha256": source_sha256,
            "payload": payload,
        }
    )


def document(scope: dict, kind: str, sources: dict, payload: dict) -> dict:
    return {
        "document_id": document_id(scope, kind, sources, payload),
        "kind": kind,
        "source_sha256": deepcopy(sources),
        "payload": deepcopy(payload),
    }


def reference(doc: dict, path: str) -> dict[str, str]:
    resolve(doc["payload"], path)
    return {"document_id": doc["document_id"], "path": path}


def claim_id(row: dict) -> str:
    fields = ("scope", "ref", "value_sha256", "branch_id", "basis")
    content = {key: row[key] for key in fields}
    for key in ("rule_id", "rules_version"):
        if key in row:
            content[key] = row[key]
    return "demo-claim-" + digest(content)


def alias(
    name: str,
    scope: dict,
    doc: dict,
    path: str,
    branch_id: str,
    basis: str,
    **extra: Any,
) -> dict:
    row = {
        "alias": name,
        "scope": deepcopy(scope),
        "ref": reference(doc, path),
        "value_sha256": digest(resolve(doc["payload"], path)),
        "branch_id": branch_id,
        "basis": basis,
        **extra,
    }
    return dict(row, claim_id=claim_id(row))
