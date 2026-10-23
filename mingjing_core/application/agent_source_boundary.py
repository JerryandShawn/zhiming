"""Only a current authoritative lease may assemble a queued turn's older boundary."""

from typing import Any

from mingjing_core.application.agent_thread_scope import assert_thread
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.timekit.clock import get_clock


def authorize_boundary(repo: Any, owner: str, subject: str, source: dict, supplied: dict) -> dict:
    with repo.transaction(owner) as connection:
        row = repo._run(repo._leased(connection, owner, supplied["id"], supplied["lease_token"]))
        if (
            row["runtime"] != "v4"
            or row["retry_epoch"] != supplied["retry_epoch"]
            or row["subject"] != subject
            or row["cancel_requested_at"]
            or row["request"].get("source_message_id") != source["id"]
            or row["request"].get("message") != source.get("content")
            or source.get("thread_id") != assert_thread(repo, row)
            or row["deadline_at"] is not None
            and row["deadline_at"] <= get_clock().now()
        ):
            raise EvidenceError("上下文旧边界缺少本轮受信租约")
        return row
