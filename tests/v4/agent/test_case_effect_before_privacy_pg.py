"""An old source present only in historical before bytes still revokes the private proof."""

from collections.abc import Iterator

import pytest

from mingjing_core.agent.journal import Journal
from mingjing_core.agent.toolkit import ToolContext, ToolRegistry
from mingjing_core.application.agent_case_effect_marker import SCHEMA
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.application.agent_tools_memory import source_ref
from mingjing_core.application.memory import MemoryService
from mingjing_core.repositories.postgres import PostgresRepository

from .test_case_index_lineage_pg import existing_case
from .test_loop_cycle_case_versions_pg import selected_run
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="before_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def historical_before_component(repo, fact_id=None, fact_field="fact_ids"):
    case, _ = existing_case(repo)
    old = MemoryService(repo).receive("alice", content="旧目标合成甲；无关尾句乙", source_id="old-before-only-source")
    fact_data = {fact_field: fact_id if fact_field == "source_fact_id" else [fact_id]} if fact_id else {}
    case = repo.update(
        "alice",
        "case",
        case["id"],
        {
            "state": {"goal": "旧目标合成甲"},
            "source_refs": [],
            "source_ids": [],
            **fact_data,
            "field_source_refs": {"title": [], "goal": [source_ref(old, 0, 6)]},
        },
        expected_revision=case["revision"],
    )
    run = selected_run(repo, case["id"], "将目标改成合成新计划")
    registry, journal = ToolRegistry(AgentToolsService(repo)), Journal(repo, "alice")
    args = {
        "id": case["id"],
        "changes": {"goal": "合成新计划"},
        "expected_revision": case["revision"],
        "message_id": run["request"]["source_message_id"],
        "quote": run["request"]["message"],
    }
    step = journal.next_or_replay(
        run, kind="tool", name="case_update", input_fp=registry.fingerprint("case_update", args)
    )
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(args["message_id"],), case_ids=(case["id"],))
    result = registry.execute("case_update", args, ctx)
    assert result.ok
    journal.complete(step, result.model_dump())
    repo.fail_run("alice", run["id"], "合成组件已结束，无对话发布", run["lease_token"], status="cancelled")
    current = repo.get("alice", "case", case["id"])
    refs = current["source_refs"] + [ref for values in current["field_source_refs"].values() for ref in values]
    assert old["id"] not in {ref["message_id"] for ref in refs}
    effect = next(row for row in repo.list("alice", "runtime_step") if row.get("schema") == SCHEMA)
    assert old["id"] in effect["source_ids"]
    return old, effect


@pytest.mark.parametrize("span", [None, (0, 6), (7, 12)])
def test_old_before_only_source_or_any_of_its_spans_clears_the_entire_private_proof(before_repo, span):
    old, effect = historical_before_component(before_repo)
    kind = "message" if span is None else "source_span"
    metadata = {} if span is None else {"message_id": old["id"], "start": span[0], "end": span[1]}
    before_repo.apply_privacy(
        "alice",
        {
            "schema_version": "core3.0",
            "owner_user_id": "alice",
            "revocations": [
                {
                    "kind": kind,
                    "entity_id": old["id"] if span is None else "old-before-span",
                    "operation": "deleted",
                    "metadata": metadata,
                }
            ],
        },
    )
    cleared = before_repo.get("alice", "runtime_step", effect["id"], include_deleted=True)
    assert cleared["status"] == "deleted" and "output" not in cleared


@pytest.mark.parametrize("fact_field", ["fact_ids", "used_fact_ids", "source_fact_id"])
def test_linked_fact_revocation_clears_new_private_case_proof(before_repo, fact_field):
    memory = MemoryService(before_repo)
    source = memory.receive("alice", content="我喜欢合成清淡口味", source_id="linked-case-effect-fact")
    receipt = memory.save_fact("alice", "self", source["id"], source["content"], "preference")
    assert receipt["write_status"] == "saved"
    _, effect = historical_before_component(before_repo, receipt["fact_id"], fact_field)
    assert effect["output"]["versions"] == {}
    before_repo.apply_privacy(
        "alice",
        {
            "schema_version": "core3.0",
            "owner_user_id": "alice",
            "revocations": [{"kind": "fact", "entity_id": receipt["fact_id"], "operation": "deleted", "metadata": {}}],
        },
    )
    cleared = before_repo.get("alice", "runtime_step", effect["id"], include_deleted=True)
    assert cleared["status"] == "deleted" and "output" not in cleared
    assert receipt["fact_id"] in effect["fact_ids"]
