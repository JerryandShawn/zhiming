"""Atomically publish one v4 reply after lease, lineage and exact own-write checks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.envelope import build_envelope
from mingjing_core.agent.options import merge_card_structure
from mingjing_core.agent.review import TrustedReviewReceipt
from mingjing_core.application.agent_case_index_citations import assert_historical_case_index
from mingjing_core.application.agent_commit_versions import (
    assert_no_withdrawal,
    persisted_receipts,
    reconcile_versions,
)
from mingjing_core.application.agent_options import load_options
from mingjing_core.application.agent_options_review import card_veto
from mingjing_core.application.agent_review_proofs import ReviewProofStore
from mingjing_core.application.agent_thread_scope import assert_thread, thread_id
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import Clock, get_clock
from mingjing_core.validation.structural import check_structure


class AgentFinalizer:
    def __init__(self, repo: PostgresRepository, *, clock: Clock | None = None) -> None:
        self.repo, self.memory, self.clock = repo, MemoryService(repo), clock or get_clock()

    def _authority(self, connection: Any, run: Mapping[str, Any]) -> dict[str, Any]:
        row = self.repo._leased(connection, run["owner"], run["id"], run["lease_token"])
        if row["runtime"] != "v4" or row["retry_epoch"] != run["retry_epoch"]:
            raise LeaseConflict("本轮提交身份已失效")
        if row["subject"] != run["subject"] or run.get("owner_user_id", run["owner"]) != run["owner"]:
            raise ScopeError("本轮提交人物或所有者不符")
        if row["cancel_requested_at"] is not None:
            raise LeaseConflict("本轮已请求取消")
        if row["deadline_at"] is not None and row["deadline_at"] <= self.clock.now():
            raise LeaseConflict("本轮已超过执行时限")
        self.repo.assert_scope(run["owner"], row["subject"])
        assert_thread(self.repo, row)
        return self.repo._run(row)

    def _asked(self, connection: Any, run: Mapping[str, Any], asked: dict[str, Any] | None) -> None:
        rows = connection.execute(
            sql.SQL(
                "SELECT output FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s "
                "AND kind='tool' AND name='ask_user' AND status='completed'"
            ).format(self.repo.table("core_run_steps")),
            (run["owner"], run["id"], run["retry_epoch"]),
        ).fetchall()
        actual = [row["output"]["data"]["asked"] for row in rows if (row["output"] or {}).get("ends_turn")]
        if len(actual) > 1 or (actual[0] if actual else None) != asked:
            raise EvidenceError("最终提问与真实步骤不符")

    def _aliases(
        self,
        run: Mapping[str, Any],
        aliases: dict[str, dict[str, Any]],
        keys: tuple[str, ...],
        versions: Mapping[str, int],
    ) -> None:
        used = set(keys)
        for value in aliases.values():
            kind, ident = value.get("kind"), value.get("id")
            if str(kind) + ":" + str(ident) not in used:
                continue
            key = entity_dependency(kind, ident)
            if key not in versions:
                raise EvidenceError("引用未进入本轮依赖集合")
            row = self.repo.get(run["owner"], kind, ident)
            if row["subject_id"] != run["subject"]:
                raise ScopeError("引用不在当前有效人物范围")
            if row["status"] not in {"active", "open", "pending"}:
                assert_historical_case_index(self.repo, run, value, row)
            if self.repo.is_revoked(run["owner"], kind, ident):
                raise EvidenceError("引用已撤销")

    def _source(self, run: Mapping[str, Any], versions: Mapping[str, int]) -> dict[str, Any]:
        source = self.memory.get_source(run["owner"], run["request"]["source_message_id"])
        if (
            source["revision"] != versions.get("message:" + source["id"])
            or source["status"] != "active"
            or source.get("role") != "user"
            or source["subject_id"] != run["subject"]
            or source.get("content") != run["request"].get("message")
            or source.get("policy", {}).get("origin") != "current_user"
            or source.get("policy", {}).get("run_context") is not True
        ):
            raise EvidenceError("当前用户原话已改变或无效")
        for revoked in self.repo.revocations(run["owner"]):
            if (
                revoked["kind"] == "message"
                and revoked["entity_id"] == source["id"]
                or revoked["kind"] == "source_span"
                and revoked["metadata"].get("message_id") == source["id"]
            ):
                raise EvidenceError("当前用户原话已撤销")
        return source

    def finalize(
        self,
        run: Mapping[str, Any],
        *,
        text: str,
        alias_map: dict[str, dict[str, Any]],
        versions: Mapping[str, int],
        snapshot_revision: int,
        asked: dict[str, Any] | None = None,
        usage: Mapping[str, Any] | None = None,
        review: TrustedReviewReceipt | None = None,
    ) -> dict[str, Any]:
        owner = run["owner"]
        with self.repo.transaction(owner) as connection:
            current = self._authority(connection, run)
            if dict(versions) != current["state_version"]:
                raise EvidenceError("最终依赖集合与持久运行不符")
            assert_no_withdrawal(self.repo, current, versions, snapshot_revision)
            effective = reconcile_versions(self.repo, current, versions)
            receipts = tuple(
                {key: value for key, value in item.items() if key != "_operation"}
                for item in persisted_receipts(self.repo, current)
            )
            self._asked(connection, current, asked)
            if asked and asked["question"] not in text:
                text = (text.strip() + "\n\n" + asked["question"]).strip()
            checked = check_structure(text, alias_map, receipts)
            options = self._options(current)
            checked = merge_card_structure(checked, options, alias_map, receipts)
            if review is not None:
                if not isinstance(review, TrustedReviewReceipt):
                    raise EvidenceError("最终评审需要受信持久证明")
                ReviewProofStore(self.repo).verify(review, current, checked.text)
            self._aliases(current, alias_map, checked.cited_keys, effective)
            source = self._source(current, effective)
            message = self._message(current, source, checked, effective)
            envelope = build_envelope(
                current,
                checked,
                message_id=message["id"],
                receipts=receipts,
                asked=asked,
                options=options,
                usage=usage,
                review=review,
            )
            connection.execute(
                sql.SQL(
                    "UPDATE {} SET result=%s,state_version=%s,status='succeeded',checkpoint='{{}}',"
                    "lease_token=NULL,lease_until=NULL,updated_at=now() WHERE owner=%s AND id=%s"
                ).format(self.repo.table("core_runs")),
                (Jsonb(envelope), Jsonb(effective), owner, current["id"]),
            )
            return envelope

    def _options(self, current: dict[str, Any]) -> dict[str, Any] | None:
        policy = current["usage"].get("agent_runtime", {})
        if policy.get("crisis") or policy.get("fallback") == "crisis_template":
            return None
        selected = load_options(self.repo, current)
        if card_veto(self.repo, current, selected):
            return None
        return selected.value if selected else None

    def _message(self, current, source, checked, effective):
        if thread_id(current).startswith("incognito:"):
            return ThreadService(self.repo, clock=self.clock).record_private_reply(
                current["owner"],
                current,
                checked.text,
                source_ids=[key[8:] for key in effective if key.startswith("message:")],
                used_fact_ids=checked.used_fact_ids,
                used_claim_ids=checked.used_claim_ids,
            )
        return self.memory.record_assistant_message(
            current["owner"],
            current["subject"],
            "life:" + current["subject"],
            checked.text,
            run_id=current["id"],
            channel=source["channel"],
            at=self.clock.now(),
            used_fact_ids=checked.used_fact_ids,
            used_claim_ids=checked.used_claim_ids,
            source_ids=[key[8:] for key in effective if key.startswith("message:")],
            case_ids=current["request"].get("case_ids", []),
            conversation_id=current["request"].get("conversation_id", "shared"),
        )
