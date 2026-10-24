"""Linux assets are rendered; local PG execution proves the internal launcher seam, not four full apps."""

from __future__ import annotations

import ast
import json
import os
import shlex
import subprocess
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from first_release_assets_process_support import BODY, STDOUT, run_common
from first_release_support import ROOT
from psycopg.rows import dict_row
from test_first_release_service_pg import restored as restored_fixture

from tools import first_release_hermes_entry as entry
from tools import first_release_service_assets as assets_module
from tools.first_release_contracts import RestoreRejected
from tools.first_release_incremental_pg import snapshot
from tools.first_release_service_assets import Assets, LocalProjection, launcher_argv
from tools.first_release_service_binding import ServiceBinding


def document(*, sid="12345678901234567", database="synthetic_assets", database_oid=401, writer_oid=403):
    return {
        "schema": "first-release-service-assets-v1",
        "candidate": "a" * 40,
        "workspace": "/root/synthetic-service-workspace",
        "system_identifier": sid,
        "database": database,
        "database_oid": database_oid,
        "writer": database + "_writer",
        "writer_oid": writer_oid,
        "report_owner": "synthetic",
        "env_files": ["/root/synthetic-core.env", "/root/synthetic-member.env"],
        "config_path": "/root/zhiming-core-secrets/synthetic-service-config.json",
        "common_env_path": "/root/zhiming-core-secrets/synthetic-service-common.env",
        "k3_tokenizer_dir": "/root/synthetic-k3-artifacts",
    }


@pytest.fixture(scope="module")
def restored(tmp_path_factory):
    yield from restored_fixture.__wrapped__(tmp_path_factory)


@pytest.fixture
def configured(restored, tmp_path):
    actual, sample = restored.actual, restored.sample
    assets = Assets.parse(
        document(
            sid=actual["sid"],
            database=sample.inputs.contract.database,
            database_oid=actual["database_oid"],
            writer_oid=actual["writer_oid"],
        )
    )
    projection = LocalProjection(ROOT, Path(sys.executable), tmp_path)
    binding = ServiceBinding(
        "hermes",
        ROOT,
        tmp_path,
        actual["sid"],
        sample.inputs.contract.database,
        actual["database_oid"],
        sample.inputs.contract.database + "_writer",
        actual["writer_oid"],
    )
    binding.fence_path.parent.mkdir(parents=True)
    binding.fence_path.write_bytes(b"synthetic-existing-assets-fence")
    return SimpleNamespace(
        assets=assets,
        projection=projection,
        binding=binding,
        actual=actual,
        writer_dsn=sample.environment["FIRST_RELEASE_WRITER_DSN"],
        owner_dsn=sample.environment["FIRST_RELEASE_OWNER_DSN"],
    )


def state(value):
    with psycopg.connect(value.owner_dsn, row_factory=dict_row) as owner:
        return snapshot(owner)


def committed(value, source):
    with psycopg.connect(value.owner_dsn) as owner:
        rows = owner.execute(
            "SELECT data FROM mingjing_core.core_entities WHERE owner='synthetic' AND kind='message' "
            "AND data->>'source_id'=%s",
            (source,),
        ).fetchall()
    assert len(rows) == 1 and rows[0][0]["content"] == BODY


