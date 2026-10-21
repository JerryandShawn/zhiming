"""Explicit local-only schema4 business probe; default invocation opens no database."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import sql
from psycopg.types.json import Jsonb

from tools.b1_bootstrap_replay_fixture import (
    CASE_TITLE,
    DRAW_KEY,
    DSN_ENV,
    OPERATIONS,
    PENDING_IDS,
    PRIVATE_CHECKPOINT,
    PROFILE,
    QUESTION,
    REPLY,
    RUN_OPERATION,
    SCHEMA4,
    SOURCE_KEY,
    SOURCE_TEXT,
    SPEC,
    STAMP,
    SeedBlocked,
    SeedRequest,
    baseline,
    fingerprint,
    receipt,
    require,
    seeded,
)
from tools.b1_bootstrap_replay_observe import CORE_TABLES, identity, observe, snapshot, table_sets
from tools.b1_restore_proof_pg import state_hash
from tools.b1_restore_replay_contracts import regular, verify_candidate
from tools.core_incremental_contracts import EXPECTED_MANIFEST, TARGET


def modules(request: SeedRequest) -> dict[str, Any]:
    names = {
        "repository": "mingjing_core.repositories.postgres",
        "memory": "mingjing_core.application.memory",
        "tarot": "mingjing_core.adapters.tarot",
        "runtime": "mingjing_core.runtime",
        "tokenize": "mingjing_core.memory.tokenize",
        "deploy": "tools.deploy_core",
        "clock": "mingjing_core.timekit.clock",
    }
    result = {key: importlib.import_module(name) for key, name in names.items()}
    require(sys.version_info[:2] == (3, 11), "SEED_PYTHON311")
    for value in result.values():
        require(Path(value.__file__).resolve().is_relative_to(request.candidate_source.resolve()), "SEED_IMPORT_SOURCE")
    return result


def locked_source(conn: Any, request: SeedRequest) -> dict[str, Any]:
    identity(conn, request)
    table_sets(conn, True)
    for table in sorted(CORE_TABLES):
        conn.execute(sql.SQL("LOCK TABLE mingjing_core.{} IN SHARE ROW EXCLUSIVE MODE").format(sql.Identifier(table)))
    return snapshot(conn)


def create_business(repo: Any, values: dict[str, Any], request: SeedRequest) -> dict[str, str]:
    memory = values["memory"].MemoryService(repo)
    with repo.transaction("primary") as conn:
        baseline(locked_source(conn, request))
        source = memory.receive(
            "primary", content=SOURCE_TEXT, source_id=SOURCE_KEY, at=STAMP, operation_id=OPERATIONS["message"]
        )
        fact = memory.save_fact("primary", "self", source["id"], SOURCE_TEXT, operation_id=OPERATIONS["fact"])
        require(fact.get("write_status") == "saved", "SEED_FACT_NOT_SAVED")
        case = memory.create_case("primary", "self", CASE_TITLE, operation_id=OPERATIONS["case"])
        draw = (
            values["tarot"]
            .TarotService(repo)
            .create_draw("primary", subject_id="self", case_id=case["id"], question=QUESTION, idempotency_key=DRAW_KEY)
        )
        request = {"source_message_id": source["id"], "fact_ids": [fact["id"]], "draw_id": draw["draw"]["id"]}
        run = repo.begin_run("primary", RUN_OPERATION, request, case_ids=[case["id"]])
        versions = {"message:" + source["id"]: 1, "fact:" + fact["id"]: 1}
        conn.execute(
            "UPDATE mingjing_core.core_runs SET state_version=%s WHERE id=%s",
            (Jsonb({"versions": versions, "case_ids": [case["id"]]}), run["id"]),
        )
        repo.fail_run("primary", run["id"], "SYNTHETIC_FAILED", run["lease_token"])
        conn.execute(
            "UPDATE mingjing_core.core_runs SET request=%s,result=%s,state_version=%s "
            "WHERE id='synthetic-run' AND owner='primary'",
            (
                Jsonb({"source_message_id": "synthetic-message", "message": "synthetic original"}),
                Jsonb({"answer": REPLY}),
                Jsonb({"versions": {"message:synthetic-message": 1}}),
            ),
        )
        for ident in PENDING_IDS:
            conn.execute(
                "INSERT INTO mingjing_core.delivery_outbox(id,owner,subject,business_id,channel,target,"
                "run_id,payload,dependencies,due) VALUES(%s,'primary','self',%s,'synthetic','synthetic',"
                "%s,'{}','{}',%s)",
                (ident, ident, run["id"], STAMP),
            )
    return {
        "source": source["id"],
        "fact": fact["id"],
        "case": case["id"],
        "draw": draw["draw"]["id"],
        "run": run["id"],
    }


def checkpoint(runtime: Any, ident: str) -> None:
    config = {"configurable": {"thread_id": ident + ":e0", "checkpoint_ns": ""}}
    value = {
        "v": 1,
        "id": str(uuid.uuid4()),
        "ts": STAMP,
        "channel_values": {"private": {"synthetic": PRIVATE_CHECKPOINT}},
        "channel_versions": {"private": "1"},
        "versions_seen": {},
    }
    runtime.checkpointer.put(config, value, {}, {"private": "1"})


def seed(request: SeedRequest, values: dict[str, Any]) -> dict[str, Any]:
    before = observe(request, checkpoint=False)
    baseline(before["snapshot"])
    repo = values["repository"].PostgresRepository(request.dsn(), initialize=False, max_size=1)
    try:
        runtime = values["runtime"].LangGraphRuntime(repo)
        ids = create_business(repo, values, request)
        checkpoint(runtime, ids["run"])
        ledger = values["deploy"].export_withdrawals(repo)
    finally:
        repo.close()
    after = observe(request, checkpoint=True)
    seeded(after["snapshot"], ids, values["tokenize"].searchable_data)
    require(
        after["checkpoints"]["checkpoints"] == 1 and after["checkpoints"]["checkpoint_blobs"] > 0,
        "SEED_CHECKPOINT_MISSING",
    )
    return public_receipt(
        request,
        values,
        after,
        ids,
        {
            "before_state_sha256": before["state_sha256"],
            "backup_ledger_sha256": fingerprint(ledger),
            "protected_receipts": len(ledger["delivery_receipts"]),
        },
    )


def withdraw_business(
    repo: Any, values: dict[str, Any], ids: dict[str, str], request: SeedRequest, prior: dict[str, Any]
) -> dict[str, Any]:
    memory, tarot = values["memory"].MemoryService(repo), values["tarot"].TarotService(repo)
    with repo.transaction("primary") as conn:
        seeded(locked_source(conn, request), ids, values["tokenize"].searchable_data)
        require(state_hash(conn) == prior["state_sha256"], "SEED_PRIOR_STATE_CHANGED")
        memory.retire_fact("primary", ids["fact"], expected_revision=1, scope="source")
        result = repo.mutation_request(
            "primary",
            "tarot-delete:" + ids["draw"],
            "b1-bootstrap-delete-v1",
            {},
            lambda: dict(tarot.delete("primary", ids["draw"]), kind="draw"),
        )
        require(result.get("deleted_ids") == [ids["draw"]], "SEED_DRAW_NOT_DELETED")
        for ident, status, proof in zip(
            PENDING_IDS, ("sent", "sending"), ("synthetic-bootstrap-receipt", ""), strict=True
        ):
            conn.execute(
                "UPDATE mingjing_core.delivery_outbox SET status=%s,receipt=%s,attempts=1 "
                "WHERE id=%s AND owner='primary'",
                (status, proof, ident),
            )
    return values["deploy"].export_withdrawals(repo)


def withdraw(request: SeedRequest, values: dict[str, Any], prior: dict[str, Any]) -> dict[str, Any]:
    before = observe(request, checkpoint=True)
    ids = receipt(prior, request, before["identity"]["database"])
    require(prior["phase"] == "seed", "SEED_PRIOR_PHASE")
    seeded(before["snapshot"], ids, values["tokenize"].searchable_data)
    require(prior.get("state_sha256") == before["state_sha256"], "SEED_PRIOR_STATE_CHANGED")
    repo = values["repository"].PostgresRepository(request.dsn(), initialize=False, max_size=1)
    try:
        values["runtime"].LangGraphRuntime(repo, initialize=False)
        ledger = withdraw_business(repo, values, ids, request, prior)
    finally:
        repo.close()
    after = observe(request, checkpoint=True)
    expected = {
        "synthetic-sent": "sent",
        "synthetic-uncertain": "uncertain",
        PENDING_IDS[0]: "sent",
        PENDING_IDS[1]: "uncertain",
    }
    require({row["id"]: row["status"] for row in ledger["delivery_receipts"]} == expected, "SEED_LEDGER_RECEIPTS")
    require({row["owner_user_id"] for row in ledger["owners"]} == {"primary", "secondary"}, "SEED_LEDGER_OWNERS")
    require(
        ledger["deleted_draws"] == [{"owner": "primary", "draw_id": ids["draw"]}]
        and len(ledger["tarot_requests"]) == 1,
        "SEED_LEDGER_DRAW",
    )
    details = {
        "before_state_sha256": before["state_sha256"],
        "ledger_sha256": fingerprint(ledger),
        "receipt_statuses": expected,
        "tarot_tombstones": len(ledger["tarot_requests"]),
        "deleted_draws": len(ledger["deleted_draws"]),
        "revocations": sum(len(owner["revocations"]) for owner in ledger["owners"]),
    }
    return public_receipt(request, values, after, ids, details)


def public_receipt(
    request: SeedRequest, values: dict[str, Any], observed: dict[str, Any], ids: dict[str, str], details: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema": "b1-schema4-seed-v1",
        "operation_id": request.operation_id,
        "phase": request.phase,
        "at": values["clock"].get_clock().now().astimezone(ZoneInfo("Asia/Shanghai")).isoformat(),
        "database": observed["identity"]["database"],
        "identity": observed["identity"],
        "target": TARGET,
        "manifest_sha256": EXPECTED_MANIFEST,
        "profile": PROFILE,
        "spec_sha256": fingerprint(SPEC),
        "ids": ids,
        "checksums": SCHEMA4,
        "state_sha256": observed["state_sha256"],
        "checkpoints": observed["checkpoints"],
        "admissible": False,
        "real_linux": False,
        "models": 0,
        "sends": 0,
        "details": details,
    }


def environment(request: SeedRequest) -> dict[str, str]:
    result = {
        key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "LANG") if key in os.environ
    }
    result.update(
        {
            DSN_ENV: request.dsn(),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
            "OTEL_SDK_DISABLED": "true",
            "CORE_FEISHU_ENABLED": "false",
        }
    )
    return result


def run_worker(request: SeedRequest, prior: dict[str, Any] | None = None) -> dict[str, Any]:
    request.validate()
    verify_candidate(request.candidate_source)
    regular(request.candidate_python)
    fields = {key: str(value) if isinstance(value, Path) else value for key, value in asdict(request).items()}
    root = str(Path(__file__).resolve().parents[1])
    code = (
        f"import sys,json,pathlib\nsys.path.insert(0,{root!r})\n"
        "from tools.b1_bootstrap_replay_seed import modules,seed,withdraw,SeedRequest,SeedBlocked\n"
        "from tools.b1_restore_replay_contracts import verify_candidate\n"
        "value=json.load(sys.stdin);fields=value['request']\n"
        "for key in ('candidate_source','candidate_python'):fields[key]=pathlib.Path(fields[key])\n"
        "request=SeedRequest(**fields);sys.path.insert(0,str(request.candidate_source))\n"
        "try:\n verify_candidate(request.candidate_source);values=modules(request)\n"
        " result=seed(request,values) if request.phase=='seed' else withdraw(request,values,value['prior'])\n"
        " print(json.dumps(result,sort_keys=True))\n"
        "except SeedBlocked as error:\n print(json.dumps({'code':str(error)}),file=sys.stderr);sys.exit(2)\n"
        "except Exception as error:\n"
        " name=type(error).__name__.upper()\n"
        " allowed={'UNDEFINEDCOLUMN','UNDEFINEDTABLE','TYPEERROR','KEYERROR','VALUEERROR','ASSERTIONERROR',"
        "'ATTRIBUTEERROR','POOLTIMEOUT','RUNTIMEERROR'}\n"
        " code='SEED_PINNED_'+name if name in allowed else 'SEED_PINNED_WORKER_FAILED'\n"
        " if name=='UNDEFINEDTABLE':\n"
        "  diagnostic=getattr(getattr(error,'diag',None),'message_primary','') or ''\n"
        "  for table in ('core_embeddings','core_run_steps','core_run_events'):\n"
        "   if table in diagnostic:code+='_'+table.upper();break\n"
        " print(json.dumps({'code':code}),file=sys.stderr);sys.exit(2)\n"
    )
    result = subprocess.run(
        [str(request.candidate_python), "-I", "-B", "-X", "pycache_prefix=" + os.path.abspath(os.devnull), "-c", code],
        input=json.dumps({"request": fields, "prior": prior}),
        env=environment(request),
        capture_output=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    if result.returncode:
        try:
            failure = json.loads(result.stderr)["code"]
        except (ValueError, TypeError, KeyError):
            failure = "SEED_PINNED_WORKER_FAILED"
        raise SeedBlocked(
            failure if re.fullmatch(r"[A-Z][A-Z0-9_]{3,80}", str(failure)) else "SEED_PINNED_WORKER_FAILED"
        )
    value = json.loads(result.stdout)
    receipt(value, request, value.get("database", ""))
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--phase", choices=("seed", "withdraw"), default="seed")
    parser.add_argument("--operation-id")
    parser.add_argument("--candidate-source", type=Path)
    parser.add_argument("--candidate-python", type=Path)
    parser.add_argument("--seed-receipt", type=Path)
    args = parser.parse_args(argv)
    if not args.apply:
        print(
            json.dumps(
                {
                    "schema": "b1-schema4-seed-plan-v1",
                    "profile": PROFILE,
                    "spec_sha256": fingerprint(SPEC),
                    "database_connections": 0,
                    "admissible": False,
                    "models": 0,
                    "sends": 0,
                },
                sort_keys=True,
            )
        )
        return 0
    try:
        require(all((args.operation_id, args.candidate_source, args.candidate_python)), "SEED_ARGUMENTS")
        prior = None
        if args.phase == "withdraw":
            require(args.seed_receipt and args.seed_receipt.is_absolute(), "SEED_RECEIPT_PATH")
            regular(args.seed_receipt)
            require(args.seed_receipt.stat().st_size < 100_000, "SEED_RECEIPT_SIZE")
            prior = json.loads(args.seed_receipt.read_text(encoding="utf-8"))
        print(
            json.dumps(
                run_worker(
                    SeedRequest(args.operation_id, args.phase, args.candidate_source, args.candidate_python), prior
                ),
                sort_keys=True,
            )
        )
        return 0
    except Exception as error:
        code = str(error) if isinstance(error, SeedBlocked) else "SEED_CONTROLLER_FAILED"
        print(json.dumps({"code": code}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
