"""Attest one committed case write without manufacturing a Journal acknowledgement."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from psycopg import sql
from pydantic import ValidationError

from mingjing_core.agent.context_types import BudgetResult, ContextBuild, ContextEpoch
from mingjing_core.agent.journal import Journal, input_fingerprint
from mingjing_core.agent.tools.interaction_parameters import CaseUpdate
from mingjing_core.application.agent_current_sources import current_source_ids
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.application.agent_tools_memory import source_ref
from mingjing_core.application.agent_tools_policy import source_policy, source_span
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict
from mingjing_core.models.port import AssistantMessage
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint


def _reject() -> None:
    raise EvidenceError("未确认工具效果缺少本轮精确持久证明")


def _saved(repo: PostgresRepository, run: Mapping[str, Any], ident: str, schema: str) -> dict[str, Any]:
    saved = repo.get(run["owner"], "runtime_step", ident, include_deleted=True)
    if (
        saved["status"] != "active"
        or saved["subject_id"] != run["subject"]
        or saved.get("schema") != schema
        or (saved.get("run_id"), saved.get("epoch")) != (run["id"], run["retry_epoch"])
        or fingerprint(saved.get("output")) != saved.get("output_sha256")
        or repo.is_revoked(run["owner"], "runtime_step", ident)
    ):
        _reject()
    return saved


def _initial(repo: PostgresRepository, run: Mapping[str, Any]) -> ContextBuild:
    from mingjing_core.application.agent_snapshots import _decode

    ident = f"{run['id']}:e{run['retry_epoch']}:agent_initial_context"
    saved = _saved(repo, run, ident, "agent-initial-context-v1")
    if saved.get("stage") != "agent_initial_context" or saved.get("request_sha256") != fingerprint(run["request"]):
        _reject()
    return _decode(ContextBuild, saved["output"])


def _arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    # Use the same parameter normalization as ToolRegistry, including defaults.
    from mingjing_core.agent.toolkit import DEFINITIONS

    definition = next((item for item in DEFINITIONS if item.name == name), None)
    if definition is None:
        _reject()
    return definition.parameters.model_validate(arguments).model_dump()


def _model_request(
    repo: PostgresRepository, run: Mapping[str, Any], model: dict[str, Any]
) -> tuple[BudgetResult, dict[str, int]]:
    from mingjing_core.application.agent_snapshots import _decode

    ident = f"{run['id']}:e{run['retry_epoch']}:agent_model_request:{model['seq']}"
    saved = _saved(repo, run, ident, "agent-model-request-v1")
    output = saved["output"]
    if (
        saved.get("stage") != "agent_model_request"
        or saved.get("seq") != model["seq"]
        or saved.get("input_fp") != model["input_fp"]
        or not isinstance(output, dict)
        or set(output) != {"budget", "choice", "versions", "plan", "role", "name"}
        or output["role"] != "primary"
        or output["name"] != model["name"]
        or output["choice"] not in {"auto", "required"}
    ):
        _reject()
    budget = _decode(BudgetResult, output["budget"])
    versions = _decode(dict[str, int], output["versions"])
    plan = _decode(ContextEpoch, output["plan"])
    if not versions or any(value < 1 for value in versions.values()) or plan.source_versions != versions:
        _reject()
    identity = {
        "messages": [asdict(message) for message in budget.messages],
        "tools": [asdict(tool) for tool in budget.tools],
        "tool_choice": output["choice"],
        "source_versions": versions,
    }
    if model["input_fp"] != input_fingerprint("model", model["name"], identity):
        _reject()
    return budget, versions


def _original_call(
    repo: PostgresRepository, run: Mapping[str, Any], rows: list[dict[str, Any]], base: ContextBuild
) -> tuple[dict[str, Any], dict[str, int]]:
    from mingjing_core.application.agent_snapshots import _decode

    pending = rows[-1]
    index = next((index for index in range(len(rows) - 2, -1, -1) if rows[index]["kind"] == "model"), -1)
    if index < 0:
        _reject()
    model, tools = rows[index], rows[index + 1 :]
    if (
        model["status"] != "completed"
        or model["name"] != ""
        or model["error_code"] is not None
        or model["finished_at"] is None
    ):
        _reject()
    response = _decode(AssistantMessage, (model["output"] or {}).get("assistant"))
    if set(model["output"]) != {"assistant"} or model["usage"] != response.usage:
        _reject()
    budget, versions = _model_request(repo, run, model)
    if "case_update" not in {tool.name for tool in budget.tools} or not 1 <= len(tools) <= len(response.tool_calls):
        _reject()
    if len({call.id for call in response.tool_calls}) != len(response.tool_calls):
        _reject()
    for offset, tool in enumerate(tools):
        call = response.tool_calls[offset]
        args = _arguments(call.name, call.arguments)
        expected = input_fingerprint("tool", call.name, {"arguments": args, "source_versions": base.injected_versions})
        if (
            tool["seq"] != model["seq"] + offset + 1
            or tool["kind"] != "tool"
            or tool["name"] != call.name
            or tool["input_fp"] != expected
            or tool["error_code"] is not None
            or tool is not pending
            and (tool["status"] != "completed" or not isinstance(tool["output"], dict) or tool["finished_at"] is None)
        ):
            _reject()
    return CaseUpdate.model_validate(response.tool_calls[len(tools) - 1].arguments).model_dump(), versions


def _source(
    repo: PostgresRepository, run: Mapping[str, Any], args: dict[str, Any], versions: dict[str, int]
) -> tuple[dict[str, Any], int, int]:
    if args["message_id"] not in current_source_ids(repo, run):
        _reject()
    source = repo.get(run["owner"], "message", args["message_id"])
    source_policy(source, run["subject"], run["thread_id"] or "life:" + run["subject"])
    if versions.get("message:" + source["id"]) != source["revision"] or args["id"] not in source.get("case_ids", []):
        _reject()
    start, end = source_span(source, args["quote"], None, None)
    for revoked in repo.revocations(run["owner"]):
        span = revoked["metadata"]
        if (
            revoked["kind"] == "message"
            and revoked["entity_id"] == source["id"]
            or (
                revoked["kind"] == "source_span"
                and span.get("message_id") == source["id"]
                and max(start, span["start"]) < min(end, span["end"])
            )
        ):
            _reject()
    return source, start, end


def _effect(
    repo: PostgresRepository, run: Mapping[str, Any], args: dict[str, Any], receipt: dict[str, Any]
) -> dict[str, Any]:
    row = repo.get(run["owner"], "case", args["id"], include_deleted=True)
    if (
        row["subject_id"] != run["subject"]
        or args["id"] not in run["request"].get("case_ids", [])
        or row["status"] in {"deleted", "stopped", "superseded"}
        or row["revision"] != args["expected_revision"] + 1
        or repo.is_revoked(run["owner"], "case", args["id"])
        or receipt != {"write_status": "saved", "kind": "case", "id": row["id"], "revision": row["revision"]}
    ):
        raise RevisionConflict("未确认事项效果已被外部修订或撤销")
    changes = {key: value for key, value in args["changes"].items() if value is not None}
    if not changes:
        _reject()
    for field, value in changes.items():
        actual = row.get("state", {}).get("goal") if field == "goal" else row[field]
        if actual != value or field in {"title", "goal"} and value not in args["quote"]:
            _reject()
    return row


def _lineage(row: dict[str, Any], args: dict[str, Any], source: dict[str, Any], start: int, end: int) -> None:
    ref = source_ref(source, start, end)
    if not row.get("source_refs") or row["source_refs"][-1] != ref:
        _reject()
    for field in ("title", "goal"):
        if args["changes"].get(field) is not None:
            offset = source["content"].index(args["changes"][field], start, end)
            expected = [source_ref(source, offset, offset + len(args["changes"][field]))]
            if row.get("field_source_refs", {}).get(field) != expected:
                _reject()


def pending_case_receipts(repo: PostgresRepository, run: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Return only an exact, still-current own effect; never acknowledge a step."""
    with repo.transaction(run["owner"]) as connection:
        rows = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s ORDER BY seq FOR UPDATE").format(
                repo.table("core_run_steps")
            ),
            (run["owner"], run["id"], run["retry_epoch"]),
        ).fetchall()
        if not rows:
            return ()
        step = rows[-1]
        if (step["kind"], step["name"], step["status"]) != ("tool", "case_update", "started") or (
            step["output"] is not None or step["finished_at"] is not None or step["usage"] != {} or step["error_code"]
        ):
            return ()
        operation = f"run:{run['id']}:e{run['retry_epoch']}:s{step['seq']}"
        mutation = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND operation='agent_case_update' AND request_key=%s").format(
                repo.table("core_mutation_requests")
            ),
            (run["owner"], operation),
        ).fetchone()
        if mutation is None:
            return ()
        current = Journal(repo, run["owner"])._leased(connection, run)
        try:
            return (_attest(repo, connection, current, rows, mutation, operation),)
        except (KeyError, TypeError, ValueError, ValidationError):
            raise EvidenceError("未确认事项效果的持久证明结构无效") from None


