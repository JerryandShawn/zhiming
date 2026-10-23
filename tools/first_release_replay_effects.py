"""Reviewed local orchestration; all business effects come from verified candidate callables."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from psycopg import sql
from psycopg.conninfo import make_conninfo

CHECKPOINTS = ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations")
CENTRAL = ("core_model_accounts", "core_model_batches", "core_model_authorizations", "core_model_usage")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def ledger(value: dict[str, Any], require: Any) -> dict[str, Any]:
    path = Path(value["replay"]["ledger"])
    require(path.is_file() and not any(item.is_symlink() for item in (path, *path.parents)), "REPLAY_LEDGER_CHANGED")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == value["pin"]["ledger_sha256"], "REPLAY_LEDGER_CHANGED")
    result = json.loads(raw)
    require(isinstance(result, dict), "REPLAY_LEDGER_CHANGED")
    return result


def snapshot(repo: Any) -> dict[str, str]:
    hashes = {}
    with repo.transaction() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL search_path=pg_catalog")
        tables = connection.execute(
            "SELECT n.nspname,c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE (n.nspname='mingjing_core' OR n.nspname='public' AND c.relname=ANY(%s)) "
            "AND c.relkind IN ('r','S') ORDER BY n.nspname,c.relname",
            (list(CHECKPOINTS),),
        ).fetchall()
        for row in tables:
            table = sql.Identifier(row["nspname"], row["relname"])
            expression = (
                "jsonb_build_array(last_value,log_cnt,is_called)::text"
                if row["relkind"] == "S"
                else "coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text COLLATE \"C\"),'[]'::jsonb)::text"
            )
            query = sql.SQL("SELECT encode(sha256(convert_to(" + expression + ",'UTF8')),'hex') AS value FROM {} t")
            hashes[row["nspname"] + "." + row["relname"]] = connection.execute(query.format(table)).fetchone()["value"]
    return hashes


def central(repo: Any, hashes: dict[str, str], require: Any) -> dict[str, str]:
    with repo.transaction() as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL search_path=pg_catalog")
        for table in CENTRAL:
            count = connection.execute(
                sql.SQL("SELECT count(*) AS n FROM mingjing_core.{}").format(sql.Identifier(table))
            ).fetchone()["n"]
            require(count == 0, "REPLAY_CENTRAL_CHANGED")
    names = ["mingjing_core." + name for name in CENTRAL] + ["mingjing_core.core_model_usage_id_seq"]
    require(all(name in hashes for name in names), "REPLAY_CENTRAL_CHANGED")
    return {name: hashes[name] for name in names}


def erased(repo: Any, document: dict[str, Any], require: Any) -> dict[str, int]:
    whole, draws, ranges = 0, 0, 0
    with repo.transaction() as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL search_path=pg_catalog")
        for owner in document["owners"]:
            for row in owner["revocations"]:
                if row["kind"] in {"source_span", "legacy_memory"}:
                    continue
                old = connection.execute(
                    "SELECT status,data FROM mingjing_core.core_entities WHERE owner=%s AND kind=%s AND id=%s",
                    (owner["owner_user_id"], row["kind"], row["entity_id"]),
                ).fetchone()
                require(old is None or old == {"status": "deleted", "data": {}}, "REPLAY_ERASURE_FAILED")
                whole += 1
        for row in document["deleted_draws"]:
            old = connection.execute(
                "SELECT 1 FROM mingjing_core.tarot_draws WHERE owner=%s AND id=%s", (row["owner"], row["draw_id"])
            ).fetchone()
            require(old is None, "REPLAY_ERASURE_FAILED")
            draws += 1
        runs = connection.execute(
            "SELECT id,retry_epoch,request,result,checkpoint,lease_token,lease_until FROM mingjing_core.core_runs "
            "WHERE status='revoked'"
        ).fetchall()
        for run in runs:
            require(
                run["request"] == run["checkpoint"] == {}
                and run["result"] is None
                and run["lease_token"] is run["lease_until"] is None,
                "REPLAY_ERASURE_FAILED",
            )
            for epoch in range(run["retry_epoch"] + 1):
                for table in CHECKPOINTS[:3]:
                    old = connection.execute(
                        sql.SQL("SELECT 1 FROM public.{} WHERE thread_id=%s LIMIT 1").format(sql.Identifier(table)),
                        (run["id"] + ":e" + str(epoch),),
                    ).fetchone()
                    require(old is None, "REPLAY_CHECKPOINT_SURVIVED")
                    ranges += 1
    return {"whole_revocations_checked": whole, "deleted_draws_checked": draws, "checkpoint_ranges_checked": ranges}


def native(function: Any, code: str, require: Any, *arguments: Any) -> Any:
    try:
        return function(*arguments)
    except Exception:
        require(False, code)


def replay(
    value: dict[str, Any], repository: Any, deployment: Any, monotone: Any, audit: Any, require: Any
) -> dict[str, Any]:
    document = ledger(value, require)
    dsn = make_conninfo(
        os.environ["FIRST_RELEASE_CANDIDATE_OWNER_DSN"],
        options="-c default_transaction_read_only=off -c search_path=pg_catalog,public",
    )
    repo = repository.PostgresRepository(dsn, initialize=False, max_size=1)
    try:
        prior = native(deployment.export_withdrawals, "REPLAY_FIRST_EXPORT_FAILED", require, repo)
        native(monotone, "REPLAY_STALE_LEDGER", require, prior, document)
        before = snapshot(repo)
        quota = central(repo, before, require)
        audit()
        first = native(deployment.apply_withdrawals, "REPLAY_FIRST_APPLY_FAILED", require, repo, document)
        audit()
        exported = native(deployment.export_withdrawals, "REPLAY_FIRST_EXPORT_FAILED", require, repo)
        native(monotone, "REPLAY_STALE_LEDGER", require, document, exported)
        checked = erased(repo, document, require)
        first_state = snapshot(repo)
        require(central(repo, first_state, require) == quota, "REPLAY_CENTRAL_CHANGED")
        require(ledger(value, require) == document, "REPLAY_LEDGER_CHANGED")
        audit()
        second = native(deployment.apply_withdrawals, "REPLAY_SECOND_APPLY_FAILED", require, repo, document)
        audit()
        repeated = native(deployment.export_withdrawals, "REPLAY_SECOND_EXPORT_FAILED", require, repo)
        erased(repo, document, require)
        second_state = snapshot(repo)
        require(central(repo, second_state, require) == quota, "REPLAY_CENTRAL_CHANGED")
        require(first_state == second_state, "REPLAY_SECOND_STATE_CHANGED")
        require(exported == repeated, "REPLAY_SECOND_EXPORT_CHANGED")
        require(ledger(value, require) == document, "REPLAY_LEDGER_CHANGED")
        audit()
        return receipt(value, before, first_state, second_state, exported, repeated, first, second, checked)
    finally:
        repo.close()


def receipt(
    value: Any,
    before: Any,
    first_state: Any,
    second_state: Any,
    exported: Any,
    repeated: Any,
    first: Any,
    second: Any,
    checked: Any,
) -> dict[str, Any]:
    return {
        "schema": "first-release-local-candidate-replay-v1",
        "effects_sha256": value["replay"]["effects_sha256"],
        "state_before_sha256": digest(before),
        "state_first_sha256": digest(first_state),
        "state_second_sha256": digest(second_state),
        "export_first_sha256": digest(exported),
        "export_second_sha256": digest(repeated),
        "first_counts": first,
        "second_counts": second,
        "checks": checked,
        "local_candidate_replay_completed": True,
        "latest_withdrawals_replayed": True,
        "second_apply_unchanged": True,
        "central_unchanged": True,
        "database_connections": 2,
        "central_binding_verified": False,
        "runtime_verified": False,
        "native_restore_completed": False,
        "linux_attestation": False,
        "publication": False,
        "model_calls": 0,
        "external_sends": 0,
    }
