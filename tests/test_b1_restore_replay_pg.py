"""Real candidate-b9 PG recovery on a dedicated local restore DB; not Linux evidence."""

from __future__ import annotations

import json
import os

import psycopg
import pytest
from psycopg import sql
from test_b1_restore_replay_support import ReplayDatabase, b1_restore_dsn, replay_db

from tools.b1_restore_replay import main, run_candidate
from tools.b1_restore_replay_contracts import (
    DSN_ENV,
    MIGRATIONS,
    ReplayRejected,
    load_document,
    verify_candidate,
)

__all__ = ["b1_restore_dsn", "replay_db"]

SEED = """import uuid
from psycopg import sql
from psycopg.types.json import Jsonb
from datetime import datetime,timezone
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.application.memory import MemoryService
from mingjing_core.adapters.tarot import TarotService
from mingjing_core.runtime import LangGraphRuntime
repo=PostgresRepository(os.environ['B1_FIXTURE_DSN'],schema=value['schema'],initialize=False)
repo.ensure_owner('primary');repo.ensure_owner('secondary')
memory=MemoryService(repo)
source=memory.receive('primary',content='我喜欢合成安静书房',source_id='b1-synthetic-source',
                      at=datetime(2026,10,17,2,0,tzinfo=timezone.utc))
fact=memory.save_fact('primary','self',source['id'],source['content'])
case=memory.create_case('primary','self','合成 B7 牌阵事项',operation_id='b1-synthetic-case')
draw=TarotService(repo).create_draw('primary',subject_id='self',case_id=case['id'],question='合成 B7 问题',
                                  idempotency_key='b1-synthetic-draw')['draw']
run=repo.begin_run('primary','b1-synthetic-run',{'source_message_id':source['id']},depth='fast')
repo.fail_run('primary',run['id'],'SYNTHETIC_FAILED',run['lease_token'])
with repo.transaction('primary') as connection:
 for ident in ('b1-sent','b1-uncertain'):
  connection.execute(sql.SQL(\"INSERT INTO {}(id,owner,subject,business_id,channel,target,run_id,payload,\"
                             \"dependencies,status,attempts,due) VALUES(%s,'primary','self',%s,'feishu',\"
                             \"'ou_synthetic',%s,%s,'{{}}','pending',0,%s)\").format(repo.table('delivery_outbox')),
                     (ident,ident,run['id'],Jsonb({'text':'SYNTHETIC_PRIVATE_OLD_BODY'}),
                      datetime(2026,10,17,2,0,tzinfo=timezone.utc)))
runtime=LangGraphRuntime(repo)
config={'configurable':{'thread_id':run['id']+':e0','checkpoint_ns':''}}
checkpoint={'v':1,'id':str(uuid.uuid4()),'ts':'2026-10-17T02:00:00+00:00',
            'channel_values':{'private':'SYNTHETIC_PRIVATE_OLD_BODY'},
            'channel_versions':{'private':'1'},'versions_seen':{}}
runtime.checkpointer.put(config,checkpoint,{}, {'private':'1'})
repo.close()
print(json.dumps({'source':source['id'],'fact':fact['id'],'fact_revision':fact['revision'],
                  'run':run['id'],'draw':draw['id']}))
"""


def initialize(database: ReplayDatabase, version: int = 7) -> None:
    with psycopg.connect(database.dsn) as connection:
        connection.execute(
            sql.SQL("CREATE SCHEMA {} AUTHORIZATION current_user").format(sql.Identifier(database.schema))
        )
        connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(database.schema)))
        connection.execute(
            "CREATE TABLE schema_migrations(version integer PRIMARY KEY,checksum text,"
            "applied_at timestamptz NOT NULL DEFAULT now())"
        )
        files = sorted((database.source / "mingjing_core/repositories/migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
        for path in files[:version]:
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)",
                (int(path.name[:4]), MIGRATIONS[str(int(path.name[:4]))]),
            )


def latest(database: ReplayDatabase, seed: dict[str, str]) -> dict:
    return database.script(
        """from psycopg import sql
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.application.memory import MemoryService
from mingjing_core.adapters.tarot import TarotService
from tools.deploy_core import export_withdrawals
repo=PostgresRepository(os.environ['B1_FIXTURE_DSN'],schema=value['schema'])
MemoryService(repo).retire_fact('primary',value['fact'],expected_revision=value['fact_revision'],scope='source')
TarotService(repo).delete('primary',value['draw'])
with repo.transaction('primary') as connection:
 connection.execute(sql.SQL(\"UPDATE {} SET status='sent',receipt='om_synthetic_sent',attempts=1 WHERE id='b1-sent'\")
                    .format(repo.table('delivery_outbox')))
 connection.execute(sql.SQL(\"UPDATE {} SET status='sending',attempts=1 WHERE id='b1-uncertain'\")
                    .format(repo.table('delivery_outbox')))
document=export_withdrawals(repo);repo.close();print(json.dumps(document,default=str))
""",
        **seed,
    )


