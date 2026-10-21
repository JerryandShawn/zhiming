"""Real nonempty deletion ledger recovery; no synthetic receipt insertion or proof rewrite."""

from __future__ import annotations

import ast
import json
import os
import subprocess
from dataclasses import replace

import psycopg
import pytest
from b1_restore_proof_support import ROOT, Fixture, backup, initialize4, proof_db, write

from tools.b1_restore_proof import generate
from tools.b1_restore_proof_contracts import verify_monotone
from tools.b1_restore_proof_process import python_prefix
from tools.b1_restore_replay_contracts import ReplayRejected, file_hash

__all__ = ["proof_db"]


def script(value: Fixture, body: str, *, target=False, **fields):
    env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    env.update(
        B1_FIXTURE_DSN=value.owner_dsn if target else value.source_dsn,
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        CORE_FEISHU_ENABLED="false",
    )
    code = (
        f"import sys,os,json\nsys.path.insert(0,{str(value.request.candidate_source)!r})\n"
        "value=json.load(sys.stdin)\n" + body
    )
    result = subprocess.run(
        [*python_prefix(value.request.candidate_python), "-c", code],
        input=json.dumps(fields),
        env=env,
        capture_output=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, "fixed synthetic business probe failed"
    return json.loads(result.stdout)


def prepare_nonempty(value: Fixture):
    initialize4(value)
    tree = ast.parse((ROOT / "tests/test_b1_restore_replay_pg.py").read_text(encoding="utf-8"))
    seed = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(name, ast.Name) and name.id == "SEED" for name in node.targets)
    )
    ids = script(value, seed, schema="mingjing_core")
    backup(value)
    document = script(
        value,
        """from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.application.memory import MemoryService
from mingjing_core.adapters.tarot import TarotService
from tools.deploy_core import export_withdrawals
repo=PostgresRepository(os.environ['B1_FIXTURE_DSN'],initialize=False)
repo.initialize()
MemoryService(repo).retire_fact('primary',value['fact'],expected_revision=value['fact_revision'],scope='source')
repo.mutation_request('primary','tarot-delete:'+value['draw'],'b1-nonempty-delete',{},
 lambda:dict(TarotService(repo).delete('primary',value['draw']),kind='draw'))
with repo.transaction('primary') as conn:
 conn.execute("UPDATE mingjing_core.delivery_outbox SET status='sent',receipt='om_synthetic_sent',"
              "attempts=1 WHERE id='b1-sent'")
 conn.execute("UPDATE mingjing_core.delivery_outbox SET status='sending',attempts=1 WHERE id='b1-uncertain'")
print(json.dumps(export_withdrawals(repo),default=str));repo.close()
""",
        **ids,
    )
    assert document["deleted_draws"] == [{"owner": "primary", "draw_id": ids["draw"]}]
    write(value.request.ledger, document)
    value.request = replace(value.request, ledger_sha256=file_hash(value.request.ledger))
    return ids, document


def inspect_target(value: Fixture, ids, document):
    with psycopg.connect(value.owner_dsn) as conn:
        rows = conn.execute(
            "SELECT status,data FROM mingjing_core.core_entities WHERE id=ANY(%s)", ([ids["source"], ids["fact"]],)
        ).fetchall()
        observed = {
            "entities_erased": len(rows) == 2 and all(row == ("deleted", {}) for row in rows),
            "draws": conn.execute("SELECT count(*) FROM mingjing_core.tarot_draws").fetchone()[0],
            "checkpoint": conn.execute(
                "SELECT count(*) FROM public.checkpoints WHERE thread_id=%s", (ids["run"] + ":e0",)
            ).fetchone()[0],
            "versions": [
                row[0] for row in conn.execute("SELECT version FROM mingjing_core.schema_migrations ORDER BY version")
            ],
            "mutation_receipts": conn.execute(
                "SELECT count(*) FROM mingjing_core.core_mutation_requests WHERE operation LIKE 'tarot-delete:%%'"
            ).fetchone()[0],
        }
    exported = script(
        value,
        """from mingjing_core.repositories.postgres import PostgresRepository
from tools.deploy_core import export_withdrawals
repo=PostgresRepository(os.environ['B1_FIXTURE_DSN'],initialize=False)
print(json.dumps(export_withdrawals(repo),default=str));repo.close()
""",
        target=True,
    )
    observed.update(
        latest_deleted_draws=len(document["deleted_draws"]), exported_deleted_draws=len(exported["deleted_draws"])
    )
    with pytest.raises(ReplayRejected) as blocked:
        verify_monotone(document, exported)
    observed["roundtrip_code"] = str(blocked.value)
    return observed


def test_nonempty_deleted_draws_is_a_real_roundtrip_blocker_after_physical_erasure(proof_db):
    ids, document = prepare_nonempty(proof_db)
    with pytest.raises(ReplayRejected, match="^PINNED_REPLAY_FAILED$"):
        generate(proof_db.request)
    observed = inspect_target(proof_db, ids, document)
    assert observed == {
        "checkpoint": 0,
        "draws": 0,
        "entities_erased": True,
        "exported_deleted_draws": 0,
        "latest_deleted_draws": 1,
        "mutation_receipts": 0,
        "versions": list(range(1, 8)),
        "roundtrip_code": "STALE_WITHDRAWALS",
    }
    print(json.dumps(observed, sort_keys=True))
