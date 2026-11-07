"""Native action driver: real business effects, no declared DB/result/event injection."""

from __future__ import annotations

from typing import Any

from mingjing_core.application.source_withdrawal import SourceWithdrawalService
from tools.eval.targets.base import TurnResult
from tools.eval.targets.v4_privacy_observations import erased, layer_rows


class NativePrivacyDriver:
    def __init__(self, target: Any) -> None:
        self.target = target

    def execute(self, turn: dict[str, Any]) -> TurnResult:
        target = self.target
        action = turn["action"]
        kind = action["type"]
        if kind not in {"fact_revoke", "source_delete"}:
            raise ValueError("Unsupported native privacy action")
        name, field = ("fact", "fact_id") if kind == "fact_revoke" else ("message", "message_id")
        ident = target.bindings[action[field]]
        row = target.repo.get(target.owner, name, ident, include_deleted=True)
        linked_followups = []
        if name == "fact":
            for followup in target.repo.list(target.owner, "followup", include_deleted=True):
                links = set(followup.get("used_fact_ids", [])) | set(followup.get("fact_ids", []))
                if followup.get("source_fact_id") == ident or ident in links:
                    linked_followups.append(followup["id"])
        request = f"eval-native:{target.seed['_scenario_id']}:{turn['_index']}"
        if kind == "source_delete":
            receipt = SourceWithdrawalService(target.service.memory).delete(
                target.owner, row["subject_id"], ident, expected_revision=row["revision"], request_id=request
            )
        else:

            def effect():
                withdrawn = target.service.memory.retire_fact(target.owner, ident, expected_revision=row["revision"])
                return {
                    "write_status": withdrawn["write_status"],
                    "kind": "fact",
                    "fact_id": ident,
                    "revision": withdrawn["revision"],
                    "affected_ids": withdrawn.get("affected_fact_ids", []),
                }

            receipt = target.repo.mutation_request(
                target.owner, "fact_revoke", request, {"fact_id": ident, "expected_revision": row["revision"]}, effect
            )
        if not erased(target.repo, target.owner, name, ident):
            raise ValueError("Native withdrawal did not erase the selected body and persist its tombstone")
        remaining = layer_rows(target.repo, target.owner, target.seeder.privacy_layers)
        semantics = []
        if kind == "source_delete":
            semantics.append(
                {"name": "source.deleted", "source_store": "core_entities + core_revocations", "source_id": ident}
            )
            if not remaining and all(
                erased(target.repo, target.owner, layer["native_kind"], layer["native_id"])
                for layer in target.seeder.privacy_layers
                if "native_kind" in layer and layer["kind"] not in {"embedding", "search_hit"}
            ):
                semantics.append(
                    {"name": "derived.invalidated", "source_store": "actual native body/FTS/vector/run-output reads"}
                )
        target.semantic = semantics
        target.semantic_history.extend(semantics)
        native = target.repo.get(target.owner, name, ident, include_deleted=True)
        effects = [name + " " + ident + " → " + native["status"]]
        for followup_id in linked_followups:
            followup = target.repo.get(target.owner, "followup", followup_id, include_deleted=True)
            state = followup["status"]
            if (
                state == "deleted"
                and target.repo.is_revoked(target.owner, "fact", ident)
                and erased(target.repo, target.owner, "followup", followup_id)
            ):
                state = "cancelled (native_status=deleted)"
            effects.append("followup " + followup_id + " → " + state)
        target.judge_action_history.append(
            {"turn": turn["_index"], "user_gist": turn["user"][:60], "receipts": [receipt], "effects": effects}
        )
        return TurnResult(
            text="来源与相关派生内容已清理。" if kind == "source_delete" else "这条记忆已撤销，相关跟进也已关闭。",
            receipts=[receipt],
            events=[item["name"] for item in semantics],
            model_calls=0,
            metadata={
                "offline": True,
                "physical_model_requests": 0,
                "evaluator_observations": semantics,
                "native_action": kind,
                "tool_effects": {"memories": [receipt], "effects": effects},
            },
        )
