"""Persistent supplemental input always has a dormant next-turn run until adoption commits."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any

from psycopg import sql

from mingjing_core.application.thread_inbox_proofs import committed_adoption, model_proof
from mingjing_core.application.thread_sources import ingress_sources, source_segments
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.models.port import ChatMessage
from mingjing_core.repositories.dispatch_hooks import notify_run
from mingjing_core.timekit.clock import get_clock


@dataclass(frozen=True)
class InboxClaim:
    inbox_id: str
    token: str = field(repr=False)
    iteration: int
    versions: dict[str, int]
    source_segments: tuple[dict[str, Any], ...]
    user_messages: tuple[ChatMessage, ...] = field(repr=False)


class ThreadInbox:
    def __init__(self, repo: Any) -> None:
        self.repo = repo

    def record(self, fallback: dict[str, Any], *, parent: dict[str, Any] | None) -> dict[str, Any]:
        request, owner = fallback["request"], fallback["owner"]
        return self.repo.put(
            owner,
            "request",
            "thread-inbox:" + fallback["id"],
            dict(
                ingress="thread_inbox",
                thread_id=fallback["thread_id"],
                fallback_run_id=fallback["id"],
                parent_run_id=parent["id"] if parent else None,
                inbox_state="waiting" if parent else "queued",
                source_ids=request["source_message_ids"],
                source_segments=request["source_segments"],
                incognito=request["incognito"],
            ),
            subject=fallback["subject"],
            expected_revision=0,
            operation_id="thread-inbox:" + fallback["id"],
        )

    def _authority(self, connection: Any, run: dict[str, Any]) -> dict[str, Any]:
        current = self.repo._run(self.repo._leased(connection, run["owner"], run["id"], run["lease_token"]))
        if (
            current["runtime"] != "v4"
            or current["retry_epoch"] != run["retry_epoch"]
            or current["subject"] != run["subject"]
            or current["cancel_requested_at"] is not None
        ):
            raise LeaseConflict("补充消息不属于当前受信运行")
        if current["deadline_at"] is not None and current["deadline_at"] <= get_clock().now():
            raise LeaseConflict("补充消息运行已超时")
        ThreadService(self.repo).get(current["owner"], current["thread_id"], subject=current["subject"])
        return current

    def _items(self, connection: Any, owner: str, parent: str | None = None) -> list[dict[str, Any]]:
        clause = sql.SQL(" AND data->>'parent_run_id'=%s") if parent else sql.SQL("")
        parameters = (owner, parent) if parent else (owner,)
        rows = connection.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE owner=%s AND kind='request' AND status='active' "
                "AND data->>'ingress'='thread_inbox' AND data->>'parent_run_id' IS NOT NULL "
                "AND data->>'inbox_state' IN ('waiting','claimed','adopted','next_turn')"
            ).format(self.repo.table("core_entities"))
            + clause
            + sql.SQL(" ORDER BY created_at,id LIMIT 100 FOR UPDATE"),
            parameters,
        ).fetchall()
        return [self.repo._decode(row) for row in rows]

    def claim(self, run: dict[str, Any], *, phase: str, iteration: int) -> tuple[InboxClaim, ...]:
        if phase not in {"before_model", "after_model"} or type(iteration) is not int or iteration < 1:
            raise EvidenceError("补充消息采用阶段或迭代无效")
        if phase == "after_model":
            self.defer(run)
            return ()
        with self.repo.transaction(run["owner"]) as connection:
            current = self._authority(connection, run)
            known = set(current["request"].get("source_message_ids", [current["request"].get("source_message_id")]))
            known.update(self.authorized_source_ids(current))
            claims = []
            for item in self._items(connection, run["owner"], run["id"]):
                sources = set(item["source_ids"])
                if len(known | sources) > 100:
                    if item["inbox_state"] == "waiting":
                        self.repo.update(
                            run["owner"],
                            "request",
                            item["id"],
                            {"inbox_state": "next_turn"},
                            expected_revision=item["revision"],
                        )
                    continue
                claim = self._claim_one(current, item, iteration)
                if claim is not None:
                    known.update(sources)
                    claims.append(claim)
            return tuple(claims)

    def _claim_one(self, run: dict[str, Any], item: dict[str, Any], iteration: int) -> InboxClaim | None:
        if item["subject_id"] != run["subject"] or item["thread_id"] != run["thread_id"]:
            raise ScopeError("补充消息跨越人物或线程")
        lease_hash = hashlib.sha256(run["lease_token"].encode()).hexdigest()
        same = (item.get("claim_epoch"), item.get("claim_iteration"), item.get("claim_lease")) == (
            run["retry_epoch"],
            iteration,
            lease_hash,
        )
        reclaim = item["inbox_state"] == "claimed" and (item.get("claim_epoch"), item.get("claim_iteration")) == (
            run["retry_epoch"],
            iteration,
        )
        if item["inbox_state"] != "waiting" and not reclaim:
            return None
        sources = ingress_sources(self.repo, run["owner"], run["subject"], run["thread_id"], item["source_ids"])
        if source_segments(sources) != item.get("source_segments"):
            raise EvidenceError("补充原话区间与原始来源不符")
        versions = {"message:" + row["id"]: row["revision"] for row in sources}
        if any(versions.get("message:" + row["message_id"]) != row["version"] for row in item["source_segments"]):
            raise EvidenceError("补充消息原话版本已改变")
        token = item["claim_token"] if same else uuid.uuid4().hex
        if not same:
            item = self.repo.update(
                run["owner"],
                "request",
                item["id"],
                dict(
                    inbox_state="claimed",
                    claim_token=token,
                    claim_epoch=run["retry_epoch"],
                    claim_iteration=iteration,
                    claim_lease=lease_hash,
                ),
                expected_revision=item["revision"],
            )
            if reclaim and self._restore_ack(run, item):
                return None
        return InboxClaim(
            item["id"],
            token,
            iteration,
            versions,
            tuple(item["source_segments"]),
            tuple(ChatMessage("user", row["content"]) for row in sources),
        )

    def _restore_ack(self, run: dict[str, Any], item: dict[str, Any]) -> bool:
        with self.repo.transaction(run["owner"]) as connection:
            steps = connection.execute(
                sql.SQL(
                    "SELECT seq FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND kind='model' "
                    "AND status='completed' AND error_code IS NULL ORDER BY seq LIMIT 100"
                ).format(self.repo.table("core_run_steps")),
                (run["owner"], run["id"], run["retry_epoch"]),
            ).fetchall()
        for step in steps:
            try:
                proof = model_proof(self.repo, run, item, step["seq"])
            except (EvidenceError, ScopeError):
                continue
            self.repo.update(
                run["owner"],
                "request",
                item["id"],
                dict(inbox_state="adopted", adoption=proof),
                expected_revision=item["revision"],
            )
            return True
        return False

    def ack(self, run: dict[str, Any], claim: InboxClaim, *, model_seq: int) -> None:
        with self.repo.transaction(run["owner"]) as connection:
            current = self._authority(connection, run)
            item = self.repo.get(run["owner"], "request", claim.inbox_id)
            if (
                item.get("parent_run_id") != run["id"]
                or item.get("thread_id") != current["thread_id"]
                or item.get("claim_token") != claim.token
                or item.get("claim_epoch") != current["retry_epoch"]
                or item.get("claim_lease") != hashlib.sha256(run["lease_token"].encode()).hexdigest()
                or item.get("claim_iteration") != claim.iteration
                or item["subject_id"] != current["subject"]
            ):
                raise ScopeError("补充消息采用凭据与当前运行不符")
            proof = model_proof(self.repo, current, item, model_seq)
            if item["inbox_state"] == "adopted" and item.get("adoption") == proof:
                return
            if item["inbox_state"] != "claimed":
                raise EvidenceError("补充消息没有当前待确认采用记录")
            self.repo.update(
                run["owner"],
                "request",
                item["id"],
                dict(inbox_state="adopted", adoption=proof),
                expected_revision=item["revision"],
            )

    def defer(self, run: dict[str, Any]) -> None:
        with self.repo.transaction(run["owner"]) as connection:
            self._authority(connection, run)
            for item in self._items(connection, run["owner"], run["id"]):
                if item["inbox_state"] == "waiting":
                    self.repo.update(
                        run["owner"],
                        "request",
                        item["id"],
                        {"inbox_state": "next_turn"},
                        expected_revision=item["revision"],
                    )

    def authorized_source_ids(self, run: dict[str, Any]) -> tuple[str, ...]:
        with self.repo.transaction(run["owner"]) as connection:
            current = self._authority(connection, run)
            result = []
            for item in self._items(connection, run["owner"], run["id"]):
                proof = item.get("adoption")
                if item["inbox_state"] != "adopted" or item.get("claim_epoch") != current["retry_epoch"]:
                    continue
                if item["subject_id"] != current["subject"] or item["thread_id"] != current["thread_id"]:
                    raise ScopeError("已采用补充原话不属于当前人物或线程")
                if (
                    not isinstance(proof, dict)
                    or proof.get("epoch") != current["retry_epoch"]
                    or model_proof(self.repo, current, item, proof.get("model_seq")) != proof
                ):
                    raise EvidenceError("已采用补充原话缺少当前模型请求证明")
                result.extend(item["source_ids"])
            return tuple(dict.fromkeys(result))

    def recover(self, owner: str) -> dict[str, int]:
        counts = {"queued": 0, "consumed": 0, "revoked": 0}
        with self.repo.transaction(owner) as connection:
            for item in self._items(connection, owner):
                outcome = self._recover_one(connection, owner, item)
                if outcome:
                    counts[outcome] += 1
        return counts

    def _recover_one(self, connection: Any, owner: str, item: dict[str, Any]) -> str | None:
        parent = self.repo._run(
            connection.execute(
                sql.SQL(
                    "SELECT *,coalesce(lease_until>now(),false) AS live FROM {} WHERE owner=%s AND id=%s FOR UPDATE"
                ).format(self.repo.table("core_runs")),
                (owner, item["parent_run_id"]),
            ).fetchone()
        )
        fallback = self.repo.fetch_run(owner, item["fallback_run_id"])
        parent_thread = parent["thread_id"] or parent["request"].get("thread_id") or "life:" + parent["subject"]
        if (
            parent["subject"] != item["subject_id"]
            or fallback["subject"] != item["subject_id"]
            or parent_thread != item["thread_id"]
            or fallback["thread_id"] != item["thread_id"]
        ):
            raise ScopeError("补充消息恢复跨越人物或线程")
        if parent["status"] == "queued" or parent["status"] == "running" and parent["live"]:
            return None
        if fallback["status"] != "inbox_wait" or fallback["attempts"] or fallback["calls"]:
            raise EvidenceError("补充消息备用轮次已改变")
        try:
            ingress_sources(self.repo, owner, item["subject_id"], item["thread_id"], item["source_ids"])
            outcome = "consumed" if committed_adoption(self.repo, parent, item) else "queued"
        except (ScopeError, EvidenceError):
            outcome = "revoked"
        status = {"consumed": "cancelled", "queued": "queued", "revoked": "revoked"}[outcome]
        connection.execute(
            sql.SQL("UPDATE {} SET status=%s,updated_at=now() WHERE owner=%s AND id=%s").format(
                self.repo.table("core_runs")
            ),
            (status, owner, fallback["id"]),
        )
        self.repo.update(owner, "request", item["id"], {"inbox_state": outcome}, expected_revision=item["revision"])
        if outcome == "queued":
            notify_run(connection, self.repo.schema, fallback["id"])
        return outcome
