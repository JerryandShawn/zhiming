"""Local application rehearsal inputs never authorize a real deployment."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tools.b1_restore_replay_contracts import regular, verify_candidate
from tools.core_incremental_contracts import RELEASE_ROOT, TARGET

DSN_ENV = "B1_APPLICATION_OWNER_DSN"
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


class ApplicationBlocked(RuntimeError):
    """Only fixed codes cross the subprocess boundary."""


def require(value: object, code: str) -> None:
    if not value:
        raise ApplicationBlocked(code)


@dataclass(frozen=True)
class ApplicationRequest:
    operation_id: str
    phase: str
    candidate_source: Path
    candidate_python: Path
    local_drill: bool = False

    def validate(self) -> None:
        require(re.fullmatch(r"b1-[a-z0-9-]{8,70}", self.operation_id), "APPLICATION_OPERATION_ID")
        require(self.phase in {"runtime", "backfill", "fence"}, "APPLICATION_PHASE")
        require(type(self.local_drill) is bool, "APPLICATION_LOCAL_MODE")
        require(
            self.candidate_source.is_absolute() and self.candidate_python.is_absolute(), "ABSOLUTE_APPLICATION_SOURCE"
        )
        if not self.local_drill:
            require(self.candidate_source == Path(RELEASE_ROOT) / TARGET, "APPLICATION_FIXED_RELEASE")
            require(self.candidate_python == self.candidate_source / "venv/core/bin/python", "APPLICATION_FIXED_PYTHON")
        verify_candidate(self.candidate_source)
        regular(self.candidate_python.resolve())
        self.trusted_files()

    def trusted_files(self) -> None:
        if self.local_drill:
            return
        manifest = self.candidate_source / "__release_manifest__.json"
        files = [
            manifest,
            self.candidate_python,
            self.candidate_python.resolve(),
            *(self.candidate_source / name for name in json.loads(manifest.read_text())["files"]),
        ]
        checked = set()
        for path in files:
            for item in (path, *path.parents):
                if item not in checked:
                    observed = item.stat()
                    require(observed.st_uid == 0 and observed.st_mode & 0o022 == 0, "APPLICATION_SOURCE_NOT_TRUSTED")
                    checked.add(item)

    def dsn(self) -> str:
        require(self.phase == "backfill", "APPLICATION_DATABASE_PHASE")
        require(not any(os.environ.get(key) for key in IMPLICIT_PG_ENV), "APPLICATION_IMPLICIT_PG_ENV")
        require(os.environ.get(DSN_ENV), "APPLICATION_DSN_MISSING")
        try:
            value = conninfo_to_dict(os.environ[DSN_ENV])
        except Exception:
            raise ApplicationBlocked("APPLICATION_DSN_INVALID") from None
        require(value.get("host") in {"127.0.0.1", "::1"}, "APPLICATION_LOOPBACK_ONLY")
        require(not value.get("hostaddr") or value["hostaddr"] == value["host"], "APPLICATION_HOSTADDR")
        allowed = {"host", "hostaddr", "port", "dbname", "user", "password", "connect_timeout", "passfile"}
        require(not set(value) - allowed, "APPLICATION_DSN_OPTIONS")
        require(not value.get("passfile") or value["passfile"] == os.devnull, "APPLICATION_DSN_OPTIONS")
        database = value.get("dbname", "")
        require(
            database == "zhiming_core_stage"
            if not self.local_drill
            else re.fullmatch(r"b1_(?:application|restore_proof)_[0-9a-f]{32}", database),
            "APPLICATION_DATABASE",
        )
        require(value.get("user") == database + "_owner", "APPLICATION_ROLE")
        port = value.get("port", "5432")
        require(port in ({"55480", "55481"} if self.local_drill else {"5432"}), "APPLICATION_PORT")
        return make_conninfo(**dict(value, port=port, hostaddr=value["host"], passfile=os.devnull, connect_timeout="5"))
