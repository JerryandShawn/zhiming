"""Trusted owner settings select explicit injected runtimes; there is no provider fallback."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.dispatcher_claims import DispatcherClaims
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository

from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer


class LegacyRuntime:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.checkpointer = object()

    def execute(self, service: Any, owner: str, ident: str, token: str, emit: Any = None) -> dict:
        self.calls.append(ident)
        return {"schema_version": "core3.0", "answer": "合成旧委托", "validation": {"status": "validated"}}

    def purge(self, ident: str, epoch: int) -> None:
        return


@pytest.fixture(name="assembly_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    original = httpx.Client.send

    def reject(self: httpx.Client, request: Any, *args: Any, **kwargs: Any) -> Any:
        if request.url.host == "testserver" and type(self._transport).__module__ == "starlette.testclient":
            return original(self, request, *args, **kwargs)
        raise AssertionError("runtime assembly tests forbid external HTTP")

    monkeypatch.setattr(httpx.Client, "send", reject)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)
    for key in ("KIMI_API_KEY", "MOONSHOT_API_KEY", "OPENAI_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    yield p2_repo


def configure(repo: PostgresRepository, runtime: str = "v4") -> None:
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET settings=settings||%s WHERE id='alice'").format(repo.table("core_owners")),
            (Jsonb({"runtime": runtime}),),
        )


def service(repo: PostgresRepository, port: ScriptedPort | None = None, **options: Any) -> ConsultationService:
    agent = AgentRuntime(repo, port, SyntheticMeter(), offline=True, **options) if port is not None else None
    return ConsultationService(
        repo, model=SimpleNamespace(model="synthetic"), runtime=LegacyRuntime(), agent_runtime=agent
    )


def test_default_v3_keeps_legacy_runtime_and_checkpointer_contract(assembly_repo: PostgresRepository) -> None:
    core = service(assembly_repo, ScriptedPort([]))
    run = core.submit(owner="alice", request_id="legacy", message="合成旧路径")
    assert run["runtime"] == "v3"
    assert core.execute("alice", run["id"])["schema_version"] == "core3.0"
    assert core.runtime.checkpointer is core.runtime_assembly.legacy.checkpointer
    assert len(core.runtime_assembly.legacy.calls) == 1


def test_v4_service_submit_and_execute_use_explicit_agent(assembly_repo: PostgresRepository) -> None:
    configure(assembly_repo)
    port = ScriptedPort([answer("合成新路径")])
    core = service(assembly_repo, port)
    run = core.submit(owner="alice", request_id="agent", message="合成当前问题")
    assert run["runtime"] == "v4" and run["thread_id"] == "life:self"
    assert core.execute("alice", run["id"])["text"] == "合成新路径"
    assert len(port.requests) == 1 and core.runtime_assembly.legacy.calls == []


def test_missing_agent_or_meter_rejects_before_creating_source(assembly_repo: PostgresRepository) -> None:
    configure(assembly_repo)
    core = service(assembly_repo)
    with pytest.raises(EvidenceError, match="计量"):
        core.submit(owner="alice", request_id="missing", message="不应写入的合成问题")
    assert assembly_repo.list("alice", "message") == [] and core.runtime_assembly.legacy.calls == []
    agent = AgentRuntime(assembly_repo, ScriptedPort([]), None, offline=True)
    core = ConsultationService(assembly_repo, model=object(), runtime=LegacyRuntime(), agent_runtime=agent)
    with pytest.raises(EvidenceError, match="计量"):
        core.submit(owner="alice", request_id="missing-meter", message="合成问题")


@pytest.mark.parametrize(
    "options",
    [
        {"images": ["synthetic-upload"]},
        {"draw_id": "synthetic-draw"},
        {"reading_id": "synthetic-reading"},
        {"mode": "report"},
        {"selection": {"chart": True}},
        {"parent_run": "old"},
    ],
)
def test_uncovered_v4_inputs_are_refused_without_legacy_fallback(
    assembly_repo: PostgresRepository, options: dict
) -> None:
    configure(assembly_repo)
    core = service(assembly_repo, ScriptedPort([]))
    with pytest.raises(EvidenceError, match="尚未支持"):
        core.submit(owner="alice", request_id="unsupported", message="合成问题", **options)
    assert assembly_repo.list("alice", "message") == [] and core.runtime_assembly.legacy.calls == []


def test_v3_pinned_run_survives_owner_setting_change(assembly_repo: PostgresRepository) -> None:
    core = service(assembly_repo, ScriptedPort([]))
    old = core.submit(owner="alice", request_id="pinned", message="合成旧问题")
    configure(assembly_repo)
    assert core.submit(owner="alice", request_id="pinned", message="合成旧问题")["id"] == old["id"]
    assert core.execute("alice", old["id"])["schema_version"] == "core3.0"


def test_v4_operation_replay_retains_pinned_runtime_after_setting_change(assembly_repo: PostgresRepository) -> None:
    configure(assembly_repo)
    core = service(assembly_repo, ScriptedPort([]))
    old = core.submit(owner="alice", request_id="pinned-v4", message="合成新问题")
    configure(assembly_repo, "v3")
    same = core.submit(owner="alice", request_id="pinned-v4", message="合成新问题")
    assert same["id"] == old["id"] and same["runtime"] == "v4"
    assert len(assembly_repo.list("alice", "message")) == 1


def test_explicit_legacy_capacity_one_does_not_disable_v3(assembly_repo: PostgresRepository) -> None:
    assembly_repo.max_running = 1
    core = service(assembly_repo, ScriptedPort([]))
    assert core.runtime_assembly.dispatcher(core) is None
    old = core.submit(owner="alice", request_id="legacy-capacity", message="合成旧问题")
    assert core.execute("alice", old["id"])["schema_version"] == "core3.0"


def test_worker_recovery_releases_unadopted_web_inbox_after_parent_finishes(assembly_repo: PostgresRepository) -> None:
    configure(assembly_repo)
    core = service(assembly_repo, ScriptedPort([]))
    parent = core.submit(owner="alice", request_id="parent", message="合成主问题")
    active = assembly_repo.claim_run("alice", parent["id"])
    child = core.submit(owner="alice", request_id="supplement", message="合成稍后补充")
    assert child["status"] == "inbox_wait"
    assembly_repo.fail_run("alice", parent["id"], "component-fixture-completed", active["lease_token"])
    DispatcherClaims(assembly_repo).recover()
    assert assembly_repo.fetch_run("alice", child["id"])["status"] == "queued"
