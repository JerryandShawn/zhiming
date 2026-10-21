"""Offline input, process isolation and actual local interpreter capability checks."""

from __future__ import annotations

import json
import os
import py_compile
import runpy
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from psycopg.conninfo import conninfo_to_dict

from tools import b1_linux_application_drill as cli
from tools.b1_linux_application_drill_contracts import (
    DSN_ENV,
    IMPLICIT_PG_ENV,
    ApplicationBlocked,
    ApplicationRequest,
)
from tools.b1_linux_application_drill_fence import check_gate, deployment, fence
from tools.b1_linux_application_drill_process import command, environment, run_worker

ROOT = Path(__file__).resolve().parents[3]
SUPPORT = runpy.run_path(str(ROOT / "tests/test_b1_restore_replay_support.py"))


@pytest.fixture(scope="module")
def application_request() -> ApplicationRequest:
    return ApplicationRequest(
        "b1-application-contract", "runtime", SUPPORT["materialize"](), Path(sys.executable), True
    )


def test_default_plan_never_constructs_worker(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setattr(sys, "argv", ["application"])
    monkeypatch.setattr(cli, "run_worker", lambda *args: pytest.fail("default must not invoke interpreter/PG/Docker"))
    assert cli.main() == 0
    assert json.loads(capsys.readouterr().out)["default_side_effects"] is False


@pytest.mark.parametrize("phase", ["migrate", "replay", "shell", "", "live"])
def test_unknown_phase_rejected_before_worker(application_request: ApplicationRequest, phase: str) -> None:
    with pytest.raises(ApplicationBlocked, match="APPLICATION_PHASE"):
        run_worker(replace(application_request, phase=phase))


@pytest.mark.parametrize("name", IMPLICIT_PG_ENV)
def test_ambient_libpq_forbidden(
    application_request: ApplicationRequest, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "synthetic-value")
    with pytest.raises(ApplicationBlocked, match="APPLICATION_IMPLICIT_PG_ENV"):
        replace(application_request, phase="backfill").dsn()


@pytest.mark.parametrize(
    "change",
    [
        {"host": "localhost"},
        {"host": "192.0.2.1"},
        {"hostaddr": "192.0.2.1"},
        {"dbname": "zhiming_core_live"},
        {"dbname": "core_test_main"},
        {"port": "5432"},
        {"user": "postgres"},
        {"options": "-c search_path=public"},
        {"service": "default"},
    ],
)
def test_database_allowlist(
    application_request: ApplicationRequest, monkeypatch: pytest.MonkeyPatch, change: dict
) -> None:
    from psycopg.conninfo import make_conninfo

    fields = {
        "host": "127.0.0.1",
        "port": "55480",
        "dbname": "b1_application_" + "a" * 32,
        "user": "b1_application_" + "a" * 32 + "_owner",
    }
    monkeypatch.setenv(DSN_ENV, make_conninfo(**dict(fields, **change)))
    with pytest.raises(ApplicationBlocked):
        replace(application_request, phase="backfill").dsn()


def test_worker_environment_excludes_secrets_and_normalizes_host(
    application_request: ApplicationRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KIMI_API_KEY", "synthetic-secret")
    monkeypatch.setenv("FEISHU_APP_SECRET", "synthetic-secret")
    monkeypatch.setenv("LANGSMITH_API_KEY", "synthetic-secret")
    monkeypatch.setenv(
        DSN_ENV,
        "host=127.0.0.1 port=55480 dbname=b1_application_" + "a" * 32 + " user=b1_application_" + "a" * 32 + "_owner",
    )
    value = environment(replace(application_request, phase="backfill"))
    assert not any(key in value for key in ("KIMI_API_KEY", "FEISHU_APP_SECRET", "LANGSMITH_API_KEY"))
    assert not any(key.startswith("PG") for key in value)
    assert conninfo_to_dict(value[DSN_ENV])["hostaddr"] == "127.0.0.1"
    assert value["CORE_FEISHU_ENABLED"] == "false" and value["OTEL_SDK_DISABLED"] == "true"


def test_actual_local_interpreter_is_not_linux_proof(application_request: ApplicationRequest) -> None:
    value = run_worker(application_request)
    assert value["runtime"]["locked_packages"] > 20
    assert value["runtime"]["dependency_check"] == "installed-metadata-requires-dist"
    assert value["runtime"]["checked_dependencies"] > 20
    assert value["runtime"]["admissible_linux"] is False
    assert value["runtime"]["database_connections"] == value["runtime"]["packages_installed"] == 0


def test_windows_cannot_claim_fcntl(application_request: ApplicationRequest) -> None:
    if os.name == "nt":
        with pytest.raises(ApplicationBlocked, match="LINUX_FCNTL_REQUIRED"):
            fence(replace(application_request, phase="fence"))


def test_corrupt_lock_rejected_without_dependency_check(
    application_request: ApplicationRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tools import b1_linux_application_drill_runtime as runtime

    (tmp_path / "requirements-core.lock").write_text("not a release lock", encoding="utf-8")
    monkeypatch.setattr(ApplicationRequest, "validate", lambda self: None)
    monkeypatch.setattr(runtime, "dependencies", lambda *args: pytest.fail("must reject before dependency check"))
    with pytest.raises(ApplicationBlocked, match="APPLICATION_CORE_LOCK_CHANGED"):
        runtime.runtime_capability(replace(application_request, candidate_source=tmp_path))


def test_worker_error_output_never_echoes_stderr(
    application_request: ApplicationRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import b1_linux_application_drill_process as process

    monkeypatch.setattr(
        process.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="synthetic-private-body-or-DSN", stdout=""),
    )
    with pytest.raises(ApplicationBlocked, match="^APPLICATION_PINNED_WORKER_FAILED$"):
        process.run_worker(application_request)


def test_existing_output_blocks_before_worker(
    application_request: ApplicationRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "receipt.json"
    path.write_text("retain", encoding="utf-8")
    monkeypatch.setattr(cli, "run_worker", lambda *args: pytest.fail("existing receipt must stop before work"))
    with pytest.raises(ApplicationBlocked, match="NEW_APPLICATION_OUTPUT"):
        cli.execute(application_request, path)
    assert path.read_text(encoding="utf-8") == "retain"


def test_requires_dist_transitive_extras_are_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import b1_linux_application_drill_runtime as runtime

    metadata = {"parent": ["child[secure]>=2"], "child": ["addon>=1; extra=='secure'"], "addon": []}
    monkeypatch.setattr(runtime.importlib.metadata, "requires", lambda name: metadata[name])
    monkeypatch.setattr(runtime.importlib.metadata, "version", lambda name: {"child": "2", "addon": "0"}[name])
    with pytest.raises(ApplicationBlocked, match="CORE_DEPENDENCY_VERSION"):
        runtime.dependencies({"parent": "1", "child": "2", "addon": "0"}, {})


def test_requires_dist_platform_marker_does_not_enable_unselected_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import b1_linux_application_drill_runtime as runtime

    monkeypatch.setattr(runtime.importlib.metadata, "requires", lambda name: ["absent>=1; extra=='unused'"])
    assert runtime.dependencies({"parent": "1"}, {}) == 0


def test_requires_dist_missing_locked_dependency_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import b1_linux_application_drill_runtime as runtime

    monkeypatch.setattr(runtime.importlib.metadata, "requires", lambda name: ["unpinned>=1"])
    with pytest.raises(ApplicationBlocked, match="CORE_UNPINNED_DEPENDENCY"):
        runtime.dependencies({"parent": "1"}, {})


def test_critical_import_rejects_development_runtime_outside_fixed_candidate(
    application_request: ApplicationRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import b1_linux_application_drill_runtime as runtime

    monkeypatch.setattr(runtime.importlib, "import_module", lambda name: SimpleNamespace(__file__=__file__))
    with pytest.raises(ApplicationBlocked, match="APPLICATION_IMPORT_OUTSIDE_CANDIDATE"):
        runtime.critical_imports(application_request)


def test_actual_b9_maintenance_gate_rejects_before_configuration_or_fcntl(
    application_request: ApplicationRequest, tmp_path: Path
) -> None:
    module = deployment(application_request)
    module.MAINTENANCE = str(tmp_path / "maintenance.flag")
    assert check_gate(module, tmp_path) is True


def test_real_python_reads_source_instead_of_matching_poisoned_pyc(
    application_request: ApplicationRequest, tmp_path: Path
) -> None:
    source = tmp_path / "application_cache_probe.py"
    source.write_text("VALUE='poison'\n", encoding="utf-8")
    observed = source.stat()
    py_compile.compile(str(source), doraise=True)
    source.write_text("VALUE='source'\n", encoding="utf-8")
    os.utime(source, ns=(observed.st_atime_ns, observed.st_mtime_ns))
    code = (
        f"import sys;sys.path.insert(0,{str(tmp_path)!r});"
        "import application_cache_probe;print(application_cache_probe.VALUE)"
    )
    unsafe = subprocess.run(
        [str(application_request.candidate_python), "-I", "-B", "-c", code],
        capture_output=True,
        encoding="utf-8",
        check=True,
        timeout=10,
        env=environment(application_request),
    )
    safe = subprocess.run(
        command(application_request, code),
        capture_output=True,
        encoding="utf-8",
        check=True,
        timeout=10,
        env=environment(application_request),
    )
    assert unsafe.stdout.strip() == "poison"
    assert safe.stdout.strip() == "source"


def test_all_application_child_vectors_disable_bytecode_reads(
    application_request: ApplicationRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import b1_linux_application_drill_process as process

    observed = []

    def child(arguments, **kwargs):
        observed.append(arguments)
        return SimpleNamespace(returncode=0, stdout='{"runtime":{},"result":{}}')

    monkeypatch.setattr(process.subprocess, "run", child)
    process.run_worker(application_request)
    assert observed[0][:6] == [
        str(application_request.candidate_python),
        "-I",
        "-B",
        "-X",
        "pycache_prefix=" + os.path.abspath(os.devnull),
        "-c",
    ]
    assert "writer(request" in process.writer_code(application_request, Path("/synthetic-fence"))


def test_dsn_uses_null_passfile_instead_of_user_home(
    application_request: ApplicationRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        DSN_ENV,
        "host=127.0.0.1 port=55480 dbname=b1_application_" + "a" * 32 + " user=b1_application_" + "a" * 32 + "_owner",
    )
    request = replace(application_request, phase="backfill")
    normalized = request.dsn()
    assert conninfo_to_dict(normalized)["passfile"] == os.devnull
    monkeypatch.setenv(DSN_ENV, normalized)
    assert conninfo_to_dict(request.dsn()) == conninfo_to_dict(normalized)
