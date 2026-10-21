"""Strict reply migration keeps real lineage and never mutates delivery state."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.adapters.delivery import DeliveryUncertain, OutboxService
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import LeaseConflict
from mingjing_core.memory.backfill import backfill
from mingjing_core.repositories.postgres import PostgresRepository

from .backfill_support import core3, core4, food_fact, store_result
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_loop_cycle_support import cycle_repo as source_fixture


@pytest.fixture(name="repo")
def repository(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch):
    yield from source_fixture.__wrapped__(p2_repo, monkeypatch)


def replies(repo: PostgresRepository) -> list[dict[str, Any]]:
    return [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]


@pytest.mark.parametrize("version", ["core3", "core4", "core3-temporary"])
def test_real_lineage_dry_run_apply_and_repeat_have_no_false_facts(repo: PostgresRepository, version: str) -> None:
    run, result = core4(repo) if version == "core4" else core3(repo, temporary=version == "core3-temporary")
    memory = MemoryService(repo)
    before = [(row["id"], row["revision"]) for row in repo.list("alice", "fact")]
    assert backfill(memory, "alice")["assistant_created"] == 1 and replies(repo) == []
    assert backfill(memory, "alice", apply=True)["assistant_created"] == 1
    reply = replies(repo)[0]
    prefix = "used" if version == "core4" else "cited"
    assert reply["used_fact_ids"] == result[prefix + "_fact_ids"]
    assert reply["used_claim_ids"] == result[prefix + "_claim_ids"]
    assert run["request"]["source_message_id"] in reply["source_ids"]
    assert reply["content"] == result["answer"] and reply["thread_id"] == "life:self"
    assert all(repo.get("alice", "message", ident)["subject_id"] == "self" for ident in reply["source_ids"])
    after = [(row["id"], row["revision"]) for row in repo.list("alice", "fact")]
    assert before == after
    repeated = backfill(memory, "alice", apply=True)
    assert repeated["assistant_created"] == repeated["message_metadata"] == repeated["search_tokens"] == 0
    assert repeated["assistant_existing"] == 1 and replies(repo) == [reply]


@pytest.mark.parametrize(
    "fault",
    [
        "unknown_schema",
        "bad_validation",
        "wrong_run",
        "bad_core4_field",
        "foreign_fact",
        "foreign_claim",
        "wrong_subject",
        "unversioned_fact",
        "claim_version",
        "revoked_claim",
        "source_withdrawal",
    ],
)
def test_corrupt_core4_or_foreign_withdrawn_references_never_create_reply(repo: PostgresRepository, fault: str) -> None:
    run, result = core4(repo)
    broken = deepcopy(result)
    fact = repo.get("alice", "fact", result["used_fact_ids"][0])
    claim = repo.get("alice", "interpretive_claim", result["used_claim_ids"][0])
    if fault == "unknown_schema":
        broken["schema_version"] = broken["schema"] = "core5.0"
    elif fault == "bad_validation":
        broken["validation"]["valid"] = False
    elif fault == "wrong_run":
        broken["meta"]["core_run"]["run_id"] = "not-this-run"
    elif fault == "bad_core4_field":
        broken["cited_fact_ids"] = []
    elif fault == "foreign_fact":
        broken["used_fact_ids"] = [food_fact(repo, "bob")["id"]]
    elif fault == "foreign_claim":
        foreign = repo.put(
            "bob", "interpretive_claim", "bob-claim", {"run_id": run["id"], "epoch": 0}, expected_revision=0
        )
        broken["used_claim_ids"] = [foreign["id"]]
    elif fault == "wrong_subject":
        repo.create_subject("alice", "someone-else", "合成他人")
        with repo.transaction("alice") as connection:
            connection.execute(
                sql.SQL("UPDATE {} SET subject='someone-else' WHERE owner='alice' AND kind='fact' AND id=%s").format(
                    repo.table("core_entities")
                ),
                (fact["id"],),
            )
    elif fault == "unversioned_fact":
        broken["used_fact_ids"] = [food_fact(repo)["id"]]
    elif fault == "claim_version":
        repo.update(
            "alice", "interpretive_claim", claim["id"], {"extra": "changed"}, expected_revision=claim["revision"]
        )
    else:
        kind, ident = (
            ("interpretive_claim", claim["id"])
            if fault == "revoked_claim"
            else ("message", run["request"]["source_message_id"])
        )
        with repo.transaction("alice") as connection:
            repo.revoke(connection, "alice", kind, ident, "deleted")
    store_result(repo, run, broken)
    result = backfill(MemoryService(repo), "alice", apply=True)
    assert result["assistant_created"] == 0 and result["assistant_skipped"] == 1 and replies(repo) == []


def test_private_metadata_stays_in_private_thread_and_has_no_long_term_reply(repo: PostgresRepository) -> None:
    threads = ThreadService(repo)
    thread = threads.create("alice", request_id="private-backfill", incognito=True)
    source = threads.receive("alice", thread["id"], "合成私密原话", request_id="private-source")
    original = deepcopy(repo.get("alice", "message", source["id"]))
    result = backfill(MemoryService(repo), "alice", apply=True)
    assert result["message_metadata"] == 0 and result["assistant_created"] == 0
    assert repo.get("alice", "message", source["id"]) == original


@pytest.mark.parametrize("status", ["sent", "uncertain"])
def test_reply_backfill_does_not_reopen_or_mutate_terminal_outbox(repo: PostgresRepository, status: str) -> None:
    repo.bind_channel("alice", "feishu", "ou_syntheticBackfill")
    run, result = core4(repo)
    outbox = OutboxService(repo)
    item = outbox.prepare_delivery(
        owner="alice", run_id=run["id"], business_id="backfill-test", channel="feishu", target="ou_syntheticBackfill"
    )
    claim = outbox.claim_delivery(owner="alice", outbox_id=item["id"])
    outbox.record_delivery(
        owner="alice",
        outbox_id=item["id"],
        status=status,
        message_id="synthetic-receipt" if status == "sent" else None,
        claim_token=claim["claim_token"],
    )
    with repo.transaction("alice") as connection:
        query = sql.SQL("SELECT * FROM {} WHERE owner='alice' AND id=%s").format(repo.table("delivery_outbox"))
        before = connection.execute(query, (item["id"],)).fetchone()
    assert backfill(MemoryService(repo), "alice", apply=True)["assistant_created"] == 1
    with repo.transaction("alice") as connection:
        assert connection.execute(query, (item["id"],)).fetchone() == before
    assert replies(repo)[0]["used_claim_ids"] == result["used_claim_ids"]
    with pytest.raises(DeliveryUncertain if status == "uncertain" else LeaseConflict):
        outbox.claim_delivery(owner="alice", outbox_id=item["id"])


@pytest.mark.parametrize(
    "fault", ["false_valid", "string_valid", "validation_schema", "foreign_fact", "native_claim", "temporary_quote"]
)
def test_legacy_core3_compatibility_never_accepts_false_validation_or_fabricated_refs(
    repo: PostgresRepository, fault: str
) -> None:
    run, result = core3(repo, temporary=fault == "temporary_quote")
    broken = deepcopy(result)
    if fault in {"false_valid", "string_valid"}:
        broken["validation"]["valid"] = False if fault == "false_valid" else "true"
    elif fault == "validation_schema":
        broken["validation"]["schema"] = "core4.0"
    elif fault == "foreign_fact":
        broken["cited_fact_ids"] = [food_fact(repo, "bob")["id"]]
    elif fault == "native_claim":
        broken["cited_claim_ids"] = [run["id"] + ":e0:synthetic-rule"]
    else:
        broken["evidence"][0]["source_refs"][0]["quote"] = "并非真实原话"
    store_result(repo, run, broken)
    observed = backfill(MemoryService(repo), "alice", apply=True)
    assert observed["assistant_created"] == 0 and observed["assistant_skipped"] == 1 and replies(repo) == []


def test_core3_uses_only_legacy_citations_not_core4_fields(repo: PostgresRepository) -> None:
    run, result = core3(repo)
    polluted = dict(result, used_fact_ids=["untrusted-new-field"], used_claim_ids=["untrusted-new-claim"])
    store_result(repo, run, polluted)
    assert backfill(MemoryService(repo), "alice", apply=True)["assistant_created"] == 1
    assert replies(repo)[0]["used_fact_ids"] == result["cited_fact_ids"]
    assert replies(repo)[0]["used_claim_ids"] == result["cited_claim_ids"]


@pytest.mark.parametrize("fault", ["wrong_runtime", "boolean_epoch", "source_revision"])
def test_exact_runtime_epoch_and_source_revision_are_required(repo: PostgresRepository, fault: str) -> None:
    run, result = core4(repo)
    with repo.transaction("alice") as connection:
        if fault == "wrong_runtime":
            connection.execute(
                sql.SQL("UPDATE {} SET runtime='v3' WHERE owner='alice' AND id=%s").format(repo.table("core_runs")),
                (run["id"],),
            )
        elif fault == "boolean_epoch":
            connection.execute(
                sql.SQL(
                    "UPDATE {} SET data=jsonb_set(data,'{{epoch}}','false') "
                    "WHERE owner='alice' AND kind='interpretive_claim' AND id=%s"
                ).format(repo.table("core_entities")),
                (result["used_claim_ids"][0],),
            )
        else:
            source = repo.get("alice", "message", run["request"]["source_message_id"])
            repo.update("alice", "message", source["id"], {"case_ids": []}, expected_revision=source["revision"])
    observed = backfill(MemoryService(repo), "alice", apply=True)
    assert observed["assistant_created"] == 0 and observed["assistant_skipped"] == 1 and replies(repo) == []


def test_real_private_core4_reply_is_never_backfilled_into_life(repo: PostgresRepository) -> None:
    threads = ThreadService(repo)
    thread = threads.create("alice", request_id="private-run", incognito=True)
    source = threads.receive("alice", thread["id"], "合成私密本轮", request_id="private-runtime-source")
    run = repo.queue_run(
        "alice",
        "private-runtime",
        {
            "message": source["content"],
            "source_message_id": source["id"],
            "thread_id": thread["id"],
            "incognito": True,
            "case_ids": [],
        },
    )
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET runtime='v4',thread_id=%s WHERE owner='alice' AND id=%s").format(
                repo.table("core_runs")
            ),
            (thread["id"], run["id"]),
        )
    run = repo.claim_run("alice", run["id"], lease_seconds=150)
    runtime = AgentRuntime(repo, ScriptedPort([answer("合成私密回复")]), SyntheticMeter(), offline=True)
    assert runtime.execute(SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"])["schema"] == "core4.0"
    before = deepcopy(repo.list("alice", "message"))
    observed = backfill(MemoryService(repo), "alice", apply=True)
    assert observed["assistant_created"] == observed["message_metadata"] == 0
    assert observed["assistant_skipped"] == 1 and repo.list("alice", "message") == before
    assert all(row["thread_id"] == thread["id"] and not row["search_tokens"] for row in before)
