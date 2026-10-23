"""Storage orchestration contracts do not establish a running Docker or Linux PG."""

import json
import sys
from pathlib import Path

import pytest

from tools import b1_linux_drill as drill
from tools.b1_linux_application_drill_storage import preparation
from tools.b1_linux_drill_transport import DrillBlocked
from tools.core_incremental_contracts import MIGRATIONS


class StorageDocker:
    def __init__(self, count=0):
        self.count, self.calls = count, []

    def verify_local(self):
        return {"os": "linux", "synthetic": True}

    def image(self, **kwargs):
        return {"digest": "synthetic", "id": "synthetic"}

    def create_container(self, image):
        return {"synthetic": True}

    def wait_postgres(self):
        pass

    def execute(self, args):
        self.calls.append(args)
        return b"700\n600\n" if args[0] == "stat" else b""

    def sql(self, database, statement, **kwargs):
        self.calls.append((database, statement))
        if "server_version_num" in statement:
            return "150019"
        if "json_agg(datname)" in statement:
            return "[]"
        if "'checksums',json_object_agg" in statement:
            return json.dumps({"version": 4, "checksums": {str(n): MIGRATIONS[str(n)] for n in range(1, 5)}})
        if "json_agg(t)" in statement:
            return json.dumps([{"schemaname": "mingjing_core", "tablename": "core_owners"}])
        if "SELECT encode(sha256" in statement:
            return "a" * 64
        if "SELECT (SELECT count(*) FROM pg_class" in statement:
            return str(self.count)
        if "SELECT count(*) FROM pg_tables" in statement:
            return "0"
        return "{}"


def test_default_storage_plan_constructs_no_transport(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["drill", "--mode", "storage-preparation"])
    monkeypatch.setattr(drill, "LocalDocker", lambda: pytest.fail("no transport in default plan"))
    assert drill.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["restore_target_reserved_empty"] and not result["restores_database"]
    assert result["formal_restore_proof"] is False
    assert "mode" not in drill.plan()


def test_storage_preparation_never_restores_migrates_or_runs_ledger_0008(monkeypatch):
    docker = StorageDocker()
    rows = [{"number": n, "sha256": MIGRATIONS[str(n)], "source": "SELECT 1;"} for n in range(1, 8)]
    monkeypatch.setattr(drill, "migrations", lambda repo: rows)
    monkeypatch.setattr(drill, "backup_stage", lambda docker, ident: ("/b1/test", "/b1/test/schema4.dump", "b" * 64))
    for name in ("restore", "migrate_restore", "check_rollback", "ledger_compatibility"):
        monkeypatch.setattr(drill, name, lambda *a, **kw: pytest.fail("storage cannot restore or migrate"))
    result = drill.execute(
        Path("."), docker, run_id="b1-20261021-local", pull=False, migration8=None, mode="storage-preparation"
    )
    assert result["restore_target_empty"] and result["restore_written"] is False
    assert not result["application_ready"] and not result["admissible_restore_proof"]
    assert "CHECKPOINT_BOOTSTRAP_NOT_RUN" in result["blockers"]
    assert result["checksums"] == {str(n): MIGRATIONS[str(n)] for n in range(1, 5)}


def test_nonempty_reserved_restore_is_retained_and_refused():
    docker = StorageDocker(count=1)
    with pytest.raises(DrillBlocked, match="B3_RESTORE_TARGET_NOT_EMPTY"):
        preparation(
            docker, run_id="b1-20261021-local", directory="/b1/test", dump="/b1/test/old.dump", dump_hash="b" * 64
        )
    assert not any(isinstance(call, list) and call[0] in {"rm", "dropdb", "pg_restore"} for call in docker.calls)


def test_unknown_mode_refuses_before_git_or_transport():
    with pytest.raises(DrillBlocked, match="DRILL_MODE"):
        drill.execute(Path("."), None, run_id="b1-20261021-local", pull=False, migration8=None, mode="other")