def rendered_builder_contract(assets):
    files = assets_module.render(assets)
    assert len([name for name in files if name.endswith(".service")]) == 3
    for role, name in assets_module.UNITS.items():
        text = files[name].decode()
        command = next(line.removeprefix("ExecStart=") for line in text.splitlines() if line.startswith("ExecStart="))
        assert shlex.split(command) == assets_module.entry_argv(assets, role)
        assert shlex.split(command)[:3] == [
            assets.core_python,
            "-I",
            assets.release + "/tools/first_release_hermes_entry.py",
        ]
        assert "KillMode=control-group" in text and "WorkingDirectory=" + assets.release in text
        assert ".timer" not in text
    wrapper = ast.parse(files["core_consultation.py"].decode())
    assignment = next(
        node
        for node in ast.walk(wrapper)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "command" for target in node.targets)
    )
    assert ast.literal_eval(assignment.value) == assets_module.entry_argv(assets, "hermes")
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
        for node in ast.walk(wrapper)
    )
    assert json.loads(files["service-config.json"]) == json.loads(json.dumps(assets.document()))
    assert "RestartSec=5\n" in files[assets_module.UNITS["web"]].decode()
    assert "RestartSec=10\n" in files[assets_module.UNITS["feishu"]].decode()
    common = files["service-common.env"].decode()
    assert "CHART_PYTHON=" + assets.chart_python + "\n" in common
    assert "K3_TOKENIZER_DIR=" + assets.k3_tokenizer_dir + "\n" in common
    assert "MODELS_CONFIG=" + assets.release + "/config/models.first-release.yaml\n" in common
    assert not any(name in common for name in ("PASSWORD", "ZHIMING_DATABASE_URL", "MEMBER_"))
    manifest = json.loads(files["manifest.json"])
    assert manifest["linux_runtime_verified"] is manifest["timer_generated"] is False
    assert not any(name.endswith(".timer") for name in files)
    return files


def test_rendered_entry_assets_share_binding_and_internal_projected_launcher_really_commits(
    configured, record_property
):
    value = configured
    rendered_builder_contract(value.assets)
    native_args = ("--question", "SYNTHETIC_QUESTION;literal$argument")
    command = launcher_argv(value.assets, "hermes", native_args, local_projection=value.projection)
    assert command[:3] == [sys.executable, "-m", "tools.first_release_service"]
    assert command[command.index("--") + 1 :] == list(native_args)
    source = "assets-" + uuid.uuid4().hex
    result = run_common(command, value.writer_dsn, role="hermes", native_args=list(native_args), source=source)
    assert result.returncode == 0 and result.stdout == STDOUT and result.stderr == ""
    committed(value, source)
    record_property("internal_projected_launcher_actual_memory_commits", 1)
    record_property("four_full_applications_or_linux_execution", False)
    record_property("actual_external_requests", 0)


def refused(value, assets):
    command = launcher_argv(assets, "web", local_projection=value.projection)
    result = run_common(command, value.writer_dsn, role="web", native_args=[], source="rejected-" + uuid.uuid4().hex)
    assert result.returncode == 2 and result.stdout == ""
    assert result.stderr == "SERVICE_CONFIGURATION_OR_FENCE_REJECTED\n"


def test_projected_assets_marker_and_actual_identity_gate_reject_without_business_changes(configured):
    value = configured
    before, original = state(value), value.binding.fence_path.read_bytes()
    wrong = replace(value.assets, database_oid=value.assets.database_oid + 1)
    variant = value.binding.fence_path.with_name(
        value.binding.system_identifier + "-" + str(wrong.database_oid) + ".lock"
    )
    variant.write_bytes(b"synthetic-wrong-assets-oid")
    refused(value, wrong)
    assert state(value) == before
    value.binding.maintenance.write_bytes(b'{"synthetic_maintenance":true}')
    marker = value.binding.maintenance.read_bytes()
    refused(value, value.assets)
    assert state(value) == before and value.binding.maintenance.read_bytes() == marker
    assert value.binding.fence_path.read_bytes() == original


