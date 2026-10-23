"""Adopt a newer own Case revision only with its entire atomically recorded chain."""

from typing import Any

from psycopg import sql

from mingjing_core.agent.journal import Journal
from mingjing_core.application.agent_case_completed import load_completed_intent
from mingjing_core.application.agent_case_effect_chain import assert_case_effect_chain, pending_chain_receipt
from mingjing_core.application.agent_case_effect_marker import marker_cases
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict
from mingjing_core.repositories.postgres import fingerprint


def assert_case_receipt_replay(repo: Any, run: dict, receipt: dict, row: dict) -> None:
    with repo.transaction(run["owner"]) as connection:
        current = repo._run(Journal(repo, run["owner"])._leased(connection, run))
        cases = marker_cases(current)
        if (
            cases is None
            or row["id"] not in cases
            or type(receipt.get("revision")) is not int
            or not 0 < receipt["revision"] < row["revision"]
            or receipt.get("kind") != "case"
            or receipt.get("id") != row["id"]
        ):
            raise RevisionConflict("旧事项回执缺少当前完整自写版本链")
        rows = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s ORDER BY seq FOR UPDATE").format(
                repo.table("core_run_steps")
            ),
            (current["owner"], current["id"], current["retry_epoch"]),
        ).fetchall()
        matching = [
            step
            for step in rows
            if step["kind"] == "tool"
            and step["name"] == "case_update"
            and step["status"] == "completed"
            and step["error_code"] is None
            and fingerprint((step["output"] or {}).get("receipt")) == fingerprint(receipt)
        ]
        if len(matching) != 1 or matching[0]["seq"] not in cases[row["id"]]:
            raise EvidenceError("旧事项回执没有唯一真实completed步骤")
        proof = load_completed_intent(repo, current, matching[0]["seq"])
        alias = next(
            (value for value in proof.base.alias_map.values() if value["kind"] == "case" and value["id"] == row["id"]),
            None,
        )
        if alias is None:
            raise EvidenceError("旧事项回执没有初始已选事项身份")
        tail = rows[-1]
        if (tail["kind"], tail["name"], tail["status"]) == ("tool", "case_update", "started"):
            pending_chain_receipt(repo, current, tail["seq"])
        else:
            assert_case_effect_chain(repo, current, alias, row)
