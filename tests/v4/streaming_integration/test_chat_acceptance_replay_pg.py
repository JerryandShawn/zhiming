"""Existing operation pins and inbox identities remain authoritative for JSON."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.adapters.web import create_app
from mingjing_core.application.run_acceptance import run_acceptance, submission_target
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from tests.v4.agent.legacy_dom_http_support import local_app
from tests.v4.agent.test_loop_cycle_support import ScriptedPort
from tests.v4.agent.test_runtime_assembly_pg import configure, service
from tests.v4.streaming_integration.chat_acceptance_support import counts
from tests.v4.streaming_integration.chat_acceptance_support import (
    repository as repository,
)
from tests.v4.streaming_integration.event_http_support import HEADERS


def test_v3_pin_rejects_json_after_owner_is_set_to_v4_without_new_writes(
    acceptance_repo: Any,
) -> None:
    repo, core = acceptance_repo, service(acceptance_repo, ScriptedPort([]))
    old = core.submit(owner="alice", request_id="pinned-old", message="合成旧运行")
    configure(repo)
    with (
        local_app(create_app(core)) as base,
        httpx.Client(base_url=base, trust_env=False) as client,
    ):
        before = counts(repo)
        response = client.post(
            "/api/chat",
            headers=dict(HEADERS, Accept="application/json"),
            json={"request_id": "pinned-old", "message": "合成旧运行"},
        )
        assert response.status_code == 406 and counts(repo) == before
        assert repo.fetch_run("alice", old["id"])["runtime"] == "v3"


def test_readonly_preflight_uses_same_persisted_pin_and_does_not_create_identity(
    acceptance_repo: Any,
) -> None:
    repo = acceptance_repo
    before = counts(repo)
    assert submission_target(repo, "new-owner", "self", "new") == ("v3", None)
    assert counts(repo) == before
    configure(repo)
    core = service(repo, ScriptedPort([]))
    old = core.submit(owner="alice", request_id="pin", message="合成固定输入")
    configure(repo, "v3")
    runtime, raw = submission_target(repo, "alice", "self", "pin")
    assert runtime == "v4" and raw["id"] == old["id"]
    assert submission_target(repo, "alice", "self", "another") == ("v3", None)


@pytest.mark.parametrize(
    "damage",
    ["foreign-subject", "foreign-primary", "changed-segments", "changed-message"],
)
def test_ack_is_not_authorized_by_arbitrary_persisted_identifiers(
    acceptance_repo: Any, damage: str
) -> None:
    repo = acceptance_repo
    configure(repo)
    core = service(repo, ScriptedPort([]))
    run = core.submit(owner="alice", request_id="ack-source", message="合成真实原话")
    request = dict(run["request"])
    if damage == "foreign-subject":
        repo.create_subject("alice", "not-granted", "合成未授权人物", consent="pending")
        field, value = "subject", "not-granted"
    else:
        field = "request"
        if damage == "foreign-primary":
            foreign = core.memory.receive(
                "bob", content="合成外人原话", source_id="foreign"
            )
            request.update(
                source_message_id=foreign["id"], source_message_ids=[foreign["id"]]
            )
        elif damage == "changed-segments":
            request["source_segments"] = []
        else:
            request["message"] = "伪造原话"
        value = Jsonb(request)
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET {}=%s WHERE owner='alice' AND id=%s").format(
                repo.table("core_runs"), sql.Identifier(field)
            ),
            (value, run["id"]),
        )
    with pytest.raises((EvidenceError, ScopeError)):
        run_acceptance(repo, "alice", run["id"])


def test_withdrawn_source_cannot_return_an_ack_or_be_reimported(
    acceptance_repo: Any,
) -> None:
    repo = acceptance_repo
    configure(repo)
    core = service(repo, ScriptedPort([]))
    run = core.submit(owner="alice", request_id="withdrawn", message="合成待撤销原话")
    original = core.memory.get_source("alice", run["request"]["source_message_id"])
    repo.delete(
        "alice", "message", original["id"], expected_revision=original["revision"]
    )
    with pytest.raises((EvidenceError, ScopeError)):
        run_acceptance(repo, "alice", run["id"])
    with pytest.raises((EvidenceError, ScopeError)):
        core.submit(owner="alice", request_id="withdrawn", message="合成待撤销原话")
    assert (
        repo.get("alice", "message", original["id"], include_deleted=True)["status"]
        == "deleted"
    )
