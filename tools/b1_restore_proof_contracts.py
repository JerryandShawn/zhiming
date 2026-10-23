"""Inputs for an observed restore, never a caller-supplied success attestation."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tools.b1_restore_replay_contracts import (
    DATABASE,
    RestoreRequest,
    file_hash,
    load_document,
    regular,
    require,
    verify_candidate,
)
from tools.core_incremental_contracts import Request, validate_backup

OWNER_ENV = "B1_PROOF_OWNER_DSN"
WRITER_ENV = "B1_PROOF_WRITER_DSN"
LOCAL_SCHEMA = "b1-local-restore-drill-v1"
FORMAL_SCHEMA = "b1-isolated-restore-proof-v1"
IMPLICIT_PG_ENV = (
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGSYSCONFDIR",
    "PGOPTIONS",
    "PGPASSFILE",
    "PGPASSWORD",
)


def read_json(path: Path, *, local: bool) -> dict[str, Any]:
    regular(path, private=True, local_drill=local)
    require(path.stat().st_size <= 16_000_000, "PROOF_INPUT_SIZE")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "PROOF_INPUT_OBJECT")
    return value


@dataclass(frozen=True)
class ProofRequest:
    request: Path
    backup: Path
    dump: Path
    backup_ledger: Path
    ledger: Path
    ledger_sha256: str
    database: str
    candidate_source: Path
    candidate_python: Path
    pg_restore: Path
    pg_restore_sha256: str
    local_drill: bool = False

    def validate(self) -> tuple[Request, dict[str, Any], dict[str, Any]]:
        upgrade = Request.parse(read_json(self.request, local=self.local_drill))
        require(upgrade.scope == "stage", "STAGE_RESTORE_ONLY")
        self.formal_paths(upgrade)
        allowed = (
            self.database == DATABASE
            if not self.local_drill
            else re.fullmatch(r"b1_restore_proof_[0-9a-f]{32}", self.database)
        )
        require(allowed, "RESTORE_TARGET_ALLOWLIST")
        backup = read_json(self.backup, local=self.local_drill)
        validate_backup(upgrade, backup, {"state_sha256": backup.get("source_state_sha256")})
        require(re.fullmatch(r"[0-9a-f]{64}", str(backup.get("source_state_sha256", ""))), "BACKUP_STATE_HASH")
        for path, expected in (
            (self.dump, backup["dump_sha256"]),
            (self.backup_ledger, backup["withdrawals_sha256"]),
            (self.pg_restore, self.pg_restore_sha256),
        ):
            regular(path, private=path != self.pg_restore, local_drill=self.local_drill)
            require(file_hash(path) == expected, "PROOF_INPUT_CHANGED")
        require(self.pg_restore.is_absolute() and self.candidate_python.is_absolute(), "ABSOLUTE_EXECUTABLE")
        require(self.candidate_source.is_absolute(), "ABSOLUTE_CANDIDATE")
        regular(self.candidate_python.resolve())
        verify_candidate(self.candidate_source)
        self.trusted_candidate()
        latest = self.document(self.ledger, self.ledger_sha256)
        old = self.document(self.backup_ledger, backup["withdrawals_sha256"])
        verify_monotone(old, latest)
        require(set(upgrade.owners) <= {row["owner_user_id"] for row in latest["owners"]}, "UPGRADE_OWNER_MISSING")
        return upgrade, backup, latest

    def formal_paths(self, upgrade: Request) -> None:
        if self.local_drill:
            return
        root = Path(upgrade.release)
        require(self.candidate_source == root, "FORMAL_FIXED_RELEASE_REQUIRED")
        require(self.candidate_python == root / "venv/core/bin/python", "FORMAL_FIXED_VENV_REQUIRED")

    def trusted_candidate(self) -> None:
        if self.local_drill:
            return
        manifest = self.candidate_source / "__release_manifest__.json"
        paths = [manifest, *(self.candidate_source / name for name in json.loads(manifest.read_text())["files"])]
        checked = set()
        for path in paths:
            for item in (path, *path.parents):
                if item in checked:
                    continue
                checked.add(item)
                observed = item.stat()
                require(observed.st_uid == 0 and observed.st_mode & 0o022 == 0, "RESTORE_SOURCE_NOT_TRUSTED")

    def document(self, path: Path, sha256: str) -> dict[str, Any]:
        regular(path, private=True, local_drill=self.local_drill)
        require(re.fullmatch(r"[0-9a-f]{64}", sha256), "LEDGER_HASH_FORMAT")
        require(file_hash(path) == sha256, "LEDGER_CHANGED")
        return load_document(
            RestoreRequest(
                "b1-proof-ledger-validation",
                "stage",
                DATABASE,
                "mingjing_core",
                self.candidate_source,
                self.candidate_python,
                path,
                sha256,
                self.local_drill,
            )
        )

    def dsn(self, role: str) -> str:
        require(role in {"owner", "writer"}, "RESTORE_ROLE")
        require(not any(os.environ.get(key) for key in IMPLICIT_PG_ENV), "IMPLICIT_PG_ENV_FORBIDDEN")
        value = os.environ.get(OWNER_ENV if role == "owner" else WRITER_ENV, "")
        require(value, "PROOF_DSN_MISSING")
        fields = conninfo_to_dict(value)
        require(fields.get("host") in {"127.0.0.1", "::1"}, "LOOPBACK_ONLY")
        require(not fields.get("hostaddr") or fields["hostaddr"] == fields["host"], "HOSTADDR_SCOPE")
        require(not any(key in fields for key in ("service", "options")), "PROOF_DSN_OPTIONS")
        require(fields.get("dbname") == self.database, "RESTORE_DATABASE_IDENTITY")
        require(fields.get("user") == self.database + "_" + role, "SEPARATE_DATABASE_ROLES")
        ports = {"55480", "55481"} if self.local_drill else {"5432"}
        require(fields.get("port", "5432") in ports, "RESTORE_PORT")
        overrides = {"hostaddr": fields["host"], "port": fields.get("port", "5432")}
        configured_passfile = os.environ.get("B1_PROOF_PGPASSFILE")
        passfile = configured_passfile or os.path.abspath(os.devnull)
        require(not fields.get("passfile") or fields["passfile"] == passfile, "PROOF_DSN_OPTIONS")
        if configured_passfile:
            require(Path(passfile).is_absolute(), "ABSOLUTE_PGPASSFILE_REQUIRED")
            regular(Path(passfile), private=True, local_drill=self.local_drill)
        overrides["passfile"] = passfile
        return make_conninfo(value, **overrides)

    def platform(self) -> None:
        require(self.local_drill or sys.platform == "linux" and os.name == "posix", "LINUX_PROOF_REQUIRED")

    def dsns(self) -> dict[str, str]:
        values = {role: self.dsn(role) for role in ("owner", "writer")}
        fields = {role: conninfo_to_dict(value) for role, value in values.items()}
        require(
            all(fields["owner"][key] == fields["writer"][key] for key in ("hostaddr", "port", "dbname")),
            "SAME_RESTORE_SERVER_REQUIRED",
        )
        return values


def verify_monotone(old: dict[str, Any], new: dict[str, Any]) -> None:
    old_owners = {row["owner_user_id"]: row for row in old["owners"]}
    new_owners = {row["owner_user_id"]: row for row in new["owners"]}
    require(set(old_owners) == set(new_owners), "LATEST_OWNER_SET")
    for owner, ledger in old_owners.items():
        require(all(row in new_owners[owner]["revocations"] for row in ledger["revocations"]), "STALE_WITHDRAWALS")
    for name in ("tarot_requests", "deleted_draws"):
        require(all(row in new[name] for row in old[name]), "STALE_WITHDRAWALS")
    for row in old["delivery_receipts"]:
        matches = [item for item in new["delivery_receipts"] if receipt_key(item) == receipt_key(row)]
        require(len(matches) == 1, "STALE_RECEIPTS")
        item = matches[0]
        require(item["attempts"] >= row["attempts"], "STALE_RECEIPTS")
        require(
            row["status"] != "sent" or item["status"] == "sent" and row["receipt"] == item["receipt"], "STALE_RECEIPTS"
        )


def receipt_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row[key] for key in ("owner", "business_id", "channel", "target"))
