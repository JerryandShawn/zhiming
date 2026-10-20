"""Keep a selected initial case alias only after an exact single status-write proof."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from psycopg import sql

from mingjing_core.agent.journal import Journal
from mingjing_core.application.agent_case_index_citations import assert_historical_case_index
from mingjing_core.application.agent_pending_effects import completed_case_effect
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint


def assert_case_status_citation(
    repo: PostgresRepository, run: Mapping[str, Any], alias: dict[str, Any], row: dict[str, Any]
) -> None:
    if alias.get("basis") == "case_index":
        assert_historical_case_index(repo, run, alias, row)
        return
    if alias.get("kind") != "case" or row["status"] not in {"paused", "closed"}:
        raise ScopeError("引用不在当前有效人物范围")
    with repo.transaction(run["owner"]) as connection:
        current = repo._run(Journal(repo, run["owner"])._leased(connection, run))
        if (
            row["id"] != alias.get("id")
            or row["subject_id"] != current["subject"]
            or row["id"] not in current["request"].get("case_ids", [])
            or type(alias.get("revision")) is not int
            or alias["revision"] + 1 != row["revision"]
            or repo.is_revoked(current["owner"], "case", row["id"])
        ):
            raise ScopeError("事项引用缺少当前已选范围内的单次写入证明")
        steps = connection.execute(
            sql.SQL(
                "SELECT seq,output FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s "
                "AND kind='tool' AND name='case_update' AND status='completed' "
                "AND error_code IS NULL AND finished_at IS NOT NULL ORDER BY seq DESC"
            ).format(repo.table("core_run_steps")),
            (current["owner"], current["id"], current["retry_epoch"]),
        ).fetchall()
        expected = {"write_status": "saved", "kind": "case", "id": row["id"], "revision": row["revision"]}
        candidates = [
            step for step in steps if fingerprint((step["output"] or {}).get("receipt")) == fingerprint(expected)
        ]
        if len(candidates) != 1:
            raise EvidenceError("事项引用缺少唯一已完成的精确写入回执")
        base, args, receipt = completed_case_effect(repo, current, candidates[0]["seq"])
        if (
            not any(fingerprint(value) == fingerprint(alias) for value in base.alias_map.values())
            or args["id"] != row["id"]
            or args["expected_revision"] != alias["revision"]
            or args["changes"].get("status") != row["status"]
            or {key: value for key, value in receipt.items() if key != "_operation"} != expected
        ):
            raise EvidenceError("事项引用与受信初始身份及单次状态写入不符")