def empty_ledger() -> dict:
    return {
        "schema": "core3-withdrawals-v2",
        "owners": [
            {"schema_version": "core3.0", "owner_user_id": owner, "revocations": []}
            for owner in ("primary", "secondary")
        ],
        "tarot_requests": [],
        "deleted_draws": [],
        "delivery_receipts": [],
    }


def test_schema4_dump_restore_forward7_replays_latest_without_resurrecting_or_sending(
    replay_db: ReplayDatabase,
) -> None:
    database = replay_db
    initialize(database, 4)
    seed = database.script(SEED)
    archive = database.directory / "schema4.dump"
    database.pg(
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--schema=" + database.schema,
        "--file=" + str(archive),
    )
    document = latest(database, seed)
    assert "SYNTHETIC_PRIVATE_OLD_BODY" not in json.dumps(document)
    with psycopg.connect(database.dsn) as connection:
        connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(database.schema)))
    database.pg(
        "pg_restore",
        "--exit-on-error",
        "--single-transaction",
        "--no-owner",
        "--no-acl",
        "--dbname=" + database.dsn,
        str(archive),
    )
    database.script("""from mingjing_core.repositories.postgres import PostgresRepository
repo=PostgresRepository(os.environ['B1_FIXTURE_DSN'],schema=value['schema'])
print(json.dumps(repo.verify_schema()));repo.close()
""")
    with psycopg.connect(database.dsn) as connection:
        assert connection.execute(
            "SELECT count(*) FROM checkpoints WHERE thread_id=%s", (seed["run"] + ":e0",)
        ).fetchone()[0]
    request = database.request(document)
    request.validate()
    verify_candidate(request.candidate_source)
    first = run_candidate(request, load_document(request))
    second = run_candidate(request, load_document(request))
    assert first["changed"] and not second["changed"]
    assert second["state_after_sha256"] == first["state_after_sha256"]
    assert first["checksums"] == MIGRATIONS and first["model_calls"] == first["external_sends"] == 0
    assert_replayed_privacy_and_delivery(database, seed)


def assert_replayed_privacy_and_delivery(database: ReplayDatabase, seed: dict) -> None:
    check = database.script(
        """from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.application.memory import MemoryService
from mingjing_core.adapters.tarot import TarotService,IdempotencyConflict
from mingjing_core.adapters.delivery import OutboxService,DeliveryUncertain
from mingjing_core.domain.contracts import EvidenceError,LeaseConflict
repo=PostgresRepository(os.environ['B1_FIXTURE_DSN'],schema=value['schema'],initialize=False)
memory=MemoryService(repo);outbox=OutboxService(repo)
assert not memory.facts('primary')
assert not TarotService(repo).list_draws('primary')
try:TarotService(repo).request_result('primary','create','b1-synthetic-draw')
except IdempotencyConflict:pass
else:raise AssertionError('deleted draw request resurrected')
try:memory.receive('primary',content='我喜欢合成安静书房',source_id='b1-synthetic-source')
except EvidenceError:pass
else:raise AssertionError('withdrawn source resurrected')
for ident,error in [('b1-sent',LeaseConflict),('b1-uncertain',DeliveryUncertain)]:
 try:outbox.claim_delivery(owner='primary',outbox_id=ident)
 except error:pass
 else:raise AssertionError('protected delivery could resend')
print(json.dumps({'revoked':repo.fetch_run('primary',value['run'])['status']=='revoked'}));repo.close()
""",
        **seed,
    )
    assert check["revoked"]
    with psycopg.connect(database.dsn) as connection:
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            assert (
                connection.execute(
                    sql.SQL("SELECT count(*) FROM {} WHERE thread_id=%s").format(sql.Identifier(table)),
                    (seed["run"] + ":e0",),
                ).fetchone()[0]
                == 0
            )


