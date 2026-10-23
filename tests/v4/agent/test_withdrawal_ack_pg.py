"""Deletion acknowledgements use actual withdrawn-epoch ledger proofs, never old output."""

from contextlib import suppress
from copy import deepcopy
from pathlib import Path

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

import mingjing_core.application.agent_finalization as finalization
from mingjing_core.domain.contracts import CoreError
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_corpus import execution_overlay

from .test_eval_v4_native_privacy_pg import target as target

__all__ = ["target"]
ROOT = Path(__file__).resolve().parents[3]


class RestoreSavepoint(Exception):
    pass


def f02():
    return execution_overlay(next(case for case in load_scenarios(ROOT / "tools/eval/scenarios") if case.id == "F02"))


def ledger(repo, run):
    with repo.transaction(run["owner"]) as connection:
        step = connection.execute(
            sql.SQL("SELECT seq FROM {} WHERE owner=%s AND run_id=%s AND epoch=0 AND name='memory_forget'").format(
                repo.table("core_run_steps")
            ),
            (run["owner"], run["id"]),
        ).fetchone()
        key = f"run:{run['id']}:e0:s{step['seq']}"
        row = connection.execute(
            sql.SQL(
                "SELECT receipt FROM {} WHERE owner=%s AND operation='agent_memory_forget' AND request_key=%s"
            ).format(repo.table("core_mutation_requests")),
            (run["owner"], key),
        ).fetchone()
    return key, step["seq"], row["receipt"]["fact_id"]


def tamper(repo, run, mode):
    key, seq, fact_id = ledger(repo, run)
    owner, ident, source = run["owner"], run["id"], run["request"]["source_message_id"]
    updates = {
        "fingerprint": (
            "core_mutation_requests",
            "SET fingerprint=%s WHERE owner=%s AND request_key=%s",
            ("0" * 64, owner, key),
        ),
        "operation": (
            "core_mutation_requests",
            "SET operation='agent_memory_write' WHERE owner=%s AND request_key=%s",
            (owner, key),
        ),
        "sequence": (
            "core_run_steps",
            "SET seq=seq+1000 WHERE owner=%s AND run_id=%s AND epoch=0 AND seq=%s",
            (owner, ident, seq),
        ),
        "epoch": (
            "core_run_steps",
            "SET epoch=2 WHERE owner=%s AND run_id=%s AND epoch=0 AND seq=%s",
            (owner, ident, seq),
        ),
        "fact_body": (
            "core_entities",
            "SET data=%s WHERE owner=%s AND kind='fact' AND id=%s",
            (Jsonb({"content": "synthetic stale body"}), owner, fact_id),
        ),
        "source_role": (
            "core_entities",
            "SET data=jsonb_set(data,%s,%s) WHERE owner=%s AND kind='message' AND id=%s",
            (["role"], Jsonb("assistant"), owner, source),
        ),
    }
    with repo.transaction(owner) as connection:
        if mode == "tombstone":
            connection.execute(
                sql.SQL("DELETE FROM {} WHERE owner=%s AND kind='fact' AND entity_id=%s").format(
                    repo.table("core_revocations")
                ),
                (owner, fact_id),
            )
        elif mode == "source_revoked":
            repo.revoke(connection, owner, "message", source, "deleted")
        else:
            table, update, values = updates[mode]
            connection.execute(sql.SQL("UPDATE {} " + update).format(repo.table(table)), values)


def assert_no_ack(bridge, repo, run, versions):
    with suppress(CoreError):
        assert bridge(repo, run, versions) == ()


def test_real_public_receipt_survives_only_with_owner_run_operation_source_and_erasure_proofs(target, monkeypatch):
    actual = finalization.withdrawal_acknowledgements
    checked = []

    def inspected(repo, run, versions):
        receipt = actual(repo, run, versions)
        if receipt:
            for mode in (
                "fingerprint",
                "operation",
                "sequence",
                "epoch",
                "fact_body",
                "source_role",
                "tombstone",
                "source_revoked",
            ):
                with pytest.raises(RestoreSavepoint), repo.transaction(run["owner"]):
                    tamper(repo, run, mode)
                    assert_no_ack(actual, repo, run, versions)
                    checked.append(mode)
                    raise RestoreSavepoint()
            for field, value in (("owner", "another-owner"), ("id", "another-run"), ("retry_epoch", 0)):
                assert_no_ack(actual, repo, dict(run, **{field: value}), versions)
                checked.append(field)
            changed = deepcopy(versions)
            changed["message:" + run["request"]["source_message_id"]] += 1
            assert_no_ack(actual, repo, run, changed)
            checked.append("source_version")
        return receipt

    monkeypatch.setattr(finalization, "withdrawal_acknowledgements", inspected)
    result = evaluate_scenario(f02(), target, target_name="v4")
    assert result["status"] == "passed", result["failed_assertions"]
    assert len(checked) == 12
    current = target.repo.fetch_run(target.owner, target.run_ids[-1])
    assert current["status"] == "succeeded" and current["retry_epoch"] == 1
    assert current["result"]["receipts"][0]["write_status"] == "deleted"
    assert all(step["output"] is None for step in target.inspect_db()["observed_tools"] if step["epoch"] == 0)


@pytest.mark.parametrize("mode", ["fingerprint", "tombstone", "source_role"])
def test_rejected_deletion_proof_cannot_publish_any_final_envelope(target, monkeypatch, mode):
    actual = finalization.withdrawal_acknowledgements

    def rejected(repo, run, versions):
        if run["retry_epoch"] == 1:
            tamper(repo, run, mode)
        return actual(repo, run, versions)

    monkeypatch.setattr(finalization, "withdrawal_acknowledgements", rejected)
    result = evaluate_scenario(f02(), target, target_name="v4")
    assert result["status"] == "failed"
    current = target.repo.fetch_run(target.owner, target.run_ids[-1])
    assert current["result"] is None and current["status"] != "succeeded"
    assert not [
        message
        for message in target.repo.list(target.owner, "message")
        if message.get("role") == "assistant" and message.get("run_id") == current["id"]
    ]
    with target.repo.transaction(target.owner) as connection:
        count = connection.execute(
            sql.SQL("SELECT count(*) AS count FROM {} WHERE owner=%s AND run_id=%s AND kind='final'").format(
                target.repo.table("core_run_events")
            ),
            (target.owner, current["id"]),
        ).fetchone()["count"]
    assert count == 0
