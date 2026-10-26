"""Evaluator-only context evidence comes from the actual persisted run snapshot."""

from __future__ import annotations

import json
import re
from typing import Any

from mingjing_core.application.agent_snapshots import STAGE
from mingjing_core.domain.contracts import ScopeError
from mingjing_core.repositories.postgres import PostgresRepository


def context_observations(repo: PostgresRepository, owner: str, run: dict[str, Any]) -> dict[str, Any]:
    empty = {
        "injected_facts": [],
        "l4": {"time_filter": None, "text": "", "item_ids": []},
        "l2": {"text": "", "item_ids": []},
        "l5": {"text": "", "item_ids": []},
    }
    if not run:
        return empty
    try:
        record = repo.get(
            owner,
            "runtime_step",
            f"{run['id']}:e{run['retry_epoch']}:{STAGE}",
            include_deleted=True,
        )
    except ScopeError:
        return empty
    if record["status"] == "deleted":
        return empty
    if record.get("run_id") != run["id"] or record.get("epoch") != run["retry_epoch"]:
        raise ValueError("评测上下文不属于当前运行")
    layers = record["output"]["budget"]["layers"]
    items = [item for layer in layers if layer["name"] == "L4" for item in layer["items"]]
    text = "\n".join(message["content"] for item in items for message in item["messages"])
    match = re.search(r'time_filter="(\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2})"', text)
    profile = [item for layer in layers if layer["name"] == "L2" for item in layer["items"]]
    history = [item for layer in layers if layer["name"] == "L5" for item in layer["items"]]
    injected = []
    for layer in layers:
        if layer["name"] not in {"L2", "L4"}:
            continue
        for item in layer["items"]:
            for message in item["messages"]:
                content = message["content"]
                try:
                    value = json.loads(content[content.index("\n") + 1 : content.rindex("\n")])
                except (ValueError, TypeError):
                    continue
                if isinstance(value, dict) and value.get("kind") in {
                    "fact",
                    "event",
                    "constraint",
                    "preference",
                }:
                    injected.append(
                        {
                            "id": item["key"],
                            "alias": value.get("alias"),
                            "kind": value["kind"],
                            "text": value.get("text", ""),
                        }
                    )
    return {
<<<<<<< HEAD
        "l5": {
            "text": "\n".join(message["content"] for item in history for message in item["messages"]),
            "item_ids": [item["key"] for item in history],
        },
        "l2": {
            "text": "\n".join(message["content"] for item in profile for message in item["messages"]),
            "item_ids": [item["key"] for item in profile],
        },
=======
        "now": "\n".join(
            message["content"]
            for layer in layers
            if layer["name"] == "L1"
            for item in layer["items"]
            for message in item["messages"]
        ),
>>>>>>> 416605312775597c2ba86607821aca7cc08f2053
        "injected_facts": injected,
        "l4": {
            "time_filter": match.group(1) if match else None,
            "text": text,
            "item_ids": [item["key"] for item in items if item["key"] != "time-filter"],
        },
    }
