"""Explicit runtime installation; owner routing never constructs or falls back to a provider."""

from __future__ import annotations

import re
from typing import Any

from psycopg import sql

from mingjing_core.application.agent_runtime import AgentRuntime, RuntimeRouter
from mingjing_core.application.dispatcher import AgentDispatcher
from mingjing_core.application.dispatcher_inbox import recover_inboxes
from mingjing_core.application.dispatcher_notifications import RunSignals
from mingjing_core.application.run_acceptance import submission_target
from mingjing_core.application.thread_ingress import ThreadIngress
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError


class RuntimeAssembly:
    def __init__(self, repo: Any, legacy: Any, agent: AgentRuntime | None = None) -> None:
        self.repo, self.legacy, self.agent = repo, legacy, agent
        self.signals = RunSignals()
        if agent is not None and (not isinstance(agent, AgentRuntime) or agent.repo is not repo):
            raise EvidenceError("v4 运行依赖必须由当前仓库显式注入")
        self.router = RuntimeRouter(repo, legacy, agent) if agent is not None else None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.legacy, name)

    def require_agent(self) -> AgentRuntime:
        agent = self.agent
        if agent is None or not callable(getattr(agent.meter, "measure", None)):
            raise EvidenceError("v4 尚未配置受信模型与上下文计量，原系统仍可使用")
        if agent.offline:
            if (
                getattr(agent.port, "offline", False) is not True
                or agent.meter.provider != "scripted"
                or agent.meter.live_admissible is not False
            ):
                raise EvidenceError("离线运行仅允许脚本模型和明确的合成计量")
        elif agent.meter.live_admissible is not True:
            raise EvidenceError("v4 真实模型的上下文计量尚未核验")
        if self.repo.max_running is not None and self.repo.max_running < 3:
            raise EvidenceError("v4 调度容量尚未配置，原系统仍可使用")
        return agent

    def dispatcher(self, service: Any) -> AgentDispatcher | None:
        if self.agent is None or self.repo.max_running is not None and self.repo.max_running < 3:
            return None
        try:
            self.require_agent()
        except EvidenceError:
            return None
        return AgentDispatcher(service, signals=self.signals, runtime=self)

    def execute(self, service: Any, owner: str, run_id: str, lease_token: str, emit: Any = None) -> dict:
        run = self.repo.fetch_run(owner, run_id)
        if run["runtime"] == "v3":
            return self.legacy.execute(service, owner, run_id, lease_token, emit)
        self.require_agent()
        if self.router is None:
            raise EvidenceError("v4 尚未安装")
        return self.router.execute(service, owner, run_id, lease_token, emit)

    def purge(self, run_id: str, epoch: int) -> None:
        self.legacy.purge(run_id, epoch)
        if self.agent is not None:
            self.agent.purge(run_id, epoch)


def route_submit(service: Any, values: dict[str, Any]) -> dict[str, Any]:
    owner, subject = values["owner"], values.get("subject", "self")
    service.repo.ensure_owner(owner)
    runtime, existing = submission_target(service.repo, owner, subject, values["request_id"])
    if runtime == "v3":
        from mingjing_core.application.privacy_mode import PrivacyModeService

        if isinstance(values["message"], str) and values["message"].strip():
            PrivacyModeService(service.repo).assert_legacy_safe(
                owner, subject, values["message"], conversation_id=values.get("conversation_id", "shared")
            )
        return service._submit_validated(**values)
    return submit_agent(service, values, existing)


def submit_agent(service: Any, values: dict[str, Any], existing: Any = None) -> dict[str, Any]:
    owner, subject = values["owner"], values.get("subject", "self")
    service.runtime_assembly.require_agent()
    validate_agent_input(values)
    thread, sources = agent_source_route(service, values, existing)
    ingress = ThreadIngress(service)
    common = dict(
        owner=owner,
        subject=subject,
        thread_id=thread,
        request_id=values["request_id"],
        conversation_id=values.get("conversation_id", "shared"),
        case_ids=values.get("case_ids"),
        depth=values.get("depth", "standard"),
    )
    if values.get("draw_id"):
        from mingjing_core.application.tarot_reveal_ingress import TarotRevealIngress

        return TarotRevealIngress(service).submit(
            draw_id=values["draw_id"], message=values["message"], source_ids=sources, **common
        )
    if sources:
        return ingress.queue(source_ids=sources, **common)
    return ingress.submit(message=values["message"], **common)


