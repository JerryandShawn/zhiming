"""Actual old-page sendChat/history DOM, real HTTP and PG; providers are scripts only."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest
from psycopg import sql

from mingjing_core.adapters.web import create_app
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.runtime_settings import RuntimeSettingsService
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_pg_channels import FixtureModel

from .legacy_dom_http_support import local_app
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer, writer


class SavingPort(ScriptedPort):
    def __init__(self, repo: PostgresRepository, *, sensitive: bool = False) -> None:
        super().__init__([])
        self.repo, self.sensitive = repo, sensitive

    def stream(self, messages: Any, **kwargs: Any) -> Any:
        if not self.responses:
            with self.repo.transaction("alice") as connection:
                row = connection.execute(
                    sql.SQL("SELECT * FROM {} WHERE owner=%s AND runtime='v4' AND status='running'").format(
                        self.repo.table("core_runs")
                    ),
                    ("alice",),
                ).fetchone()
            arguments = writer(row)
            if self.sensitive:
                arguments.update(kind="background", sensitivity="health")
            self.responses.extend(
                [
                    answer("", [ToolCall("dom-save", "memory_write", arguments)]),
                    answer("合成待确认回答。" if self.sensitive else "合成新页面兼容回答：已记住〔f1〕。"),
                ]
            )
        yield from super().stream(messages, **kwargs)


def probe(origin: str, *, message: str | None, expected: list[str]) -> dict:
    node = shutil.which("node")
    assert node, "declared frontend test runtime Node.js is required"
    env = {k: v for k, v in os.environ.items() if not re.search(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD)$", k)}
    env.update(TZ="Asia/Tokyo", LANGSMITH_TRACING="false", OTEL_SDK_DISABLED="true")
    result = subprocess.run(
        [node, str(Path(__file__).with_name("legacy_dom_probe.cjs"))],
        input=json.dumps(dict(origin=origin, message=message, expected=expected), ensure_ascii=False),
        encoding="utf-8",
        capture_output=True,
        timeout=30,
        env=env,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    return json.loads(result.stdout)


def exercise_roundtrip(
    p2_repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> dict:
    repo, legacy, port = p2_repo, FixtureModel(), SavingPort(p2_repo)
    monkeypatch.setenv("MINGJING_TOKEN", "synthetic-dom-owner")
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    monkeypatch.setenv("ZHIMING_TOKEN_OWNERS", "{}")
    original = httpx.Client.send

    def loopback_only(client: httpx.Client, request: httpx.Request, **kwargs: Any) -> Any:
        assert request.url.host == "127.0.0.1" and request.url.scheme == "http"
        return original(client, request, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", loopback_only)
    agent = AgentRuntime(repo, port, SyntheticMeter(), offline=True)
    core = ConsultationService(repo, model=legacy, agent_runtime=agent)
    settings = RuntimeSettingsService(repo)
    with local_app(create_app(core)) as origin:
        old = probe(origin, message="本机合成旧路径问题", expected=["先核对现实安排"])
        assert old["post_count"] == 1 and len(legacy.requests) == 2 and port.requests == []
        assert old["receipt_nodes"] == 0
        settings.apply("alice", "v4", expected_runtime="v3", request_id="dom-to-v4")
        new = probe(
            origin,
            message="请记住我喜欢合成蓝杯",
            expected=["合成新页面兼容回答", "已记住"],
        )
        assert new["post_count"] == 1 and new["recovery_count"] == 1
        assert len(repo.list("alice", "fact")) == 1 and len(port.requests) == 2
        settings.apply("alice", "v3", expected_runtime="v4", request_id="dom-back-v3")
        again = probe(origin, message="本机合成回退后的问题", expected=["先核对现实安排"])
        assert again["post_count"] == 1 and len(legacy.requests) == 4 and len(port.requests) == 2
        assert again["receipt_nodes"] == 0
        history = probe(origin, message=None, expected=["合成新页面兼容回答", "先核对现实安排"])
        assert history["assistant_nodes"] == 3 and history["history_count"] == 1
        with repo.transaction("alice") as connection:
            runs = connection.execute(
                sql.SQL("SELECT runtime,result FROM {} WHERE owner=%s ORDER BY created_at").format(
                    repo.table("core_runs")
                ),
                ("alice",),
            ).fetchall()
        assert [row["runtime"] for row in runs] == ["v3", "v4", "v3"]
        assert [row["result"]["schema_version"] for row in runs] == [
            "core3.0",
            "core4.0",
            "core3.0",
        ]
        assert repo.assert_scope("bob")["settings"].get("runtime", "v3") == "v3"
        assert len(runs[1]["result"]["receipts"]) == 1
        return {"current": new, "history": history}


def test_legacy_dom_real_http_v3_v4_v3_and_committed_history(
    p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = exercise_roundtrip(p2_repo, monkeypatch)
    assert observed["history"]["assistant_nodes"] == 3


def test_legacy_dom_displays_actual_core4_memory_receipt(
    p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = exercise_roundtrip(p2_repo, monkeypatch)
    counts = [observed[key]["receipt_nodes"] for key in ("current", "history")]
    assert counts == [1, 1]


def test_legacy_dom_sensitive_proposal_is_pending_and_never_a_saved_notice(
    p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, port = p2_repo, SavingPort(p2_repo, sensitive=True)
    monkeypatch.setenv("MINGJING_TOKEN", "synthetic-dom-owner")
    monkeypatch.setenv("MINGJING_OWNER_ID", "alice")
    monkeypatch.setenv("ZHIMING_TOKEN_OWNERS", "{}")
    original = httpx.Client.send

    def loopback_only(client: httpx.Client, request: httpx.Request, **kwargs: Any) -> Any:
        assert request.url.host == "127.0.0.1" and request.url.scheme == "http"
        return original(client, request, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", loopback_only)
    agent = AgentRuntime(repo, port, SyntheticMeter(), offline=True)
    service = ConsultationService(repo, model=FixtureModel(), agent_runtime=agent)
    RuntimeSettingsService(repo).apply("alice", "v4", expected_runtime="v3", request_id="sensitive-v4")
    expected = ["合成待确认回答", "敏感信息需你确认后才会保存；目前未写入长期记忆。"]
    with local_app(create_app(service)) as origin:
        current = probe(origin, message="我确诊了合成疾病，想谈谈近况", expected=expected)
        history = probe(origin, message=None, expected=expected)
        assert current["post_count"] == 1 and current["recovery_count"] == 1
        assert history["history_count"] == 1 and history["assistant_nodes"] == 1
        assert current["receipt_nodes"] == history["receipt_nodes"] == 0
        assert len(port.requests) == 2 and repo.list("alice", "fact") == []
        proposals = repo.list("alice", "proposal")
        assert len(proposals) == 1 and proposals[0]["status"] == "pending"
        with repo.transaction("alice") as connection:
            run = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE owner=%s AND runtime='v4'").format(repo.table("core_runs")),
                ("alice",),
            ).fetchone()
        result = run["result"]
        assert result["receipts"] == [
            {
                "write_status": "pending_confirmation",
                "id": proposals[0]["id"],
                "kind": "proposal",
                "revision": proposals[0]["revision"],
                "code": "sensitive_confirmation",
            }
        ]
        assert "memory_receipts" not in result and "caveats" not in result
        headers = {"X-Token": "synthetic-dom-owner"}
        with httpx.Client(trust_env=False) as client:
            response = client.get(origin + "/api/chat/" + run["id"], headers=headers)
        assert response.status_code == 200
        meta = response.json()["meta"]
        assert meta["memory_receipts"] == result["receipts"]
        assert meta["receipts"] == result["receipts"]
