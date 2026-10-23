"""Multiple selected cases share model dependencies without borrowing unproved effects."""

import copy
import uuid
from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .case_effect_chain_support import effect_row, replace_effect
from .case_status_write_support import BeforeFinal, PreparedWrite
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer, modify
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="interleaved_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def prepare_interleaved(repo, monkeypatch, same_response):
    memory = MemoryService(repo)
    first = memory.create_case("alice", "self", "合成事项甲")
    second = memory.create_case("alice", "self", "合成事项乙")
    ids, text = [first["id"], second["id"]], "甲的目标改成合成新计划，关闭乙，最后关闭甲"
    source = memory.receive("alice", content=text, source_id=uuid.uuid4().hex, case_ids=ids)
    run = repo.queue_run(
        "alice", uuid.uuid4().hex, {"message": text, "source_message_id": source["id"], "case_ids": ids}, case_ids=ids
    )
    modify(repo, run, "runtime='v4',thread_id='life:self'")
    run = repo.claim_run("alice", run["id"], lease_seconds=3600)
    updates = [(first, 1, {"goal": "合成新计划"}), (second, 1, {"status": "closed"}), (first, 2, {"status": "closed"})]
    calls = [
        ToolCall(
            f"change-{index}",
            "case_update",
            {
                "id": case["id"],
                "expected_revision": revision,
                "changes": change,
                "message_id": source["id"],
                "quote": text,
            },
        )
        for index, (case, revision, change) in enumerate(updates)
    ]
    responses = [answer("", calls)] if same_response else [answer("", [call]) for call in calls]
    port, prepared = ScriptedPort([*responses, answer("事项变更〔e1〕〔e2〕")]), []

    def pause(self, actual, **inputs):
        prepared.append(PreparedWrite(repo, copy.deepcopy(actual), copy.deepcopy(inputs), first))
        raise BeforeFinal()

    with monkeypatch.context() as scope:
        scope.setattr(AgentFinalizer, "finalize", pause)
        with pytest.raises(BeforeFinal):
            AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
                SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"]
            )
    assert len(prepared) == 1
    return prepared[0]


@pytest.mark.parametrize("same_response", [False, True])
def test_interleaved_selected_cases_verify_every_real_revision(interleaved_repo, monkeypatch, same_response):
    prepared = prepare_interleaved(interleaved_repo, monkeypatch, same_response)
    assert prepared.finish()["text"] == "事项变更〔e1〕〔e2〕"


def test_another_selected_case_cannot_supply_forged_intermediate_dependency_credit(interleaved_repo, monkeypatch):
    prepared = prepare_interleaved(interleaved_repo, monkeypatch, False)
    output = effect_row(prepared, 4)["output"]
    output["before"]["title"] = "伪造的乙历史"
    replace_effect(prepared, 4, output)
    with pytest.raises(CoreError):
        prepared.finish()
    prepared.unpublished()