def validate_agent_input(values: dict[str, Any]) -> None:
    if (
        not isinstance(values.get("request_id"), str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}", values["request_id"]) is None
    ):
        raise EvidenceError("v4 请求标识需要有效的字母数字标识")
    if (
        values.get("mode", "chat") != "chat"
        or values.get("images")
        or values.get("reading_id")
        or values.get("selection")
        or values.get("parent_run")
    ):
        raise EvidenceError("此 v4 入口尚未支持附件或既有牌阵、报告等输入，请保留原记录等待接线")
    if values.get("depth", "standard") not in {"standard", "deep"}:
        raise EvidenceError("v4 目前支持标准或深入模式")


def agent_source_route(service: Any, values: dict[str, Any], existing: Any) -> tuple[str, list[str] | None]:
    owner, subject = values["owner"], values.get("subject", "self")
    identifiers, expected_thread = None, None
    if existing:
        old = existing["request"]
        if (
            existing["subject"] != subject
            or old.get("message") != values["message"]
            or not old.get("source_message_id")
            or values.get("source_message_id") not in (None, old["source_message_id"])
        ):
            raise EvidenceError("原请求已改变、撤销或属于其他线程，不能重建")
        identifiers = old.get("source_message_ids", [old["source_message_id"]])
        expected_thread = existing.get("thread_id") or old.get("thread_id")
        if not isinstance(expected_thread, str):
            raise EvidenceError("原运行缺少固定线程身份")
    elif values.get("source_message_id"):
        identifiers = [values["source_message_id"]]
    if identifiers is None:
        row = ThreadService(service.repo).create(owner, subject=subject, request_id="runtime-life:" + subject)
        return row["id"], None
    if not isinstance(identifiers, list) or not identifiers or any(not isinstance(ident, str) for ident in identifiers):
        raise EvidenceError("原运行的来源身份无效")
    source = service.memory.get_source(owner, identifiers[-1])
    thread = source.get("thread_id")
    if (
        source["subject_id"] != subject
        or source.get("content") != values["message"]
        or not isinstance(thread, str)
        or expected_thread is not None
        and thread != expected_thread
    ):
        raise EvidenceError("当前问题与原人物、线程或授权原话不符")
    ThreadService(service.repo).get(owner, thread, subject=subject)
    return thread, identifiers


def legacy_queue(repo: Any, owner: str | None = None, limit: int = 1) -> list[dict[str, Any]]:
    with repo.transaction(owner) as connection:
        where, args = (" AND owner=%s", [owner]) if owner else ("", [])
        connection.execute(
            sql.SQL(
                "UPDATE {} SET status='queued',lease_token=NULL,lease_until=NULL,updated_at=now() "
                "WHERE runtime='v3' AND status='running' AND lease_until<=now()" + where
            ).format(repo.table("core_runs")),
            args,
        )
        rows = connection.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE runtime='v3' AND status='queued'" + where + " ORDER BY created_at,id LIMIT %s"
            ).format(repo.table("core_runs")),
            [*args, limit],
        ).fetchall()
        result = [repo._run(row) for row in rows]
    recover_inboxes(repo, owner)
    return result


def stop_dispatcher(dispatcher: AgentDispatcher) -> None:
    with dispatcher.guard:
        identifiers = list(dispatcher.active)
    if identifiers:
        with dispatcher.repo.transaction() as connection:
            rows = connection.execute(
                sql.SQL("SELECT owner,id FROM {} WHERE id=ANY(%s) AND runtime='v4' AND status='running'").format(
                    dispatcher.repo.table("core_runs")
                ),
                (identifiers,),
            ).fetchall()
        for row in rows:
            dispatcher.cancellation.request(row["owner"], row["id"])
    dispatcher.close()