def _attest(
    repo: PostgresRepository,
    connection: Any,
    run: Mapping[str, Any],
    rows: list[dict[str, Any]],
    mutation: dict[str, Any],
    operation: str,
) -> dict[str, Any]:
    base = _initial(repo, run)
    args, versions = _original_call(repo, run, rows, base)
    key = entity_dependency("case", args["id"])
    if (
        (run["thread_id"] or "life:" + run["subject"]).startswith("incognito:")
        or key not in base.injected_versions
        or versions.get(key) != args["expected_revision"]
        or run["state_version"].get(key) not in {args["expected_revision"], args["expected_revision"] + 1}
        or mutation["fingerprint"] != fingerprint(args)
    ):
        _reject()
    source, start, end = _source(repo, run, args, versions)
    row = _effect(repo, run, args, mutation["receipt"])
    _lineage(row, args, source, start, end)
    effect = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE owner=%s AND operation_id=%s AND kind='case' AND result_id=%s").format(
            repo.table("core_operations")
        ),
        (run["owner"], operation + ":case", args["id"]),
    ).fetchone()
    if (
        effect is None
        or re.fullmatch(r"[0-9a-f]{64}", effect["fingerprint"]) is None
        or effect["created_at"] != mutation["created_at"]
        or effect["created_at"].isoformat() != row["updated_at"]
    ):
        _reject()
    # The operation digest covers an old full payload, which cannot be reconstructed.
    # Exact operation, transaction time, normalized intent and current receipt bind causality.
    return dict(mutation["receipt"], _operation=operation)


