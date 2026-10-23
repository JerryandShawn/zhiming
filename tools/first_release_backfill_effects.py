"""Local business-effects checks only; callers retain source and candidate authority."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from psycopg import sql

from tools.first_release_backfill_expected import WRITES, BackfillBindings, ExpectedBackfill, expected_backfill, require

CHECKPOINTS = ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations")
SPECIAL = ("core_entities", "core_owners", "core_operations")
COUNTS = frozenset(
    {
        "message_metadata",
        "search_tokens",
        "invalid_time",
        "assistant_created",
        "assistant_existing",
        "assistant_skipped",
    }
)


@dataclass(frozen=True)
class BackfillState:
    hashes: dict[str, str] = field(repr=False)
    sequences: dict[str, dict] = field(repr=False)
    catalog: list[dict] = field(repr=False)
    columns: dict[str, list[dict]] = field(repr=False)
    rows: dict[str, list[dict]] = field(repr=False)


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str, allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def observe_state(connection: Any, schema: str) -> BackfillState:
    connection.execute("SET LOCAL TimeZone='UTC'")
    connection.execute("SET LOCAL search_path=pg_catalog")
    catalog = connection.execute(
        "SELECT n.nspname,c.relname,c.relkind,c.oid FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
        "WHERE (n.nspname=%s OR n.nspname='public' AND c.relname=ANY(%s)) "
        "AND c.relkind IN ('r','p','S','v','m','f') ORDER BY n.nspname,c.relname",
        (schema, list(CHECKPOINTS)),
    ).fetchall()
    hashes, sequences, columns, rows = {}, {}, {}, {}
    for relation in catalog:
        name = relation["nspname"] + "." + relation["relname"]
        table = sql.Identifier(relation["nspname"], relation["relname"])
        require(relation["relkind"] in {"r", "S"}, "BACKFILL_RELATION_KIND_CHANGED")
        if relation["relkind"] == "S":
            sequences[name] = dict(
                connection.execute(sql.SQL("SELECT last_value,log_cnt,is_called FROM {}").format(table)).fetchone()
            )
            continue
        columns[name] = connection.execute(
            "SELECT a.attname AS name,format_type(a.atttypid,a.atttypmod) AS type,a.attnotnull AS not_null,"
            "a.attgenerated AS generated,a.attidentity AS identity,"
            "pg_get_expr(d.adbin,d.adrelid) AS default_expression "
            "FROM pg_catalog.pg_attribute a LEFT JOIN pg_catalog.pg_attrdef d "
            "ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
            "WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum",
            (relation["oid"],),
        ).fetchall()
        hashes[name] = connection.execute(
            sql.SQL(
                "SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(t) ORDER BY "
                "to_jsonb(t)::text COLLATE \"C\"),'[]'::jsonb)::text,'UTF8')),'hex') AS value FROM {} t"
            ).format(table)
        ).fetchone()["value"]
        if relation["nspname"] == schema and relation["relname"] in (*SPECIAL, "core_runs"):
            rows[relation["relname"]] = [
                dict(row)
                for row in connection.execute(
                    sql.SQL('SELECT * FROM {} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(table)
                )
            ]
    require(set(rows) == {*SPECIAL, "core_runs"}, "BACKFILL_CORE_RELATIONS_MISSING")
    return BackfillState(hashes, sequences, catalog, columns, rows)


def checked_counts(value: Any, mode: str, wanted: dict[str, Any]) -> dict[str, int]:
    require(type(value) is dict and set(value) == COUNTS | {"mode", "sample_ids"}, "BACKFILL_COUNTS_INVALID")
    require(value["mode"] == mode, "BACKFILL_COUNTS_INVALID")
    require(all(type(value[key]) is int and 0 <= value[key] < 2**63 for key in COUNTS), "BACKFILL_COUNTS_INVALID")
    require(
        isinstance(value["sample_ids"], list)
        and len(value["sample_ids"]) <= 5
        and all(isinstance(ident, str) and 1 <= len(ident) <= 200 for ident in value["sample_ids"]),
        "BACKFILL_COUNTS_INVALID",
    )
    require({key: value[key] for key in wanted} == wanted, "BACKFILL_NATIVE_COUNTS_DIFFER")
    return {key: value[key] for key in sorted(COUNTS)}


def keyed(rows: list[dict], keys: tuple[str, ...]) -> dict[tuple, dict]:
    result = {tuple(row[key] for key in keys): row for row in rows}
    require(len(result) == len(rows), "BACKFILL_ROW_IDENTITY_INVALID")
    return result


def generated_search(connection: Any, data: dict) -> Any:
    return connection.execute(
        "SELECT pg_catalog.to_tsvector('pg_catalog.simple'::regconfig,%s) AS value", (data.get("search_tokens", ""),)
    ).fetchone()["value"]


def expected_entities(
    connection: Any, before: BackfillState, expected: ExpectedBackfill, stamp: Any
) -> dict[tuple, dict]:
    rows = deepcopy(keyed(before.rows["core_entities"], ("owner", "kind", "id")))
    for identity, changes in expected.metadata.items():
        row = rows[identity]
        row["data"] = dict(row["data"], **changes)
        row["search"] = generated_search(connection, row["data"])
    for reply in expected.replies:
        key = (expected.owner, "message", reply.identifier)
        require(key not in rows, "BACKFILL_NEW_ASSISTANT_EXISTS")
        rows[key] = dict(
            owner=expected.owner,
            kind="message",
            id=reply.identifier,
            subject=reply.subject,
            case_id=None,
            revision=1,
            status="active",
            data=reply.payload,
            created_at=stamp,
            updated_at=stamp,
            search=generated_search(connection, reply.payload),
        )
    return rows


def expected_operations(before: BackfillState, expected: ExpectedBackfill, stamp: Any) -> dict:
    rows = deepcopy(keyed(before.rows["core_operations"], ("owner", "operation_id")))
    for reply in expected.replies:
        key = (expected.owner, reply.operation)
        require(key not in rows, "BACKFILL_NEW_OPERATION_EXISTS")
        rows[key] = dict(
            owner=expected.owner,
            operation_id=reply.operation,
            fingerprint=reply.operation_fingerprint,
            kind="message",
            result_id=reply.identifier,
            created_at=stamp,
        )
    return rows


def verify_first(
    connection: Any,
    schema: str,
    before: BackfillState,
    after: BackfillState,
    expected: ExpectedBackfill,
    stamp: Any,
) -> None:
    require(before.catalog == after.catalog and before.columns == after.columns, "BACKFILL_SCHEMA_CHANGED")
    require(before.sequences == after.sequences, "BACKFILL_SEQUENCE_CHANGED")
    mutable = {schema + "." + name for name in SPECIAL}
    require(
        {key: value for key, value in before.hashes.items() if key not in mutable}
        == {key: value for key, value in after.hashes.items() if key not in mutable},
        "BACKFILL_UNRELATED_STATE_CHANGED",
    )
    require(
        keyed(after.rows["core_entities"], ("owner", "kind", "id"))
        == expected_entities(connection, before, expected, stamp),
        "BACKFILL_ENTITY_VALUES_DIFFER",
    )
    require(
        keyed(after.rows["core_operations"], ("owner", "operation_id")) == expected_operations(before, expected, stamp),
        "BACKFILL_OPERATION_VALUES_DIFFER",
    )
    owners = deepcopy(keyed(before.rows["core_owners"], ("id",)))
    require((expected.owner,) in owners, "BACKFILL_OWNER_MISSING")
    owners[(expected.owner,)]["revision"] += len(expected.replies)
    require(keyed(after.rows["core_owners"], ("id",)) == owners, "BACKFILL_OWNER_VALUES_DIFFER")


def verify_backfill_effects(repo: Any, owner: str, *, bindings: BackfillBindings) -> dict[str, Any]:
    """No source witness, candidate-origin, fresh-process, or publication claim is made."""
    with repo.transaction(owner) as connection:
        connection.execute("SET LOCAL search_path=pg_catalog")
        repo.assert_scope(owner)
        stamp = connection.execute("SELECT transaction_timestamp() AS value").fetchone()["value"]
        before = observe_state(connection, repo.schema)
        expected = expected_backfill(repo, owner, before.rows, bindings)
        require(observe_state(connection, repo.schema) == before, "BACKFILL_PROJECTION_WROTE_STATE")
        memory = bindings.memory_factory(repo)
        preview = checked_counts(bindings.module.backfill(memory, owner, apply=False), "dry-run", expected.counts)
        require(observe_state(connection, repo.schema) == before, "BACKFILL_PREVIEW_WROTE_STATE")
        first = checked_counts(bindings.module.backfill(memory, owner, apply=True), "apply", expected.counts)
        after = observe_state(connection, repo.schema)
        verify_first(connection, repo.schema, before, after, expected, stamp)
        repeat_wanted = dict(expected.counts, **{key: 0 for key in WRITES}, sample_ids=[])
        repeat_wanted["assistant_existing"] += len(expected.replies)
        second = checked_counts(bindings.module.backfill(memory, owner, apply=True), "apply", repeat_wanted)
        require(observe_state(connection, repo.schema) == after, "BACKFILL_SECOND_STATE_CHANGED")
        return dict(
            scope="local native business-effects component only",
            before_sha256=digest(dict(tables=before.hashes, sequences=before.sequences, columns=before.columns)),
            after_sha256=digest(dict(tables=after.hashes, sequences=after.sequences, columns=after.columns)),
            preview=preview,
            first=first,
            second=second,
            sample_id_sha256=[digest(ident) for ident in expected.counts["sample_ids"]],
            assistant_id_sha256=[digest(reply.identifier) for reply in expected.replies[:5]],
            all_assistant_ids_sha256=digest([reply.identifier for reply in expected.replies]),
            metadata_values_verified=True,
            generated_search_verified=True,
            new_assistants_verified=len(expected.replies),
            candidate_origin_verified=False,
            source_admission_verified=False,
            formal_release_verified=False,
        )
