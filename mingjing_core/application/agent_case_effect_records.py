"""Record before/after and the exact update input in the actual mutation transaction."""

from __future__ import annotations

import json
from typing import Any

from psycopg import sql

from mingjing_core.agent.journal import Journal
from mingjing_core.application.agent_case_effect_marker import SCHEMA, STAGE, mark_effect, marker_cases
from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import fingerprint

MAX_EFFECT_BYTES = 2_000_000


def effect_id(run_id: str, epoch: int, sequence: int) -> str:
    return f"{run_id}:e{epoch}:case_effect:{sequence}"


def linked_metadata(output: dict[str, Any]) -> tuple[list[str], list[str]]:
    sources = {key[8:] for key in output["versions"] if key.startswith("message:")}
    facts = {key[5:] for key in output["versions"] if key.startswith("fact:")}
    sources.update(output["context_source_ids"])
    for row in (output["before"], output["after"]):
        refs = list(row.get("source_refs", []))
        refs.extend(ref for values in row.get("field_source_refs", {}).values() for ref in values)
        sources.update(ref["message_id"] for ref in refs)
        sources.update(row.get("source_ids", []))
        facts.update(row.get("fact_ids", []))
        facts.update(row.get("used_fact_ids", []))
        if row.get("source_fact_id"):
            facts.add(row["source_fact_id"])
    return sorted(sources), sorted(facts)


def check_size(output: dict[str, Any]) -> None:
    if len(json.dumps(output, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_EFFECT_BYTES:
        raise EvidenceError("事项版本证据超过私有存储上限")


def update_with_evidence(
    service: Any, args: dict[str, Any], ctx: ToolContext, before: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    repo = service.repo
    with repo.transaction(ctx.owner) as connection:
        current = repo._run(
            Journal(repo, ctx.owner)._leased(
                connection,
                {
                    "owner": ctx.owner,
                    "id": ctx.run_id,
                    "subject": ctx.subject,
                    "retry_epoch": ctx.epoch,
                    "lease_token": ctx.lease_token,
                },
            )
        )
        service.authority(connection, ctx)
        marker_cases(current)
        if before["id"] not in current["request"].get("case_ids", []):
            raise ScopeError("事项版本证据不属于本轮已选范围")
        if fingerprint(repo.get(ctx.owner, "case", before["id"])) != fingerprint(before):
            raise EvidenceError("事项版本证据的更新前状态已改变")
        ident = effect_id(ctx.run_id, ctx.epoch, ctx.seq)
        try:
            repo.get(ctx.owner, "runtime_step", ident, include_deleted=True)
        except ScopeError:
            pass
        else:
            raise EvidenceError("事项版本证据不能在效果重放时重建")
        output = {
            "arguments": args,
            "before": before,
            "update_input": dict(before, **payload),
            "versions": dict(current["state_version"]),
            "context_source_ids": list(ctx.source_ids),
        }
        check_size(output)
        after = repo.update(
            ctx.owner,
            "case",
            before["id"],
            payload,
            expected_revision=before["revision"],
            operation_id=ctx.operation_id + ":case",
        )
        receipt = {"write_status": "saved", "id": after["id"], "kind": "case", "revision": after["revision"]}
        output.update(after=after, receipt=receipt)
        _save(repo, connection, current, ctx, output)
        mark_effect(repo, connection, current, before["id"], ctx.seq)
        return receipt


def _save(repo: Any, connection: Any, run: dict[str, Any], ctx: ToolContext, output: dict[str, Any]) -> None:
    operation = ctx.operation_id + ":case"
    value = ["case", output["before"]["id"], ctx.subject, output["before"]["case_id"], output["update_input"]]
    output["operation_fingerprint"] = fingerprint(value)
    effect = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE owner=%s AND operation_id=%s AND kind='case' AND result_id=%s").format(
            repo.table("core_operations")
        ),
        (ctx.owner, operation, output["before"]["id"]),
    ).fetchone()
    if effect is None or effect["fingerprint"] != output["operation_fingerprint"]:
        raise EvidenceError("事项版本证据与真实效果摘要不符")
    output["effect_created_at"] = effect["created_at"].isoformat()
    check_size(output)
    sources, facts = linked_metadata(output)
    data = {
        "schema": SCHEMA,
        "stage": STAGE,
        "run_id": ctx.run_id,
        "epoch": ctx.epoch,
        "seq": ctx.seq,
        "output": output,
        "output_sha256": fingerprint(output),
        "request_sha256": fingerprint(run["request"]),
        "source_ids": sources,
        "fact_ids": facts,
        "case_ids": list(run["request"].get("case_ids", [])),
        "target_case_id": output["before"]["id"],
    }
    ident = effect_id(ctx.run_id, ctx.epoch, ctx.seq)
    repo.put(
        ctx.owner,
        "runtime_step",
        ident,
        data,
        subject=ctx.subject,
        expected_revision=0,
        operation_id="agent-case-effect:" + ident,
    )