def default_no_io(assets, output, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("DEFAULT_ASSET_GENERATION_MUST_NOT_CONNECT_SPAWN_OR_WRITE")

    with monkeypatch.context() as changes:
        for target, name in (
            (psycopg, "connect"),
            (subprocess, "Popen"),
            (subprocess, "run"),
            (os, "open"),
            (os, "mkdir"),
            (Path, "write_bytes"),
            (Path, "write_text"),
        ):
            changes.setattr(target, name, forbidden)
        result = assets_module.execute(assets, output)
        assert result["files_written"] == result["database_connections"] == result["processes_started"] == 0
        assert result["installed"] is result["linux_runtime_verified"] is False
    assert not output.exists()


def private_read_boundary(path, record_property):
    path.write_bytes(b"SYNTHETIC_PRIVATE_ENV=literal\n")
    os.chmod(path, 0o600)
    if os.name == "nt":
        with pytest.raises(RestoreRejected, match="^ENTRY_PRIVATE_PERMISSIONS_UNVERIFIED$"):
            entry._private_read(path)
        record_property("protected_env_mode_check", "ENTRY_PRIVATE_PERMISSIONS_UNVERIFIED")
    else:
        assert entry._private_read(path) == b"SYNTHETIC_PRIVATE_ENV=literal\n"
        os.chmod(path, 0o644)
        with pytest.raises(RestoreRejected, match="^ENTRY_PRIVATE_CONFIG_REQUIRED$"):
            entry._private_read(path)
        record_property("protected_env_mode_check", "actual_posix_private_then_world_readable_rejected")


def entry_guard_boundary(assets, temporary, monkeypatch):
    projection = LocalProjection(ROOT, Path(sys.executable), temporary)
    with monkeypatch.context() as changes:
        changes.setenv("PYTHONPATH", "SYNTHETIC_INJECTED_ENVIRONMENT")
        with pytest.raises(RestoreRejected, match="^ENTRY_INJECTED_ENVIRONMENT_REJECTED$"):
            entry.run(assets, (), local_projection=projection)
    for role, args in (("web", ("--question", "invalid")), ("hermes", ("embedded\x00argument",))):
        with pytest.raises(RestoreRejected, match="^ASSETS_NATIVE_ARGUMENTS_REJECTED$"):
            launcher_argv(assets, role, args)


def wrapper_guard(output):
    environment = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    environment["PYTHONPATH"] = "SYNTHETIC_INJECTED_ENVIRONMENT"
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(output / "core_consultation.py"), "--question", "SYNTHETIC_PRIVATE_ARGUMENT"],
        env=environment,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 78 and result.stdout == ""
    assert result.stderr == "HERMES_INJECTED_ENVIRONMENT_REJECTED\n"


def cold_nonisolated_entry(temporary):
    environment = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    missing = temporary / "missing-service-config.json"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "tools/first_release_hermes_entry.py"),
            "--config",
            str(missing),
            "--role",
            "hermes",
            "--run",
        ],
        env=environment,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 78 and result.stdout == ""
    assert result.stderr == "ENTRY_ISOLATED_RUNTIME_REQUIRED\n" and not missing.exists()


def test_default_exclusive_review_outputs_and_real_entry_wrapper_boundaries(
    tmp_path, monkeypatch, capsys, record_property
):
    assets = Assets.parse(document())
    monkeypatch.chdir(tmp_path)
    private = tmp_path / "private"
    private.mkdir()
    output = private / "new-review-assets"
    expected = rendered_builder_contract(assets)
    rendered_builder_contract(replace(assets, config_path="/root/zhiming-core-secrets/RELEASE.json"))
    default_no_io(assets, output, monkeypatch)
    result = assets_module.execute(assets, output, write_local=True)
    assert result["files_written"] == len(expected) and result["installed"] is False
    before = {name: (output / name).read_bytes() for name in expected}
    assert before == expected
    with pytest.raises(RestoreRejected, match="^ASSETS_NEW_OUTPUT_REQUIRED$"):
        assets_module.execute(assets, output, write_local=True)
    assert before == {name: (output / name).read_bytes() for name in expected}
    private_read_boundary(tmp_path / "real-test-environment.env", record_property)
    entry_guard_boundary(assets, tmp_path, monkeypatch)
    wrapper_guard(output)
    cold_nonisolated_entry(tmp_path)
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(dict(document(), workspace="/root/SYNTHETIC_SECRET_$EXPANSION")), encoding="utf-8")
    assert assets_module.main(["--config", str(invalid), "--output", str(private / "rejected")]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "blocked", "code": "SERVICE_ASSETS_REJECTED_OUTPUTS_RETAINED"}
    assert captured.err == "" and "SYNTHETIC_SECRET" not in captured.out + captured.err
    assert before == {name: (output / name).read_bytes() for name in expected}
    record_property("formal_entry_or_systemd_execution", False)
