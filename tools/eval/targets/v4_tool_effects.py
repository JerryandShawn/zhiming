"""Private evaluator projections of actual tool outputs and persisted followups."""

from copy import deepcopy
from typing import Any
from mingjing_core.repositories.postgres import PostgresRepository

from .v4_observations import tool_steps


def tool_effects(repo: PostgresRepository, owner: str, run_id: str) -> dict[str, Any]:
    result = {
        "followups": [],
        "present_options": [],
        "ask_user": [],
        "profile_requests": [],
        "memories": [],
        "tarot": [],
        "chart_claims": [],
        "effects": [],
    }
    for step in tool_steps(repo, owner, run_id):
        output = step.get("output") or {}
        if step["status"] != "completed" or not output.get("ok"):
            continue
        data, receipt = output.get("data") or {}, output.get("receipt") or {}
        if step["name"].startswith("memory_") and receipt:
            result["memories"].append(deepcopy(receipt))
            if receipt.get("write_status"):
                result["effects"].append(
                    step["name"]
                    + ": "
                    + str(receipt.get("id", receipt.get("fact_id", "")))
                    + " → "
                    + receipt["write_status"]
                )
        if step["name"] in {"tarot_start", "tarot_read"} and data.get("draw"):
            draw = data["draw"]
            result["tarot"].append(
                {key: deepcopy(draw[key]) for key in ("id", "question", "spread_id", "status", "cards") if key in draw}
            )
        if step["name"] == "chart_compute":
            result["chart_claims"].extend(deepcopy(data.get("claims", [])))
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
    affected = {ident for receipt in result["memories"] for ident in receipt.get("affected_ids", [])}
    if affected:
        for row in repo.list(owner, "followup", include_deleted=True):
            if row.get("source_fact_id") in affected or affected.intersection(row.get("fact_ids", [])):
                result["effects"].append("followup " + row["id"] + " → " + row["status"])
    return result


def previous_turns(repo: PostgresRepository, owner: str, run_ids: list[str]) -> list[dict[str, Any]]:
    result = []
    for number, ident in enumerate(run_ids, 1):
        run = repo.fetch_run(owner, ident)
        if run["status"] == "succeeded":
            envelope = run["result"]
            result.append(
                {
                    "run_id": ident,
                    "turn": number,
                    "user_gist": run["request"]["message"][:60],
                    "receipts": envelope["receipts"],
                    "tool_effects": tool_effects(repo, owner, ident),
                }
            )
    return result
