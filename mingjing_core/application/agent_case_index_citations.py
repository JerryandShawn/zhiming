"""Historical case citations require this epoch's exact completed index proof."""

from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

from psycopg import sql
from pydantic import ValidationError

from mingjing_core.application.agent_case_index_lineage import case_index_lineage
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint


def assert_historical_case_index(
    repo: PostgresRepository,
    run: Mapping[str, Any],
    alias: dict[str, Any],
    row: dict[str, Any],
) -> None:
    if (
        alias.get("kind") != "case"
        or row["status"] not in {"done", "archived"}
        or row["subject_id"] != run["subject"]
        or alias.get("basis") != "case_index"
        or alias.get("index_only") is not True
        or alias.get("run_id") != run["id"]
        or type(alias.get("epoch")) is not int
        or alias["epoch"] != run["retry_epoch"]
        or type(alias.get("model_tool_seq")) is not int
        or alias["model_tool_seq"] < 1
    ):
        raise ScopeError("历史事项引用缺少当前只读索引证明")
    with repo.transaction(run["owner"]) as connection:
        step = connection.execute(
            sql.SQL(
                "SELECT seq,output FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND seq=%s "
                "AND kind='tool' AND name='case_list' AND status='completed' AND error_code IS NULL "
                "AND finished_at IS NOT NULL"
            ).format(repo.table("core_run_steps")),
            (run["owner"], run["id"], run["retry_epoch"], alias["model_tool_seq"]),
        ).fetchone()
        if step is None:
            raise EvidenceError("历史事项索引步骤没有完成证明")
        try:
            result = ToolResult.model_validate(step["output"])
        except ValidationError:
            raise EvidenceError("历史事项索引步骤结构无效") from None
        records = case_index_lineage(SimpleNamespace(repo=repo), dict(run), result)
        expected = next((value for value in records if value["id"] == row["id"]), None)
        if expected is not None:
            # Identical later reads must not invalidate the earlier, stable alias.
            expected = dict(expected, model_tool_seq=step["seq"])
        if expected is None or fingerprint(alias) != fingerprint(expected):
            raise EvidenceError("历史事项引用与真实索引证明不符")
