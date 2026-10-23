"""Adoption is a completed model request plus a published reply with exact lineage."""

from __future__ import annotations

from typing import Any

from psycopg import sql

from mingjing_core.application.thread_sources import ingress_sources, source_segments
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import fingerprint


def model_proof(repo: Any, run: dict[str, Any], item: dict[str, Any], seq: int) -> dict[str, Any]:
    if type(seq) is not int or seq < 1:
        raise EvidenceError("补充原话采用需要真实模型步骤")
    with repo.transaction(run["owner"]) as connection:
        step = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND seq=%s").format(
                repo.table("core_run_steps")
            ),
            (run["owner"], run["id"], run["retry_epoch"], seq),
        ).fetchone()
    if not step or step["kind"] != "model" or step["status"] != "completed" or step["error_code"]:
        raise EvidenceError("补充原话尚未进入已完成模型步骤")
    ident = f"{run['id']}:e{run['retry_epoch']}:agent_model_request:{seq}"
    snapshot = repo.get(run["owner"], "runtime_step", ident)
    value = snapshot.get("output")
    if (
        snapshot.get("schema") != "agent-model-request-v1"
        or snapshot.get("input_fp") != step["input_fp"]
        or (snapshot.get("run_id"), snapshot.get("epoch"), snapshot.get("seq")) != (run["id"], run["retry_epoch"], seq)
        or fingerprint(value) != snapshot.get("output_sha256")
        or not isinstance(value, dict)
        or value.get("role") != "primary"
    ):
        raise EvidenceError("补充原话模型快照证明无效")
    rows = ingress_sources(repo, run["owner"], run["subject"], item["thread_id"], item["source_ids"])
    if source_segments(rows) != item.get("source_segments"):
        raise EvidenceError("补充原话区间与原始来源不符")
    versions, messages = value.get("versions", {}), value.get("budget", {}).get("messages", [])
    for source in rows:
        expected = next(
            segment["version"] for segment in item["source_segments"] if segment["message_id"] == source["id"]
        )
        if (
            source["revision"] != expected
            or versions.get("message:" + source["id"]) != expected
            or not any(
                message.get("role") == "user" and message.get("content") == source["content"]
                for message in messages
                if isinstance(message, dict)
            )
        ):
            raise EvidenceError("补充原话未逐条进入真实模型请求")
    return {"model_seq": seq, "epoch": run["retry_epoch"], "request_sha256": snapshot["output_sha256"]}


def committed_adoption(repo: Any, parent: dict[str, Any], item: dict[str, Any]) -> bool:
    adoption = item.get("adoption")
    if (
        parent["status"] != "succeeded"
        or not isinstance(adoption, dict)
        or adoption.get("epoch") != parent["retry_epoch"]
        or not isinstance(parent.get("result"), dict)
    ):
        return False
    try:
        if model_proof(repo, parent, item, adoption.get("model_seq")) != adoption:
            return False
        ident = parent["result"].get("message_id")
        if not isinstance(ident, str):
            return False
        reply = repo.get(parent["owner"], "message", ident)
        if (
            reply.get("role") != "assistant"
            or reply.get("run_id") != parent["id"]
            or reply.get("thread_id") != item["thread_id"]
            or reply["subject_id"] != parent["subject"]
            or reply["status"] != "active"
            or not set(item["source_ids"]).issubset(reply.get("source_ids", []))
        ):
            return False
        return all(
            parent["state_version"].get("message:" + segment["message_id"]) == segment["version"]
            for segment in item["source_segments"]
        )
    except (EvidenceError, ScopeError, KeyError, TypeError):
        return False
