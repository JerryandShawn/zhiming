"""Explicit evaluator views over persisted rows; never public runtime events."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import sql

from mingjing_core.repositories.postgres import PostgresRepository


def tool_steps(repo: PostgresRepository, owner: str, run_id: str) -> list[dict[str, Any]]:
    with repo.transaction(owner) as connection:
        return connection.execute(
            sql.SQL(
                "SELECT run_id,epoch,seq,name,input_fp,status,output FROM {} "
                "WHERE owner=%s AND run_id=%s AND kind='tool' ORDER BY epoch,seq"
            ).format(repo.table("core_run_steps")),
            (owner, run_id),
        ).fetchall()


def semantic_observations(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for step in steps:
        if step["status"] == "completed" and (step["output"] or {}).get("data", {}).get("code") == "repeated_tool":
            result.append(
                {
                    "name": "tool.repeat_circuit_open",
                    "source_store": "core_run_steps.output.data.code",
                    "run_id": step["run_id"],
                    "epoch": step["epoch"],
                    "seq": step["seq"],
                    "rule": "completed tool output code == repeated_tool; evaluator-only, not events_v1",
                }
            )
    return result


def decision_rows(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for step in steps:
        output = step["output"] or {}
        if step["name"] != "present_options" or step["status"] != "completed" or not output.get("ok"):
            continue
        for index, option in enumerate(output.get("data", {}).get("options", [])):
            result.append(
                {
                    "kind": "decision_option",
                    "id": f"{step['run_id']}:s{step['seq']}:{index}",
                    "status": "active",
                    "data": deepcopy(option),
                    "source_store": "core_run_steps.output.data.options",
                    "source_seq": step["seq"],
                }
            )
    return result


def local_entity(row: dict[str, Any], zone: str) -> dict[str, Any]:
    result = deepcopy(row)
    due = result.get("due_at")
    if due:
        stamp = datetime.fromisoformat(due)
        if stamp.tzinfo is None:
            raise ValueError("Stored schedule timestamp is naive")
        result["due_at"] = stamp.astimezone(ZoneInfo(zone)).isoformat()
    return result


def repeat_count(steps: list[dict[str, Any]]) -> int:
    return max(Counter((step["epoch"], step["input_fp"]) for step in steps).values(), default=0)


def delivery_rows(repo: PostgresRepository, owner: str) -> list[dict[str, Any]]:
    with repo.transaction(owner) as connection:
        rows = connection.execute(
            sql.SQL("SELECT id,run_id,status,business_id,channel,target FROM {} WHERE owner=%s").format(
                repo.table("delivery_outbox")
            ),
            (owner,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "kind": "outbox",
            "status": "queued" if row["status"] == "pending" else row["status"],
            "data": dict(row),
            "source_store": "delivery_outbox",
            "native_status": row["status"],
        }
        for row in rows
    ]
