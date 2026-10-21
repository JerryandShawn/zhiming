"""Actual old-entry Python argv with synthetic modules; never b9 PG/Linux proof."""

from __future__ import annotations

import json
import os
import py_compile
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tools import b1_restore_replay as replay
from tools.b1_restore_replay_contracts import DATABASE, RestoreRequest, file_hash
from tools.core_incremental_contracts import EXPECTED_MANIFEST, STAGE_UNITS, Request
from tools.core_incremental_pg import PostgresPort


@dataclass(frozen=True)
class CacheProbe:
    root: Path
    module: Path
    cache: Path
    source: bytes
    original_cache: bytes

    def code(self, *, receipt: bool = False) -> str:
        return (
            f"import sys,json;sys.path.insert(0,{str(self.root)!r})\n"
            "from mingjing_core.repositories.postgres import PostgresRepository\n"
            "print(json.dumps({'value':PostgresRepository.marker,'isolated':sys.flags.isolated,"
            "'dont_write':sys.dont_write_bytecode,'cache_prefix':sys.pycache_prefix"
            + (",'schema':'b1-stage-restore-replay-v1'" if receipt else "")
            + "}))\n"
        )

    def unchanged(self) -> None:
        assert self.module.read_bytes() == self.source
        assert self.cache.read_bytes() == self.original_cache


@pytest.fixture
def probe(tmp_path: Path) -> CacheProbe:
    root = tmp_path / "synthetic-candidate"
    package = root / "mingjing_core/repositories"
    package.mkdir(parents=True)
    (root / "mingjing_core/__init__.py").write_bytes(b"")
    (package / "__init__.py").write_bytes(b"")
    module = package / "postgres.py"
    poison = b"class PostgresRepository:\n    marker='poison'\n"
    source = b"class PostgresRepository:\n    marker='source'\n"
    assert len(poison) == len(source)
    module.write_bytes(poison)
    stamp = module.stat()
    cache = Path(
        py_compile.compile(str(module), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
    )
    original_cache = cache.read_bytes()
    module.write_bytes(source)
    os.utime(module, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    return CacheProbe(root, module, cache, source, original_cache)


def safe_environment() -> dict[str, str]:
    return {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}


def check_guarded(value: dict[str, Any]) -> None:
    assert value["value"] == "source" and value["isolated"] == 1
    assert value["dont_write"] is True and value["cache_prefix"] == os.path.abspath(os.devnull)


def test_real_old_B_only_control_reads_timestamp_valid_poison(probe: CacheProbe) -> None:
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe.code()],
        env=safe_environment(),
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert json.loads(result.stdout)["value"] == "poison"
    probe.unchanged()


def restore_request(probe: CacheProbe, tmp_path: Path) -> tuple[RestoreRequest, dict[str, Any]]:
    document: dict[str, Any] = {
        "schema": "core3-withdrawals-v2",
        "owners": [],
        "tarot_requests": [],
        "deleted_draws": [],
        "delivery_receipts": [],
    }
    ledger = tmp_path / "synthetic-ledger.json"
    ledger.write_text(json.dumps(document), encoding="utf-8")
    ledger.chmod(0o600)
    request = RestoreRequest(
        "b1-bytecode-replay",
        "stage",
        DATABASE,
        "mingjing_core",
        probe.root,
        Path(sys.executable),
        ledger,
        file_hash(ledger),
        True,
    )
    return request, document


def test_existing_B7_entry_argv_executes_source_and_keeps_original_cache(
    probe: CacheProbe, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, document = restore_request(probe, tmp_path)
    observations: list[object] = []
    actual_run = subprocess.run

    def verify(path: Path) -> None:
        # Only the cache boundary is under test; this synthetic source is not a b9 release.
        assert path == probe.root
        observations.append("source-guard-invoked")

    def observe(arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        observations.append(arguments)
        assert "PYTHONPYCACHEPREFIX" not in kwargs["env"]
        return actual_run(arguments, **kwargs)

    monkeypatch.setenv("B1_RESTORE_OWNER_DSN", f"host=127.0.0.1 port=55480 dbname={DATABASE} user={DATABASE}_owner")
    monkeypatch.setenv("PYTHONPYCACHEPREFIX", str(tmp_path / "untrusted-prefix"))
    monkeypatch.setattr(replay, "verify_candidate", verify)
    monkeypatch.setattr(replay, "worker_code", lambda: probe.code(receipt=True))
    monkeypatch.setattr(replay.subprocess, "run", observe)
    check_guarded(replay.run_candidate(request, document))
    assert observations[0] == "source-guard-invoked"
    assert observations[1][:6] == [
        str(request.candidate_python),
        "-I",
        "-B",
        "-X",
        "pycache_prefix=" + os.path.abspath(os.devnull),
        "-c",
    ]
    probe.unchanged()


def test_B7_ledger_change_still_stops_before_source_or_process(
    probe: CacheProbe, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, document = restore_request(probe, tmp_path)
    request.ledger.write_bytes(request.ledger.read_bytes() + b" ")
    monkeypatch.setattr(replay, "verify_candidate", lambda *args: pytest.fail("changed ledger reached source"))
    monkeypatch.setattr(replay.subprocess, "run", lambda *args, **kwargs: pytest.fail("changed ledger spawned process"))
    with pytest.raises(replay.ReplayRejected, match="LEDGER_CHANGED"):
        replay.run_candidate(request, document)
    probe.unchanged()


@dataclass
class LocalRunner:
    expected_python: str
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        args: list[str],
        *,
        env: Mapping[str, str] | None = None,
        stdin: str | None = None,
        output: Path | None = None,
    ) -> bytes:
        assert args[0] == self.expected_python and output is None
        self.calls.append(args)
        # Existing Linux lexical executable is recorded; the injected runner uses the available local Python.
        result = subprocess.run(
            [sys.executable, *args[1:]],
            input=stdin,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return result.stdout.encode()


def test_existing_incremental_entry_argv_executes_source_without_opening_PG(
    probe: CacheProbe, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = Request(
        "b1-bytecode-upgrade",
        "stage",
        "synthetic-host",
        EXPECTED_MANIFEST,
        "a" * 64,
        ("primary",),
        8 * 1024**3,
        dict.fromkeys(STAGE_UNITS, "a" * 64),
        "",
    )
    monkeypatch.setattr(Request, "release", property(lambda self: str(probe.root)))
    for role in ("owner", "writer"):
        monkeypatch.setenv(
            "CORE_INCREMENTAL_" + role.upper() + "_DSN",
            f"host=127.0.0.1 port=5432 dbname={request.database} user={request.database}_{role}",
        )
    runner = LocalRunner(str(probe.root) + "/venv/core/bin/python")
    port = PostgresPort(request, runner, connector=lambda *args, **kwargs: pytest.fail("cache test opened PG"))
    check_guarded(port.candidate(probe.code()))
    assert runner.calls[0][:6] == [
        runner.expected_python,
        "-I",
        "-B",
        "-X",
        "pycache_prefix=" + os.path.abspath(os.devnull),
        "-c",
    ]
    probe.unchanged()