@pytest.mark.parametrize("failure", ["queued", "checksum", "other_session", "missing_owner"])
def test_real_pg_preflight_refuses_unsafe_restore(replay_db: ReplayDatabase, failure: str) -> None:
    database = replay_db
    initialize(database)
    seed = database.script(SEED)
    document = empty_ledger()
    if failure == "missing_owner":
        document["owners"].pop()
    with psycopg.connect(database.dsn) as connection:
        if failure == "queued":
            connection.execute(
                sql.SQL("UPDATE {} SET status='queued' WHERE id=%s").format(
                    sql.Identifier(database.schema, "core_runs")
                ),
                (seed["run"],),
            )
        if failure == "checksum":
            connection.execute(
                sql.SQL("UPDATE {} SET checksum=%s WHERE version=7").format(
                    sql.Identifier(database.schema, "schema_migrations")
                ),
                ("0" * 64,),
            )
    hold = psycopg.connect(database.dsn) if failure == "other_session" else None
    try:
        request = database.request(document)
        expected = {
            "queued": "RESTORE_NOT_QUIESCENT",
            "checksum": "RESTORE_SCHEMA7_CHECKSUMS",
            "other_session": "OTHER_RESTORE_SESSIONS",
            "missing_owner": "COMPLETE_OWNER_LEDGER_REQUIRED",
        }
        with pytest.raises(ReplayRejected, match=expected[failure]):
            run_candidate(request, document)
    finally:
        if hold:
            hold.close()
    assert os.environ.get(DSN_ENV) == database.dsn


def test_cli_default_never_connects_and_apply_writes_new_receipt(
    replay_db: ReplayDatabase, capsys: pytest.CaptureFixture
) -> None:
    database = replay_db
    initialize(database)
    database.script(SEED)
    request = database.request(empty_ledger())
    arguments = [
        "--operation-id",
        request.operation_id,
        "--scope",
        "stage",
        "--database",
        request.database,
        "--schema",
        request.schema,
        "--candidate-source",
        str(request.candidate_source),
        "--candidate-python",
        str(request.candidate_python),
        "--ledger",
        str(request.ledger),
        "--ledger-sha256",
        request.ledger_sha256,
        "--local-drill",
    ]
    assert main(arguments) == 0
    assert json.loads(capsys.readouterr().out)["database_connections"] == 0
    output = database.directory / "receipt.json"
    assert main(arguments + ["--quiesced", "--apply", "--output", str(output)]) == 0
    assert json.loads(output.read_text())["database"] == request.database
    assert main(arguments + ["--quiesced", "--apply", "--output", str(output)]) == 2
    assert "NEW_RECEIPT_REQUIRED" in capsys.readouterr().err


@pytest.mark.parametrize("incoming", ["uncertain", "sent"])
def test_sent_is_monotonic_and_conflicting_receipt_rolls_back_every_owner(
    replay_db: ReplayDatabase,
    incoming: str,
) -> None:
    database = replay_db
    initialize(database)
    seed = database.script(SEED)
    document = empty_ledger()
    document["owners"][0]["revocations"] = [
        {
            "kind": "fact",
            "entity_id": seed["fact"],
            "operation": "deleted",
            "metadata": {},
        }
    ]
    document["delivery_receipts"] = [
        {
            "id": "b1-sent",
            "owner": "primary",
            "subject": "self",
            "business_id": "b1-sent",
            "channel": "feishu",
            "target": "ou_synthetic",
            "run_id": seed["run"],
            "status": incoming,
            "attempts": 2,
            "due": "2026-10-17T02:00:00+00:00",
            "receipt": "om_latest" if incoming == "sent" else "",
        }
    ]
    with psycopg.connect(database.dsn) as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET status='sent',receipt='om_before',attempts=1 WHERE id='b1-sent'").format(
                sql.Identifier(database.schema, "delivery_outbox")
            )
        )
    request = database.request(document)
    if incoming == "sent":
        with pytest.raises(ReplayRejected, match="CANDIDATE_BUSINESS_REPLAY_FAILED"):
            run_candidate(request, document)
    else:
        assert run_candidate(request, document)["changed"]
    with psycopg.connect(database.dsn) as connection:
        row = connection.execute(
            sql.SQL("SELECT status,receipt FROM {} WHERE id='b1-sent'").format(
                sql.Identifier(database.schema, "delivery_outbox")
            )
        ).fetchone()
        fact = connection.execute(
            sql.SQL("SELECT status FROM {} WHERE kind='fact' AND id=%s").format(
                sql.Identifier(database.schema, "core_entities")
            ),
            (seed["fact"],),
        ).fetchone()
    assert row == ("sent", "om_before")
    assert fact[0] == ("active" if incoming == "sent" else "deleted")