def completed_case_effect(
    repo: PostgresRepository, run: Mapping[str, Any], sequence: int
) -> tuple[ContextBuild, dict[str, Any], dict[str, Any]]:
    """Attest an existing acknowledgement; never upgrade a started Journal step."""
    if type(sequence) is not int or sequence < 1:
        _reject()
    with repo.transaction(run["owner"]) as connection:
        current = repo._run(Journal(repo, run["owner"])._leased(connection, run))
        rows = connection.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND seq<=%s ORDER BY seq FOR UPDATE"
            ).format(repo.table("core_run_steps")),
            (current["owner"], current["id"], current["retry_epoch"], sequence),
        ).fetchall()
        if not rows:
            _reject()
        step = rows[-1]
        if (
            step["seq"] != sequence
            or (step["kind"], step["name"], step["status"]) != ("tool", "case_update", "completed")
            or step["error_code"] is not None
            or step["finished_at"] is None
        ):
            _reject()
        operation = f"run:{current['id']}:e{current['retry_epoch']}:s{sequence}"
        mutation = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND operation='agent_case_update' AND request_key=%s").format(
                repo.table("core_mutation_requests")
            ),
            (current["owner"], operation),
        ).fetchone()
        if mutation is None:
            _reject()
        try:
            result = ToolResult.model_validate(step["output"])
            base = _initial(repo, current)
            args, _ = _original_call(repo, current, rows, base)
            receipt = _attest(repo, connection, current, rows, mutation, operation)
            actual = {key: value for key, value in receipt.items() if key != "_operation"}
            if not result.ok or result.ends_turn or fingerprint(result.receipt) != fingerprint(actual):
                _reject()
        except (KeyError, TypeError, ValueError, ValidationError):
            raise EvidenceError("已完成事项写入的持久证明结构无效") from None
        return base, args, receipt
