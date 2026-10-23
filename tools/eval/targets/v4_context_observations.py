"""Evaluator-only context evidence comes from the actual persisted run snapshot."""

from __future__ import annotations

import re
from typing import Any

from mingjing_core.application.agent_snapshots import STAGE
from mingjing_core.domain.contracts import ScopeError
from mingjing_core.repositories.postgres import PostgresRepository


def context_observations(repo: PostgresRepository, owner: str, run: dict[str, Any]) -> dict[str, Any]:
    empty = {"l4": {"time_filter": None, "text": "", "item_ids": []}}
    if not run:
        return empty
    try:
        record = repo.get(owner, "runtime_step", f"{run['id']}:e{run['retry_epoch']}:{STAGE}")
    except ScopeError:
        return empty
    if record.get("run_id") != run["id"] or record.get("epoch") != run["retry_epoch"]:
        raise ValueError("评测上下文不属于当前运行")
    layers = record["output"]["budget"]["layers"]
    items = [item for layer in layers if layer["name"] == "L4" for item in layer["items"]]
    text = "\n".join(message["content"] for item in items for message in item["messages"])
    match = re.search(r'time_filter="(\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2})"', text)
    return {
        "l4": {
            "time_filter": match.group(1) if match else None,
            "text": text,
            "item_ids": [item["key"] for item in items if item["key"] != "time-filter"],
        }
    }
