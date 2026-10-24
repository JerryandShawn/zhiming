"""Bind v4 replies to persisted authenticated sources before queuing or claiming."""

from __future__ import annotations

from typing import Any

from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository


def _scheduled_report(repo: PostgresRepository, owner: str, run: dict[str, Any], business_id: str) -> None:
    try:
        manifest = repo.get(owner, "report", business_id)
    except ScopeError:
        raise EvidenceError("定期报告缺少已持久保存的发布记录") from None
    if (
        manifest["status"] != "active"
        or manifest["subject_id"] != run["subject"]
        or manifest.get("run_id") != run["id"]
        or manifest.get("business_id") != business_id
        or manifest.get("guidance") != run["result"]
    ):
        raise EvidenceError("定期报告发布记录与本轮执行不符")


def assert_delivery_origin(
    repo: PostgresRepository, owner: str, run: dict[str, Any], *, business_id: str, channel: str, target: str
) -> None:
    if run.get("runtime") != "v4":
        return
    # application.__init__ imports ConsultationService, which imports the outbox.
    from mingjing_core.application.thread_sources import ingress_sources

    request = run["request"]
    if request.get("mode") == "scheduled_report":
        _scheduled_report(repo, owner, run, business_id)
        return
    if channel != "feishu":
        raise ScopeError("本轮回复只能返回发起它的渠道")
    primary = request.get("source_message_id")
    identifiers = request.get("source_message_ids", [primary])
    if (
        not isinstance(primary, str)
        or not isinstance(identifiers, list)
        or not identifiers
        or identifiers[-1] != primary
    ):
        raise EvidenceError("本轮回复缺少确定的入站来源")
    thread = run.get("thread_id") or request.get("thread_id") or "life:" + run["subject"]
    sources = ingress_sources(repo, owner, run["subject"], thread, identifiers)
    for source in sources:
        if source.get("channel") != channel or source.get("external_id") != target:
            raise ScopeError("本轮回复不能转发到其他渠道或其他用户")
        if source["revision"] != run["state_version"].get("message:" + source["id"]):
            raise EvidenceError("本轮回复的入站来源已改变")
    binding = repo.resolve_channel(channel, target)
    if binding["owner"] != owner or binding["subject"] != run["subject"] or binding.get("binding_kind") != "user":
        raise ScopeError("回复目标缺少当前用户的有效渠道绑定")
