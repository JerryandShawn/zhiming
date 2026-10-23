"""Read-only receipt aliases for the existing page; frozen core4 stays untouched."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from mingjing_core.application.read_result import read_result

PENDING_MEMORY_NOTICE = "敏感信息需你确认后才会保存；目前未写入长期记忆。"
MEMORY_KINDS = frozenset({"fact", "note", "proposal"})


def legacy_web_result(value: Any) -> dict[str, Any]:
    result = read_result(value)
    if result["schema_version"] != "core4.0":
        return result
    # Other saved effects (cases, reminders or cards) are not long-term memories.
    receipts = [item for item in result["receipts"] if item.get("kind") in MEMORY_KINDS]
    result["memory_receipts"] = deepcopy(receipts)
    if any(
        item.get("kind") == "proposal"
        and item.get("write_status") in {"pending_confirmation", "pending_confirm"}
        and item.get("code") == "sensitive_confirmation"
        for item in receipts
    ):
        # The unchanged page renders saved notices only. Its existing caveat area
        # can show a pending outcome without converting it into a saved receipt.
        result["caveats"] = [PENDING_MEMORY_NOTICE]
    return result


def legacy_web_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(row, meta=legacy_web_result(row["meta"]))
        if row.get("role") == "assistant"
        and isinstance(row.get("meta"), dict)
        and row["meta"].get("schema_version") == "core4.0"
        else row
        for row in rows
    ]
