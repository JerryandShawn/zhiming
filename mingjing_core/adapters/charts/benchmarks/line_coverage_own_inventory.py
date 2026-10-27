"""Complete committed P8-history ownership inventory, with no sampling API."""

from __future__ import annotations

import hashlib
import sys
from collections import Counter
from pathlib import Path

from . import line_coverage_own_sources as source
from .line_coverage_manifest import (
    commit_id,
    digest,
    executable_lines,
    git_bytes,
    normalized,
    safe_root,
)

VERSION = "p8-history-own-python-inventory-v2"


def _pinned(root: Path, base_commit: str, commit: str) -> tuple[str, str]:
    base, observed = commit_id(root, base_commit), commit_id(root, commit)
    if base != source.ORIGIN:
        raise ValueError("own_inventory_approved_origin_required")
    if git_bytes(root, "rev-parse", "--show-object-format").strip() != b"sha1":
        raise ValueError("own_inventory_sha1_repository_required")
    cutover = commit_id(root, source.CUTOVER)
    if git_bytes(root, "merge-base", base, observed).strip().decode() != base:
        raise ValueError("own_inventory_observed_commit_not_descendant")
    if git_bytes(root, "merge-base", cutover, observed).strip().decode() != cutover:
        raise ValueError("own_inventory_observed_commit_before_cutover")
    return base, observed


def _file(
    root: Path, path: str, raw: bytes, identity: str, status: str, cut: dict
) -> dict:
    return {
        "path": path,
        "group": source.classify(path),
        "change_since_origin": status,
        "change_since_cutover": cut.get(path),
        "initial_carry_forward_unchanged_since_cutover": path not in cut,
        "git_blob_id": identity,
        "git_raw_sha256": hashlib.sha256(raw).hexdigest(),
        "lf_sha256": source.lf_hash(raw),
        "executable_lines": executable_lines(normalized(raw), str(root / path)),
    }


def _summary(files: list[dict]) -> dict:
    counts = Counter(row["group"] for row in files)
    result = {}
    for group in sorted(counts):
        selected = [row for row in files if row["group"] == group]
        result[group] = {
            "files": len(selected),
            "denominator_lines": sum(len(row["executable_lines"]) for row in selected),
        }
    result["own_scope_total"] = {
        "files": len(files),
        "denominator_lines": sum(len(row["executable_lines"]) for row in files),
    }
    return result


def _inventory(root: Path, base: str, commit: str) -> dict:
    changes = source.changed(root, base, commit)
    cut = source.changed(root, source.CUTOVER, commit)
    identities = source.tree(root, commit)
    raw = source.raw_sources(root, identities)
    files = []
    deleted = [
        {"path": path, "reason": "absent_in_observed_commit"}
        for path in source.deleted_paths(root, base, commit, identities)
    ]
    for path, status in sorted(changes.items()):
        if status == "D":
            continue
        if path not in raw:
            raise ValueError("own_inventory_source_missing_in_observed_tree")
        else:
            files.append(_file(root, path, raw[path], identities[path], status, cut))
    if not files:
        raise ValueError("own_inventory_scope_empty")
    guards = [
        {"path": path, "lf_sha256": source.lf_hash(value)}
        for path, value in sorted(raw.items())
    ]
    return {
        "files": files,
        "deleted_owned_python": deleted,
        "excluded_preexisting_python": [
            {"path": path, "reason": "present_in_origin_and_unchanged"}
            for path in sorted(identities)
            if path.endswith(".py") and path not in changes
        ],
        "static_source_guards": guards,
        "summary": _summary(files),
        "range_python_change_count": len(changes),
        "initial_carry_forward_unchanged_count": sum(
            path not in cut for path in changes
        ),
    }


def build_own_inventory(root: Path, *, base_commit: str, commit: str) -> dict:
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 11):
        raise ValueError("own_inventory_cpython311_required")
    root = safe_root(root)
    base, observed = _pinned(root, base_commit, commit)
    result = {
        "version": VERSION,
        "history_base_commit": base,
        "cutover_reference_commit": source.CUTOVER,
        "commit": observed,
        "inventory_complete_for_p8_history": True,
        "coverage_collected": False,
        "denominator_method": "cpython-3.11-compile-optimize0-recursive-dis-findlinestarts-v1",
        "denominator_python": list(sys.version_info[:3]),
        "selection": "all-current-owned-Python-changed-since-approved-origin-full-file",
        "limits": [
            "Completeness describes this committed P8 ownership range, not execution or all-repository code.",
            "Unimported files remain in the denominator; this module collects no hits or percentages.",
            "Deleted source paths have no current line denominator and remain in the deletion ledger.",
            "No automatic commit upgrade; newly tracked sources require a new explicit inventory.",
        ],
    }
    result.update(_inventory(root, base, observed))
    result["inventory_sha256"] = digest(result)
    return result


def validate_own_inventory(root: Path, inventory: dict) -> None:
    if not isinstance(inventory, dict) or inventory.get("version") != VERSION:
        raise ValueError("own_inventory_shape_invalid")
    if (
        inventory.get("coverage_collected") is not False
        or inventory.get("inventory_complete_for_p8_history") is not True
    ):
        raise ValueError("own_inventory_static_state_invalid")
    files = inventory.get("files")
    if not isinstance(files, list):
        raise ValueError("own_inventory_line_shape_invalid")
    for row in files:
        if not isinstance(row, dict) or not isinstance(
            row.get("executable_lines"), list
        ):
            raise ValueError("own_inventory_line_shape_invalid")
        lines = row["executable_lines"]
        if any(type(line) is not int or line <= 0 for line in lines):
            raise ValueError("own_inventory_line_type_invalid")
        if lines != sorted(set(lines)):
            raise ValueError("own_inventory_line_order_invalid")
    payload = {
        key: value for key, value in inventory.items() if key != "inventory_sha256"
    }
    if inventory.get("inventory_sha256") != digest(payload):
        raise ValueError("own_inventory_integrity_invalid")
    rebuilt = build_own_inventory(
        root,
        base_commit=inventory.get("history_base_commit"),
        commit=inventory.get("commit"),
    )
    if inventory != rebuilt:
        raise ValueError("own_inventory_pinned_source_mismatch")
