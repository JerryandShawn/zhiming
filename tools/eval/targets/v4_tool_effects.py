"""Private evaluator projections of actual tool outputs and persisted followups."""

from copy import deepcopy
from typing import Any
from mingjing_core.repositories.postgres import PostgresRepository

from .v4_observations import tool_steps


def tool_effects(repo: PostgresRepository, owner: str, run_id: str) -> dict[str, Any]:
    result = {"followups": [], "present_options": [], "ask_user": [], "profile_requests": []}
    for step in tool_steps(repo, owner, run_id):
        output = step.get("output") or {}
        if step["status"] != "completed" or not output.get("ok"):
            continue
        data, receipt = output.get("data") or {}, output.get("receipt") or {}
        if step["name"] == "schedule_followup" and receipt.get("id"):
            row = repo.get(owner, "followup", receipt["id"], include_deleted=True)
            result["followups"].append(
                {k: deepcopy(row.get(k)) for k in ("id", "status", "event_at", "due_at", "source_ids")}
            )
        elif step["name"] == "present_options":
            result["present_options"].append(deepcopy(data))
        elif step["name"] == "ask_user":
            result["ask_user"].append(deepcopy(data))
        elif step["name"] == "profile_update_request" and receipt.get("id"):
            row = repo.get(owner, "proposal", receipt["id"], include_deleted=True)
            result["profile_requests"].append({k: deepcopy(row.get(k)) for k in ("id", "status", "kind", "fields")})
    return result


def previous_turns(repo: PostgresRepository, owner: str, run_ids: list[str]) -> list[dict[str, Any]]:
    result = []
    for ident in run_ids:
        run = repo.fetch_run(owner, ident)
        if run["status"] == "succeeded":
            envelope = run["result"]
            result.append(
                {
                    "run_id": ident,
                    "receipts": envelope["receipts"],
                    "tool_effects": tool_effects(repo, owner, ident),
                }
            )
    return result
