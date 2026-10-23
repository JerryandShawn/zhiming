"""Execution-hook models never attest a physical Linux venv or execute a child."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import b1_linux_application_drill as application
from tools import b1_linux_application_drill_fence as fence_module
from tools import b1_linux_application_drill_process as app_process
from tools import b1_restore_proof as proof
from tools import b1_restore_proof_process as proof_process
from tools import b1_restore_replay as replay
from tools import b1_runtime_trust as trust
from tools import core_incremental as incremental
from tools import core_incremental_binaries as binaries
from tools.b1_linux_application_drill_contracts import ApplicationRequest
from tools.b1_restore_proof_contracts import ProofRequest
from tools.b1_restore_replay_contracts import DATABASE, ReplayRejected, RestoreRequest
from tools.core_incremental_contracts import TARGET, digest

ROOT = Path("/root/zhiming-core-releases") / TARGET
PYTHON = ROOT / "venv/core/bin/python"
PROOF_SOURCES = (
    "tools/b1_restore_proof.py",
    "tools/b1_restore_proof_contracts.py",
    "tools/b1_restore_proof_pg.py",
    "tools/b1_restore_proof_process.py",
    "tools/b1_restore_proof_worker.py",
    "tools/b1_restore_replay.py",
    "tools/b1_restore_replay_contracts.py",
    "tools/b1_restore_replay_worker.py",
    "tools/b1_runtime_trust.py",
    "tools/core_incremental_contracts.py",
    "mingjing_core/__init__.py",
    "mingjing_core/timekit/__init__.py",
    "mingjing_core/timekit/clock.py",
)


class StoppedBeforeEffect(Exception):
    """Proves a callback was reached without running its real effect."""


def rejected() -> None:
    raise trust.RuntimeTrustRejected("VENV_GROUP_OR_OTHER_WRITABLE")


def forbidden(*args, **kwargs):
    pytest.fail("hook model crossed a physical process/PG/filesystem boundary")


def no_effect(*args, **kwargs):
    raise StoppedBeforeEffect


@pytest.fixture
def app_request() -> ApplicationRequest:
    return ApplicationRequest("b1-runtime-hook-model", "runtime", ROOT, PYTHON)


@pytest.fixture
def proof_request(tmp_path) -> ProofRequest:
    return ProofRequest(
        *(tmp_path / name for name in ("request", "backup", "dump", "old-ledger", "ledger")),
        "a" * 64,
        DATABASE,
        ROOT,
        PYTHON,
        tmp_path / "pg_restore",
        "b" * 64,
    )


def trust_hook(monkeypatch, module, hook):
    monkeypatch.setattr(module, "inspect_core_venv", hook, raising=False)


def test_app_formal_guard_rejects_before_child(app_request, monkeypatch):
    monkeypatch.setattr(ApplicationRequest, "validate", lambda self: None)
    trust_hook(monkeypatch, app_process, rejected)
    monkeypatch.setattr(app_process.subprocess, "run", forbidden)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_GROUP_OR_OTHER_WRITABLE"):
        app_process.run_worker(app_request)


@pytest.mark.parametrize("local", [False, True])
def test_app_guard_applies_only_to_formal_and_preserves_lexical_argv(app_request, monkeypatch, local):
    calls, commands = [], []
    monkeypatch.setattr(ApplicationRequest, "validate", lambda self: None)
    trust_hook(monkeypatch, app_process, lambda: calls.append("checked"))

    def child(args, **kwargs):
        commands.append(args)
        return SimpleNamespace(returncode=0, stdout='{"runtime":{},"result":{}}')

    monkeypatch.setattr(app_process.subprocess, "run", child)
    app_process.run_worker(replace(app_request, local_drill=local))
    app_process.run_worker(replace(app_request, local_drill=local))
    assert calls == ([] if local else ["checked", "checked"])
    assert len(commands) == 2 and all(command[0] == str(PYTHON) for command in commands)
    assert all(command[1:4] == ["-I", "-B", "-X"] for command in commands)


@pytest.mark.parametrize("local", [False, True])
def test_fence_second_popen_has_its_own_formal_guard(app_request, monkeypatch, tmp_path, local):
    calls = []
    original = fence_module.require
    monkeypatch.setattr(fence_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        fence_module, "require", lambda value, code: None if code == "LINUX_FCNTL_REQUIRED" else original(value, code)
    )
    monkeypatch.setattr(fence_module, "create_inert_tree", lambda request: tmp_path)
    monkeypatch.setattr(fence_module, "deployment", lambda request: SimpleNamespace())
    monkeypatch.setattr(fence_module, "command", lambda request, code: [], raising=False)
    monkeypatch.setattr(app_process, "command", lambda request, code: [])
    monkeypatch.setattr(app_process, "environment", lambda request: {})
    monkeypatch.setattr(app_process, "writer_code", lambda request, directory: "inert-model")
    monkeypatch.setattr(fence_module.subprocess, "Popen", no_effect)
    trust_hook(monkeypatch, fence_module, lambda: calls.append("checked"))
    with pytest.raises(StoppedBeforeEffect):
        fence_module.fence(replace(app_request, local_drill=local))
    assert calls == ([] if local else ["checked"])


def test_fence_rejected_guard_never_starts_second_child(app_request, monkeypatch, tmp_path):
    original = fence_module.require
    monkeypatch.setattr(fence_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        fence_module, "require", lambda value, code: None if code == "LINUX_FCNTL_REQUIRED" else original(value, code)
    )
    monkeypatch.setattr(fence_module, "create_inert_tree", lambda request: tmp_path)
    monkeypatch.setattr(fence_module, "deployment", lambda request: SimpleNamespace())
    monkeypatch.setattr(fence_module.subprocess, "Popen", forbidden)
    trust_hook(monkeypatch, fence_module, rejected)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_GROUP_OR_OTHER_WRITABLE"):
        fence_module.fence(app_request)


def generation_request(local):
    return SimpleNamespace(
        local_drill=local, platform=lambda: None, validate=lambda: (None, None, None), dsns=lambda: {}
    )


def test_restore_proof_checks_formal_runtime_before_first_pg(monkeypatch):
    trust_hook(monkeypatch, proof, rejected)
    monkeypatch.setattr(proof, "empty_target", forbidden)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_GROUP_OR_OTHER_WRITABLE"):
        proof.generate(generation_request(False))


@pytest.mark.parametrize("local", [False, True])
def test_restore_proof_local_never_borrows_formal_guard(monkeypatch, local):
    calls = []
    trust_hook(monkeypatch, proof, lambda: calls.append("checked"))
    monkeypatch.setattr(proof, "empty_target", no_effect)
    with pytest.raises(StoppedBeforeEffect):
        proof.generate(generation_request(local))
    assert calls == ([] if local else ["checked"])


@pytest.mark.parametrize("phase", ["migrate", "replay"])
def test_every_formal_proof_worker_is_checked_before_launch(proof_request, monkeypatch, phase):
    trust_hook(monkeypatch, proof_process, rejected)
    monkeypatch.setattr(proof_process, "environment", lambda request: {})
    monkeypatch.setattr(proof_process.subprocess, "run", forbidden)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_GROUP_OR_OTHER_WRITABLE"):
        proof_process.run_worker(proof_request, phase, {})


def test_local_proof_worker_keeps_nonformal_mode_and_bytecode_flags(proof_request, monkeypatch):
    trust_hook(monkeypatch, proof_process, forbidden)
    monkeypatch.setattr(proof_process, "environment", lambda request: {})
    calls = []

    def child(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="{}")

    monkeypatch.setattr(proof_process.subprocess, "run", child)
    proof_process.run_worker(replace(proof_request, local_drill=True), "replay", {})
    assert calls[0][:4] == [str(PYTHON), "-I", "-B", "-X"]


def replay_request() -> RestoreRequest:
    return RestoreRequest(
        "b1-replay-hook-model", "stage", DATABASE, "mingjing_core", ROOT, PYTHON, Path("/ledger"), "a" * 64
    )


def prepare_replay(monkeypatch):
    monkeypatch.setattr(RestoreRequest, "validate", lambda self: None)
    monkeypatch.setattr(replay, "verify_candidate", lambda request: None)
    monkeypatch.setattr(replay, "load_document", lambda request: {})
    monkeypatch.setattr(replay, "regular", lambda *args, **kwargs: None)
    monkeypatch.setattr(replay, "worker_environment", lambda request: {})


def test_formal_b7_guard_rejects_before_child(monkeypatch):
    prepare_replay(monkeypatch)
    trust_hook(monkeypatch, replay, rejected)
    monkeypatch.setattr(replay.subprocess, "run", forbidden)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_GROUP_OR_OTHER_WRITABLE"):
        replay.run_candidate(replay_request(), {})


@pytest.mark.parametrize(
    "change", [{"candidate_source": Path("/elsewhere")}, {"candidate_python": Path("/usr/bin/python3")}]
)
def test_b7_formal_binding_cannot_borrow_fixed_tree_attestation(monkeypatch, change):
    prepare_replay(monkeypatch)
    trust_hook(monkeypatch, replay, forbidden)
    monkeypatch.setattr(replay.subprocess, "run", forbidden)
    with pytest.raises(ReplayRejected, match="FORMAL_FIXED_(RELEASE|VENV)_REQUIRED"):
        replay.run_candidate(replace(replay_request(), **change), {})


@pytest.mark.parametrize("local", [False, True])
def test_b7_local_and_formal_modes_are_distinct_before_launch(monkeypatch, local):
    prepare_replay(monkeypatch)
    calls = []
    trust_hook(monkeypatch, replay, lambda: calls.append("checked"))
    monkeypatch.setattr(replay.subprocess, "run", no_effect)
    with pytest.raises(StoppedBeforeEffect):
        replay.run_candidate(replace(replay_request(), local_drill=local), {})
    assert calls == ([] if local else ["checked"])


@pytest.mark.parametrize("module", [application, proof])
def test_default_application_and_proof_never_construct_physical_guard(module, monkeypatch, capsys):
    trust_hook(monkeypatch, module, forbidden)
    monkeypatch.setattr(trust, "inspect_core_venv", forbidden)
    if module is application:
        monkeypatch.setattr(sys, "argv", ["application"])
        assert module.main() == 0
    else:
        monkeypatch.setattr(ProofRequest, "validate", lambda self: None)
        paths = (
            "request",
            "backup",
            "dump",
            "backup-ledger",
            "ledger",
            "candidate-source",
            "candidate-python",
            "pg-restore",
        )
        argv = [item for name in paths for item in ("--" + name, "/synthetic")]
        argv += ["--ledger-sha256", "a" * 64, "--database", DATABASE, "--pg-restore-sha256", "b" * 64]
        assert module.main(argv) == 0
    assert json.loads(capsys.readouterr().out)


def test_controller_hash_covers_new_guard_without_changing_candidate(tmp_path, monkeypatch):
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "core_incremental.py").write_text("controller")
    helper = tools / "b1_runtime_trust.py"
    helper.write_text("first")
    monkeypatch.setattr(incremental, "__file__", str(tools / "core_incremental.py"))
    first = incremental.controller_digest()
    helper.write_text("second")
    assert incremental.controller_digest() != first


@pytest.mark.parametrize("member", PROOF_SOURCES)
def test_generator_hash_covers_explicit_local_import_closure(tmp_path, monkeypatch, member):
    for name in PROOF_SOURCES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
    monkeypatch.setattr(proof, "__file__", str(tmp_path / "tools/b1_restore_proof.py"))
    expected = digest({name: hashlib.sha256(name.encode()).hexdigest() for name in PROOF_SOURCES})
    assert proof.generator_hash() == expected
    (tmp_path / member).write_text("changed")
    assert proof.generator_hash() != expected


def test_native_fixed_core_guard_rejects_before_program_return(monkeypatch):
    fake = SimpleNamespace(is_file=lambda: True, parents=(), stat=lambda: SimpleNamespace(st_uid=0, st_mode=0o755))
    fake.resolve = lambda **kwargs: fake
    monkeypatch.setattr(binaries, "Path", lambda value: fake)
    monkeypatch.setattr(binaries.os, "access", lambda *args: True)
    trust_hook(monkeypatch, binaries, rejected)
    with pytest.raises(trust.RuntimeTrustRejected, match="VENV_GROUP_OR_OTHER_WRITABLE"):
        binaries.executable(f"/root/zhiming-core-releases/{TARGET}/venv/core/bin/python")


@pytest.mark.parametrize("name", ["systemctl", "pg_dump", "pg_restore"])
def test_system_programs_do_not_scan_core_venv(monkeypatch, name):
    fake = SimpleNamespace(is_file=lambda: True, parents=(), stat=lambda: SimpleNamespace(st_uid=0, st_mode=0o755))
    fake.resolve = lambda **kwargs: fake
    monkeypatch.setattr(binaries, "Path", lambda value: fake)
    monkeypatch.setattr(binaries.os, "access", lambda *args: True)
    trust_hook(monkeypatch, binaries, forbidden)
    assert binaries.executable(name) == str(fake)


def test_charts_interpreter_is_not_a_core_executable_candidate(monkeypatch):
    trust_hook(monkeypatch, binaries, forbidden)
    from tools.core_incremental_contracts import UpgradeRejected

    with pytest.raises(UpgradeRejected, match="HOST_COMMAND_NOT_ALLOWED"):
        binaries.executable(str(ROOT / "venv/charts/bin/python"))
