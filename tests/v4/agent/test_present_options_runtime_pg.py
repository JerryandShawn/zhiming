"""Real option tools commit a single frozen public card only after safety checks."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.events import validate_event
from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.agent_options import load_options
from mingjing_core.application.agent_review_proofs import ReviewProofStore
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.run_event_read import RunEventReader
from mingjing_core.domain.contracts import CoreError, EvidenceError
from mingjing_core.models.errors import ModelUnavailable
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint

from .test_agent_runtime_pg import invoke, queued
from .test_agent_runtime_pg import repository_fixture as source_repo_fixture
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer, modify, writer


@pytest.fixture(name="options_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def decisions(label: str = "合成", **changes: Any) -> list[dict[str, Any]]:
    base = dict(
        benefit="了解书面条件",
        cost="费用待核实",
        risk="条件仍未知",
        reversibility="需核对退出条件",
        first_step="先询问",
    )
    return [dict(base, title=label + "A", **changes), dict(base, title=label + "B", **changes)]


def card(values: list[dict[str, Any]], ident: str = "decision") -> ToolCall:
    return ToolCall(ident, "present_options", {"options": values})


def stored_events(repo: PostgresRepository, ident: str) -> list[dict[str, Any]]:
    with repo.transaction("alice") as connection:
        return connection.execute(
            sql.SQL("SELECT seq,kind,payload FROM {} WHERE owner='alice' AND run_id=%s ORDER BY seq").format(
                repo.table("core_run_events")
            ),
            (ident,),
        ).fetchall()


class CrashedAfterToolsPort(ScriptedPort):
    def stream(self, *args: Any, **kwargs: Any) -> Any:
        if self.requests:
            raise RuntimeError("synthetic process loss before final")
        yield from super().stream(*args, **kwargs)


def uncommitted_card(repo: PostgresRepository) -> dict[str, Any]:
    run = queued(repo)
    with pytest.raises(RuntimeError, match="synthetic process loss"):
        invoke(repo, run, CrashedAfterToolsPort([answer("", [card(decisions("未提交"))])]))
    assert load_options(repo, run) is not None and repo.fetch_run("alice", run["id"])["result"] is None
    return run


def test_card_envelope_event_and_replay_are_identical_and_only_after_commit(options_repo: PostgresRepository) -> None:
    repo, run = options_repo, queued(options_repo)
    primary = ScriptedPort([answer("", [card(decisions())]), answer("请先核对条件再决定")])
    observed: list[dict] = []

    def emit(event: dict) -> None:
        if event["type"] in {"present_options", "final"}:
            assert repo.fetch_run("alice", run["id"])["status"] == "succeeded"
        observed.append(event)

    runtime = AgentRuntime(repo, primary, SyntheticMeter(), offline=True)
    result = runtime.execute(SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"], emit)
    public = [event["data"] for event in observed if event["type"] == "present_options"]
    assert len(public) == 1 and result["options"]["options_id"].startswith("options-")
    assert public[0]["options"] == result["options"]["options"]
    assert all(row["reversibility"] == "unknown" and row["unknowns"] == [] for row in result["options"]["options"])
    for event in observed:
        validate_event(event["type"], event["data"])
    reader = RunEventReader(repo, "alice", run["id"])
    with ThreadPoolExecutor(max_workers=3) as pool:
        pages = list(pool.map(lambda _: reader.page(0), range(3)))
    assert all(page[0][-1]["data"]["envelope"] == result for page in pages)
    rows = stored_events(repo, run["id"])
    assert sum(row["kind"] == "present_options" for row in rows) == sum(row["kind"] == "final" for row in rows) == 1
    assert "reasoning" not in json.dumps([row["payload"] for row in rows], ensure_ascii=False)


def test_last_successful_card_wins_and_later_failed_tool_does_not_replace_it(options_repo: PostgresRepository) -> None:
    repo, run = options_repo, queued(options_repo)
    calls = [card(decisions("旧"), "a"), card(decisions("新"), "b"), card(decisions("失败")[:1], "c")]
    result, events = invoke(repo, run, ScriptedPort([answer("", calls), answer("合成最后回答")]))
    assert result["options"]["options"][0]["title"] == "新A"
    assert sum(event["type"] == "present_options" for event in events) == 1


def test_old_epoch_card_from_interrupted_execution_cannot_be_published_in_new_epoch(
    options_repo: PostgresRepository,
) -> None:
    repo, run = options_repo, uncommitted_card(options_repo)
    modify(repo, run, "retry_epoch=1")
    current = repo.fetch_run("alice", run["id"])
    assert load_options(repo, current) is None
    result, events = invoke(repo, current, ScriptedPort([answer("新周期不含旧卡")]))
    assert result["options"] is None and not any(row["type"] == "present_options" for row in events)


@pytest.mark.parametrize("clause", ["status='failed'", "error_code='SYNTHETIC_FAILED'"])
def test_failed_or_error_marked_tool_is_not_a_publishable_card(options_repo: PostgresRepository, clause: str) -> None:
    repo, run = options_repo, uncommitted_card(options_repo)
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET " + clause + " WHERE run_id=%s AND name='present_options'").format(
                repo.table("core_run_steps")
            ),
            (run["id"],),
        )
    assert load_options(repo, run) is None
    current = repo.fetch_run("alice", run["id"])
    result = AgentFinalizer(repo).finalize(
        current,
        text="合成无卡片回答",
        alias_map={},
        versions=current["state_version"],
        snapshot_revision=repo.get_revision("alice"),
    )
    assert result["options"] is None


def test_completed_tool_cannot_send_public_card_before_final_commit(options_repo: PostgresRepository) -> None:
    repo, run = options_repo, uncommitted_card(options_repo)
    with pytest.raises(EvidenceError, match="真实信封"):
        RuntimeEvents(repo, run, None).send("present_options", load_options(repo, run).value)
    assert not any(row["kind"] == "present_options" for row in stored_events(repo, run["id"]))


def test_critic_pass_receives_actual_card_and_proof_binds_it(options_repo: PostgresRepository) -> None:
    repo, run = options_repo, queued(options_repo)
    critic = ScriptedPort([answer('{"verdict":"pass","issues":[]}')])
    result, _ = invoke(repo, run, ScriptedPort([answer("", [card(decisions())]), answer("合成初稿")]), critic=critic)
    material = json.loads(critic.requests[0]["messages"][-1].content)
    assert material["options"] == result["options"] and result["review"]["state"] == "passed"
    proof = repo.get("alice", "runtime_step", f"{run['id']}:e0:agent_review")["output"]
    assert proof["options_source_sha256"] and proof["options_sha256"] and proof["options_suppressed"] is False


@pytest.mark.parametrize("revision_fails", [False, True])
def test_card_critic_issue_can_be_quoted_and_revision_never_republishes_old_card(
    options_repo: PostgresRepository, revision_fails: bool
) -> None:
    class RevisionPort(ScriptedPort):
        def stream(self, *args: Any, **kwargs: Any) -> Any:
            if len(self.requests) == 2 and revision_fails:
                raise ModelUnavailable()
            yield from super().stream(*args, **kwargs)

    repo, run = options_repo, queued(options_repo)
    verdict = {
        "verdict": "revise",
        "issues": [dict(type="overpromise", quote="保证成功", severity=4, fix_hint="保留未知")],
    }
    primary = RevisionPort(
        [answer("", [card(decisions(benefit="保证成功"))]), answer("合成初稿"), answer("条件仍需核实")]
    )
    result, events = invoke(repo, run, primary, critic=ScriptedPort([answer(json.dumps(verdict, ensure_ascii=False))]))
    assert result["options"] is None and not any(row["type"] == "present_options" for row in events)
    assert result["review"]["state"] == ("skipped" if revision_fails else "revised")
    assert result["text"] == ("合成初稿" if revision_fails else "条件仍需核实")
    assert len(primary.requests) == (2 if revision_fails else 3)
    if not revision_fails:
        assert primary.requests[-1]["tools"] == []


def test_unrelated_saved_receipt_does_not_authorize_card_save_claim(options_repo: PostgresRepository) -> None:
    repo, run = options_repo, queued(options_repo)
    primary = ScriptedPort(
        [
            answer("", [ToolCall("write", "memory_write", writer(run)), card(decisions(benefit="已经保存这项安排"))]),
            answer("合成独立初稿"),
        ]
    )
    with pytest.raises(CoreError, match="决策卡片"):
        invoke(repo, run, primary)
    assert len(repo.list("alice", "fact")) == 1 and repo.fetch_run("alice", run["id"])["result"] is None


def test_card_unknown_citation_cannot_publish(options_repo: PostgresRepository) -> None:
    repo, run = options_repo, queued(options_repo)
    with pytest.raises(CoreError, match="决策卡片"):
        invoke(repo, run, ScriptedPort([answer("", [card(decisions(benefit="依据〔f999〕"))]), answer("合成初稿")]))
    assert not [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]


def test_fact_cited_only_in_card_is_in_message_and_envelope_lineage(options_repo: PostgresRepository) -> None:
    repo, run = options_repo, queued(options_repo)
    calls = [ToolCall("write", "memory_write", writer(run)), card(decisions(benefit="参考已确认约束〔f1〕"))]
    result, _ = invoke(repo, run, ScriptedPort([answer("", calls), answer("请先核对条件")]))
    fact = repo.list("alice", "fact")[0]
    assert result["used_fact_ids"] == [fact["id"]] and "f1" not in result["text"]
    message = repo.get("alice", "message", result["message_id"])
    assert message["used_fact_ids"] == [fact["id"]] and result["options"]["options"][0]["benefit"].endswith("〔f1〕")


def tamper_request(repo: PostgresRepository, run: dict[str, Any], proof: dict[str, Any]) -> None:
    ident = f"{run['id']}:e0:agent_model_request:{proof['output']['critic_seq']}"
    row = repo.get("alice", "runtime_step", ident)
    value = copy.deepcopy(row["output"])
    messages = value["budget"]["messages"]
    material = json.loads(messages[-1]["content"])
    material["options"]["options"][0]["benefit"] = "被调换的合成收益"
    messages[-1]["content"] = json.dumps(material, ensure_ascii=False)
    repo.update(
        "alice",
        "runtime_step",
        ident,
        {"output": value, "output_sha256": fingerprint(value)},
        expected_revision=row["revision"],
    )


@pytest.mark.parametrize("target", ["proof", "tool", "request"])
def test_self_consistent_tampering_cannot_rebind_critic_to_another_card(
    options_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    repo, run = options_repo, queued(options_repo)
    original = ReviewProofStore.save

    def tamper(self: ReviewProofStore, *args: Any, **kwargs: Any) -> Any:
        receipt = original(self, *args, **kwargs)
        proof = repo.get("alice", "runtime_step", receipt.proof_id)
        if target == "proof":
            value = dict(proof["output"], options_sha256="0" * 64)
            repo.update(
                "alice",
                "runtime_step",
                receipt.proof_id,
                {"output": value, "output_sha256": fingerprint(value)},
                expected_revision=proof["revision"],
            )
            return replace(receipt, proof_sha256=fingerprint(value))
        if target == "tool":
            with repo.transaction("alice") as connection:
                selected = load_options(repo, run)
                row = connection.execute(
                    sql.SQL("SELECT output FROM {} WHERE run_id=%s AND epoch=0 AND seq=%s").format(
                        repo.table("core_run_steps")
                    ),
                    (run["id"], selected.seq),
                ).fetchone()
                value = copy.deepcopy(row["output"])
                value["data"]["options"][0]["cost"] = "被调换的合成成本"
                connection.execute(
                    sql.SQL("UPDATE {} SET output=%s WHERE run_id=%s AND epoch=0 AND seq=%s").format(
                        repo.table("core_run_steps")
                    ),
                    (Jsonb(value), run["id"], selected.seq),
                )
        else:
            tamper_request(repo, run, proof)
        return receipt

    monkeypatch.setattr(ReviewProofStore, "save", tamper)
    with pytest.raises(CoreError):
        invoke(
            repo,
            run,
            ScriptedPort([answer("", [card(decisions())]), answer("合成初稿")]),
            critic=ScriptedPort([answer('{"verdict":"pass","issues":[]}')]),
        )
    assert repo.fetch_run("alice", run["id"])["result"] is None
    assert not [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]


def test_missing_public_card_and_final_recover_once_and_corruption_fails_closed(
    options_repo: PostgresRepository,
) -> None:
    repo, run = options_repo, queued(options_repo)
    result, _ = invoke(repo, run, ScriptedPort([answer("", [card(decisions())]), answer("合成终稿")]))
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE owner='alice' AND run_id=%s AND kind IN ('present_options','final')").format(
                repo.table("core_run_events")
            ),
            (run["id"],),
        )
    reader = RunEventReader(repo, "alice", run["id"])
    assert reader.page(0)[0][-1]["data"]["envelope"] == result
    changed = dict(result["options"], options_id="wrong-card")
    with pytest.raises(EvidenceError):
        RuntimeEvents(repo, repo.fetch_run("alice", run["id"]), None).send("present_options", changed)
    with repo.transaction("alice") as connection:
        row = next(item for item in stored_events(repo, run["id"]) if item["kind"] == "present_options")
        changed = dict(row["payload"], options_id="corrupted-card")
        connection.execute(
            sql.SQL("UPDATE {} SET payload=%s WHERE run_id=%s AND seq=%s").format(repo.table("core_run_events")),
            (Jsonb(changed), run["id"], row["seq"]),
        )
    with pytest.raises(EvidenceError, match="真实提交"):
        reader.page(0)
