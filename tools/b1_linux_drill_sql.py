"""Pinned migration bytes and synthetic fixtures for the isolated Linux rehearsal."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from tools.b1_linux_drill_transport import DrillBlocked, require
from tools.core_incremental_contracts import MIGRATIONS, TARGET

PREFIX = "mingjing_core/repositories/migrations/"
DATABASES = (
    "zhiming_core_stage",
    "zhiming_core_b1_restore",
    "b1_drill_rollback",
    "b1_drill_ledger",
)


def git_bytes(repo: Path, revision: str, member: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "show", revision + ":" + member],
            cwd=repo,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise DrillBlocked("PINNED_GIT_SOURCE_UNAVAILABLE") from None
    require(result.returncode == 0, "PINNED_GIT_MEMBER_UNAVAILABLE")
    return result.stdout


def migrations(repo: Path) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", TARGET, PREFIX],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    require(result.returncode == 0, "PINNED_GIT_TREE_UNAVAILABLE")
    names = sorted(result.stdout.decode("utf-8").splitlines())
    require(len(names) == 7, "B1_PACKAGE_MUST_HAVE_SEVEN_MIGRATIONS")
    rows = []
    for name in names:
        source = git_bytes(repo, TARGET, name).replace(b"\r\n", b"\n")
        number = int(Path(name).name[:4])
        checksum = hashlib.sha256(source).hexdigest()
        require(
            MIGRATIONS.get(str(number)) == checksum, "PINNED_MIGRATION_HASH_MISMATCH"
        )
        rows.append(
            {"number": number, "sha256": checksum, "source": source.decode("utf-8")}
        )
    require(
        [row["number"] for row in rows] == list(range(1, 8)),
        "PINNED_MIGRATION_SEQUENCE",
    )
    return rows


def apply_sql(rows: list[dict[str, Any]]) -> str:
    pieces = [
        "BEGIN; SET LOCAL search_path TO mingjing_core;",
        "CREATE TABLE IF NOT EXISTS schema_migrations(version integer PRIMARY KEY, "
        "checksum text,applied_at timestamptz NOT NULL DEFAULT now());",
    ]
    for row in rows:
        pieces.extend(
            [
                row["source"],
                "INSERT INTO schema_migrations(version,checksum) VALUES("
                + str(row["number"])
                + ",'"
                + row["sha256"]
                + "');",
            ]
        )
    return "\n".join([*pieces, "COMMIT;"])


def fixture_sql() -> str:
    # No personal fixture data, HTTP entry point, queue item or pending send is created.
    return """
BEGIN;
INSERT INTO mingjing_core.core_owners(id) VALUES('primary'),('secondary');
INSERT INTO mingjing_core.core_subjects(owner,id,label) VALUES
  ('primary','self','synthetic'),('secondary','self','synthetic');
INSERT INTO mingjing_core.core_entities(owner,kind,id,subject,data) VALUES
  ('primary','message','synthetic-message','self',
   '{"content":"synthetic original","role":"user","at":"2026-10-17T02:30:00+00:00"}'),
  ('secondary','message','synthetic-secondary','self','{"content":"synthetic untouched"}');
INSERT INTO mingjing_core.core_runs(id,owner,subject,operation_id,fingerprint,request,status,call_limit)
  VALUES('synthetic-run','primary','self','synthetic-operation','synthetic-fingerprint','{}','succeeded',6);
INSERT INTO mingjing_core.delivery_outbox
  (id,owner,subject,business_id,channel,target,run_id,status,receipt,due,attempts) VALUES
  ('synthetic-sent','primary','self','synthetic-sent','synthetic','synthetic','synthetic-run',
   'sent','synthetic-receipt','2026-10-17T02:30:00+00:00',1),
  ('synthetic-uncertain','primary','self','synthetic-uncertain','synthetic','synthetic','synthetic-run',
   'uncertain','','2026-10-17T02:30:00+00:00',1);
COMMIT;
"""


def grants(database: str) -> str:
    require(
        database in {"zhiming_core_stage", "zhiming_core_b1_restore"},
        "GRANT_TARGET_SCOPE",
    )
    role = database + "_writer"
    return f"""
GRANT CONNECT ON DATABASE {database} TO {role};
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA mingjing_core TO {role};
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA mingjing_core TO {role};
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA mingjing_core TO {role};
REVOKE INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER ON mingjing_core.schema_migrations FROM {role};
REVOKE CREATE ON SCHEMA mingjing_core FROM {role};
"""


def schema_snapshot_sql() -> str:
    return """SELECT json_build_object(
'version',max(version),'checksums',json_object_agg(version,checksum))
FROM mingjing_core.schema_migrations;"""


def immutable_snapshot_sql() -> str:
    return """SELECT json_build_object(
'entities',encode(sha256(convert_to((SELECT jsonb_agg(to_jsonb(e)-'search' ORDER BY owner,kind,id)::text
  FROM mingjing_core.core_entities e),'UTF8')),'hex'),
'outbox',encode(sha256(convert_to((SELECT jsonb_agg(to_jsonb(o) ORDER BY id)::text
  FROM mingjing_core.delivery_outbox o),'UTF8')),'hex'),
'owners',(SELECT json_object_agg(owner,total) FROM
  (SELECT owner,count(*) total FROM mingjing_core.core_entities GROUP BY owner) owners));"""


def permission_sql() -> str:
    return """SELECT json_build_object(
'superuser',rolsuper,'createdb',rolcreatedb,'createrole',rolcreaterole,'bypassrls',rolbypassrls,
'database_create',has_database_privilege(current_user,current_database(),'CREATE'),
'schema_create',has_schema_privilege(current_user,'mingjing_core','CREATE'),
'public_create',has_schema_privilege(current_user,'public','CREATE'),
'ledger_select',has_table_privilege(current_user,'mingjing_core.schema_migrations','SELECT'),
'ledger_write',has_table_privilege(current_user,'mingjing_core.schema_migrations',
  'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER'),
'tables',(SELECT json_object_agg(tablename,
  has_table_privilege(current_user,'mingjing_core.'||tablename,'SELECT') AND
  has_table_privilege(current_user,'mingjing_core.'||tablename,'INSERT') AND
  has_table_privilege(current_user,'mingjing_core.'||tablename,'UPDATE') AND
  has_table_privilege(current_user,'mingjing_core.'||tablename,'DELETE'))
  FROM pg_tables WHERE schemaname='mingjing_core' AND tablename<>'schema_migrations'))
FROM pg_roles WHERE rolname=current_user;"""


def owner_sql() -> str:
    return """SELECT json_build_object(
'schema',pg_get_userbyid(nspowner),
'relations',(SELECT json_object_agg(c.relname,pg_get_userbyid(c.relowner))
 FROM pg_class c WHERE c.relnamespace=n.oid AND c.relkind IN ('r','p','S')))
FROM pg_namespace n WHERE n.nspname='mingjing_core';"""


def public_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"number": row["number"], "sha256": row["sha256"]} for row in rows]


def receipt_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
