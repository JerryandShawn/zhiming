"""Expose case titles/statuses only after the existing exact P3 case proofs."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from psycopg import sql
from pydantic import ValidationError

from mingjing_core.application.agent_case_index_lineage import case_index_lineage
from mingjing_core.application.agent_case_write_citations import (
    assert_case_status_citation,
)
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint


def case_projection(
    repo: PostgresRepository,
    run: dict[str, Any],
    alias: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    if alias.get("basis") != "case_index" and row["id"] not in run["request"].get("case_ids", []):
        raise EvidenceError("P6未选事项缺少本轮真实索引证明")
    if row["status"] not in {"active", "open", "pending"}:
        assert_case_status_citation(repo, run, alias, row)
    elif alias.get("basis") == "case_index":
        _assert_open_index(repo, run, alias, row)
    # Even an open index does not select its case or expose its source closure.
    return {key: row[key] for key in ("id", "title", "status", "revision", "subject_id")} | {"entity_kind": "case"}


def _assert_open_index(
    repo: PostgresRepository,
    run: dict[str, Any],
    alias: dict[str, Any],
    row: dict[str, Any],
) -> None:
    seq = alias.get("model_tool_seq")
    if type(seq) is not int or seq < 1:
        raise EvidenceError("P6事项索引缺少真实工具步骤")
    with repo.transaction(run["owner"]) as connection:
        step = connection.execute(
            sql.SQL(
                "SELECT output FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND seq=%s "
                "AND kind='tool' AND name='case_list' AND status='completed' "
                "AND error_code IS NULL AND finished_at IS NOT NULL"
            ).format(repo.table("core_run_steps")),
            (run["owner"], run["id"], run["retry_epoch"], seq),
        ).fetchone()
        if step is None:
            raise EvidenceError("P6事项索引缺少已完成步骤证明")
        try:
            result = ToolResult.model_validate(step["output"])
        except ValidationError:
            raise EvidenceError("P6事项索引步骤结构无效") from None
        records = case_index_lineage(SimpleNamespace(repo=repo), run, result)
        expected = next((value for value in records if value["id"] == row["id"]), None)
        if expected is not None:
            expected = dict(expected, model_tool_seq=seq)
        if expected is None or fingerprint(alias) != fingerprint(expected):
            raise EvidenceError("P6事项索引不符合本轮真实只读证明")
