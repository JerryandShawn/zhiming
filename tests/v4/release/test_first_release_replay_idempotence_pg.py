"""One real-PG reproducer for full privacy replay, including every checkpoint row."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb
from test_first_release_local_restore_pg import sample as sample

from mingjing_core.adapters.delivery import DeliveryUncertain, OutboxService
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.runtime import LangGraphRuntime
from tools.deploy_core import apply_withdrawals, export_withdrawals
from tools.first_release_local_restore import execute

BODY = "SYNTHETIC_PRIVATE_REPLAY_BODY"
TEXT = "我喜欢合成安静书房"
CHECKPOINTS = ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations")


def seed_owner(repo, owner):
    repo.ensure_owner(owner)
    memory = MemoryService(repo)
    source = memory.receive(owner, content=TEXT, source_id="synthetic-source", channel="synthetic")
    fact = memory.save_fact(owner, "self", source["id"], TEXT)
    run = repo.begin_run(owner, "synthetic-run", {"source_message_id": source["id"]}, depth="fast")
    repo.fail_run(owner, run["id"], "SYNTHETIC_FAILED", run["lease_token"])
    with repo.transaction(owner) as connection:
        connection.execute(
            "UPDATE mingjing_core.core_runs SET state_version=%s,retry_epoch=1,result=%s WHERE id=%s",
            (
                Jsonb({"message:" + source["id"]: 1, "fact:" + fact["id"]: fact["revision"]}),
                Jsonb({"text": BODY}),
                run["id"],
            ),
        )
        for status in ("sent", "uncertain"):
            connection.execute(
                "INSERT INTO mingjing_core.delivery_outbox(id,owner,subject,business_id,channel,target,run_id,"
                "payload,dependencies,status,attempts,due) VALUES(%s,%s,'self',%s,'feishu','ou_synthetic',"
                "%s,%s,'{}','pending',0,%s)",
                (
                    owner + "-" + status,
                    owner,
                    owner + "-" + status,
                    run["id"],
                    Jsonb({"text": BODY}),
                    datetime(2026, 10, 17, tzinfo=UTC),
                ),
            )
    runtime = LangGraphRuntime(repo)
    for epoch in (0, 1):
        config = {"configurable": {"thread_id": run["id"] + ":e" + str(epoch), "checkpoint_ns": ""}}
        checkpoint = {
            "v": 1,
            "id": owner + "-checkpoint-" + str(epoch),
            "ts": "2026-10-17T00:00:00+00:00",
            "channel_values": {"private": BODY},
            "channel_versions": {"private": "1"},
            "versions_seen": {},
        }
        saved = runtime.checkpointer.put(config, checkpoint, {}, {"private": "1"})
        runtime.checkpointer.put_writes(saved, [("synthetic-write", BODY)], "synthetic-task")
    return source, fact, run


def complete_state(repo, *, owner=None, run_id=None):
    hashes = {}
    with repo.transaction() as connection:
        tables = connection.execute(
            "SELECT n.nspname,c.relname,c.relkind,ARRAY(SELECT attname FROM pg_attribute "
            "WHERE attrelid=c.oid AND attnum>0 AND NOT attisdropped) AS columns "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE "
            "(n.nspname='mingjing_core' OR n.nspname='public' AND c.relname=ANY(%s)) "
            "AND c.relkind IN ('r','S') ORDER BY n.nspname,c.relname",
            (list(CHECKPOINTS),),
        ).fetchall()
        for row in tables:
            where, arguments = sql.SQL(""), []
            if owner:
                column = "owner" if "owner" in row["columns"] else "id" if row["relname"] == "core_owners" else None
                if row["nspname"] == "public" and "thread_id" in row["columns"]:
                    where, arguments = sql.SQL(" WHERE thread_id=ANY(%s)"), [[run_id + ":e0", run_id + ":e1"]]
                elif column:
                    where, arguments = sql.SQL(" WHERE {}=%s").format(sql.Identifier(column)), [owner]
                elif row["relname"] != "checkpoint_migrations":
                    continue
            if row["relkind"] == "S":
                value = connection.execute(
                    sql.SQL(
                        "SELECT encode(sha256(convert_to(jsonb_build_array(last_value,log_cnt,is_called)::text,"
                        "'UTF8')),'hex') AS value FROM {}"
                    ).format(sql.Identifier(row["nspname"], row["relname"]))
                ).fetchone()["value"]
                hashes[row["nspname"] + "." + row["relname"]] = value
                continue
            value = connection.execute(
                sql.SQL(
                    "SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(t) "
                    "ORDER BY to_jsonb(t)::text),'[]'::jsonb)::text,'UTF8')),'hex') AS value FROM {} t{}"
                ).format(sql.Identifier(row["nspname"], row["relname"]), where),
                arguments,
            ).fetchone()["value"]
            hashes[row["nspname"] + "." + row["relname"]] = value
    return hashes


def related_rows(repo, run_id):
    with repo.transaction() as connection:
        run = connection.execute("SELECT * FROM mingjing_core.core_runs WHERE id=%s", (run_id,)).fetchone()
        outbox = connection.execute(
            "SELECT * FROM mingjing_core.delivery_outbox WHERE run_id=%s ORDER BY id", (run_id,)
        ).fetchall()
    return {"run": run, **{row["id"]: row for row in outbox}}


def assert_erased(repo, source, fact, run):
    memory = MemoryService(repo)
    assert memory.get_source("alice", source["id"])["content"] == ""
    assert repo.get("alice", "fact", fact["id"], include_deleted=True)["status"] == "deleted"
    with pytest.raises(EvidenceError):
        memory.receive("alice", content=TEXT, source_id="synthetic-source", channel="synthetic")
    with pytest.raises(LeaseConflict):
        repo.claim_run("alice", run["id"])
    with repo.transaction() as connection:
        row = connection.execute("SELECT * FROM mingjing_core.core_runs WHERE id=%s", (run["id"],)).fetchone()
        assert row["status"] == "revoked" and row["request"] == {} and row["result"] is None and row["checkpoint"] == {}
        for table in CHECKPOINTS[:3]:
            assert (
                connection.execute(
                    sql.SQL("SELECT count(*) AS n FROM public.{} WHERE thread_id=ANY(%s)").format(
                        sql.Identifier(table)
                    ),
                    ([run["id"] + ":e0", run["id"] + ":e1"],),
                ).fetchone()["n"]
                == 0
            )
        rows = connection.execute(
            "SELECT status,receipt,payload FROM mingjing_core.delivery_outbox WHERE owner='alice' ORDER BY id"
        ).fetchall()
        assert [(row["status"], row["payload"]) for row in rows] == [("sent", {}), ("uncertain", {})]
        assert rows[0]["receipt"] == "om_synthetic_sent"
    for suffix, error in (("sent", LeaseConflict), ("uncertain", DeliveryUncertain)):
        with pytest.raises(error):
            OutboxService(repo).claim_delivery(owner="alice", outbox_id="alice-" + suffix)


@pytest.mark.parametrize("sample", [7], indirect=True)
def test_native_nonempty_privacy_replay_second_apply_keeps_full_state_and_other_owner(sample):
    source_repo = PostgresRepository(sample.source, initialize=False, max_size=1)
    try:
        source, fact, run = seed_owner(source_repo, "alice")
        _, _, bob_run = seed_owner(source_repo, "bob")
        sample.dump()
        MemoryService(source_repo).retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
        with source_repo.transaction("alice") as connection:
            connection.execute(
                "UPDATE mingjing_core.delivery_outbox SET status='sent',receipt='om_synthetic_sent',attempts=1 "
                "WHERE id='alice-sent'"
            )
            connection.execute(
                "UPDATE mingjing_core.delivery_outbox SET status='sending',attempts=1 WHERE id='alice-uncertain'"
            )
        latest = export_withdrawals(source_repo)
        assert any(ledger["revocations"] for ledger in latest["owners"]), "NONEMPTY_NATIVE_REVOCATIONS_REQUIRED"
        assert BODY not in json.dumps(latest), "LEDGER_BODY_LEAK"
    finally:
        source_repo.close()
    execute(sample.inputs, apply_local=True, upgrade_local=True, environment=sample.environment)
    repo = PostgresRepository(sample.environment["FIRST_RELEASE_OWNER_DSN"], initialize=False, max_size=1)
    try:
        bob_before = complete_state(repo, owner="bob", run_id=bob_run["id"])
        apply_withdrawals(repo, latest)  # No outer transaction: native checkpoint cleanup follows its actual commit.
        first_export = export_withdrawals(repo)
        assert first_export == latest, "LATEST_WITHDRAWALS_NOT_PRESERVED"
        assert_erased(repo, source, fact, run)
        before, rows_before = complete_state(repo), related_rows(repo, run["id"])
        apply_withdrawals(repo, latest)
        after, rows_after = complete_state(repo), related_rows(repo, run["id"])
        assert_erased(repo, source, fact, run)
        assert export_withdrawals(repo) == first_export, "SECOND_EXPORT_CHANGED"
        assert complete_state(repo, owner="bob", run_id=bob_run["id"]) == bob_before, "OTHER_OWNER_CHANGED"
        changed = sorted(name for name in before if before[name] != after[name])
        columns = {
            name: sorted(key for key in row if row[key] != rows_after[name][key]) for name, row in rows_before.items()
        }
        if changed or any(columns.values()):
            raise AssertionError(
                "REPLAY_SECOND_STATE_CHANGED:" + json.dumps({"tables": changed, "columns": columns}, sort_keys=True)
            )
    finally:
        repo.close()
