"""Real approved interpreter observations; no PG, model, network or release authority."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "tools/first_release_controller_runtime.py"
CHILD = r"""
import dataclasses, json, pathlib, socket, sys
value = json.load(sys.stdin)
sys.path.insert(0, value['root'])
if value.get('base_process'):
    sys.path.insert(0, value['site'])
from langgraph.checkpoint import postgres
import importlib.metadata as metadata
import psycopg
from tools.first_release_candidate_process import CandidatePreflight, CandidateReplay
from tools.first_release_contracts import MIGRATIONS, ReleasePin, RestoreRejected
from tools.first_release_incremental import BackupInputs, SourcePin
from tools.first_release_controller_runtime import (
    ControllerRuntimePin, RuntimeWitness, runtime_summary, verified_saver, verify_controller_runtime,
)
def blocked_io(*args, **kwargs):
    raise AssertionError('RUNTIME_GATE_MUST_NOT_CONNECT')
socket.create_connection = blocked_io
socket.socket.connect = blocked_io
psycopg.connect = blocked_io
psycopg.Connection.connect = blocked_io
pin = ControllerRuntimePin.parse(value['pin'])
release = ReleasePin(pin.candidate, pin.manifest_sha256, tuple(sorted(MIGRATIONS.items())),
                     tuple(sorted(value['locks'].items())))
operation = 'fr-' + '1' * 32
source = SourcePin('fr_upgrade_' + '1' * 32, '1234567890123456789', 100, 101, 102,
                   ('synthetic-runtime-owner',), tuple(sorted(MIGRATIONS.items()))[:4])
backup = BackupInputs(operation, release, source, pathlib.Path(value['python']),
                      pathlib.Path(value['python']), pin.python_sha256, pin.python_sha256,
                      (), pathlib.Path(value['workspace']))
preflight = CandidatePreflight(pathlib.Path(value['python']), pathlib.Path(value['workspace']) / 'unused-ledger',
                              tuple(sorted(dict(candidate=pin.candidate, manifest_sha256=pin.manifest_sha256,
                                                python_sha256=pin.python_sha256).items())))
replay = CandidateReplay(preflight, '0' * 64)
def reject(call, expected):
    try:
        call()
    except RestoreRejected as error:
        assert str(error) == expected, (str(error), expected)
    else:
        raise AssertionError('RUNTIME_GATE_UNEXPECTEDLY_OPENED')
def verify(b=backup, r=replay, p=pin, saver=postgres.PostgresSaver):
    return verify_controller_runtime(b, r, p, saver)
mode = value['mode']
if mode == 'success':
    assert sys.version_info[:2] == (3, 11) and sys.prefix != sys.base_prefix
    assert pathlib.Path(sys.executable).resolve() == pathlib.Path(value['python']).resolve()
    assert 'tools.first_release_candidate_process' in sys.modules
    witness = verify()
    result = runtime_summary(witness)
    assert result['active_core_pins'] > 60 and result['active_dependency_edges'] > 100
    assert result['controller_runtime_verified'] is True
    assert verified_saver(witness) is postgres.PostgresSaver
    assert result['database_connections'] == result['model_calls'] == result['external_sends'] == 0
    assert all(result[key] is False for key in (
        'wheel_artifacts_verified', 'supply_chain_verified', 'runtime_verified', 'linux_attestation', 'publication'))
    reject(lambda: RuntimeWitness(), 'CONTROLLER_RUNTIME_WITNESS_REQUIRED')
    reject(lambda: verified_saver(json.loads(json.dumps(result))), 'CONTROLLER_RUNTIME_WITNESS_REQUIRED')
    reject(lambda: verified_saver(object.__new__(RuntimeWitness)), 'CONTROLLER_RUNTIME_WITNESS_REQUIRED')
elif mode == 'interpreter':
    # Exercise the interpreter mismatch rather than a platform-specific base-executable symlink.
    other = dataclasses.replace(preflight, python=pathlib.Path(sys._base_executable).resolve())
    reject(lambda: verify(r=dataclasses.replace(replay, preflight=other)), 'CONTROLLER_ACTUAL_INTERPRETER')
    wrong = '0' * 64
    changed_pin = dataclasses.replace(pin, python_sha256=wrong)
    changed_backup = dataclasses.replace(backup, python_sha256=wrong)
    changed_preflight = dataclasses.replace(
        preflight, pin=tuple(sorted(dict(preflight.pin, python_sha256=wrong).items())))
    reject(lambda: verify(changed_backup, dataclasses.replace(replay, preflight=changed_preflight), changed_pin),
           'CONTROLLER_ACTUAL_INTERPRETER')
    result = {'rejected': 2}
elif mode == 'base':
    assert sys.prefix == sys.base_prefix, 'NEGATIVE_MUST_USE_REAL_BASE_INTERPRETER'
    reject(verify, 'CONTROLLER_ACTUAL_INTERPRETER')
    result = {'rejected': 1}
elif mode == 'saver':
    version = metadata.version('langgraph-checkpoint-postgres')
    class UnreviewedSaver(postgres.PostgresSaver):
        pass
    reject(lambda: verify(saver=UnreviewedSaver), 'CONTROLLER_ACTUAL_SAVER_REQUIRED')
    witness = verify()
    postgres.PostgresSaver.MIGRATIONS.append('SELECT 123456;')
    try:
        reject(lambda: verified_saver(witness), 'CONTROLLER_SAVER_SQL_CHANGED')
    finally:
        postgres.PostgresSaver.MIGRATIONS.pop()
    assert metadata.version('langgraph-checkpoint-postgres') == version == pin.saver_version
    result = {'rejected': 2, 'metadata_unchanged': True}
elif mode == 'closure':
    reject(verify, 'CONTROLLER_DEPENDENCY_CLOSURE')
    result = {'rejected': 1}
else:
    raise AssertionError('UNKNOWN_SYNTHETIC_RUNTIME_CASE')
print(json.dumps(result, sort_keys=True))
"""


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migrations(path):
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(item, ast.Name) and item.id == "MIGRATIONS" for item in node.targets
        ):
            value = ast.literal_eval(node.value)
            assert type(value) is list and all(type(item) is str for item in value)
            return value
    raise AssertionError("REVIEWED_INSTALLED_SAVER_SQL_REQUIRED")


@pytest.fixture
def observed(tmp_path):
    configured = os.environ.get("FIRST_RELEASE_CANDIDATE_TEST_PYTHON")
    fallback = ROOT.parent / "zhiming-v4/.venv-k3/Scripts/python.exe" if os.name == "nt" else Path(sys.executable)
    python = Path(configured) if configured else fallback
    assert python.is_file(), "EXPLICIT_REAL_CORE_LOCKED_VENV_REQUIRED"
    site = (
        python.parent.parent / "Lib/site-packages"
        if os.name == "nt"
        else python.parent.parent / "lib/python3.11/site-packages"
    )
    package = site / "langgraph/checkpoint/postgres"
    sql = migrations(package / "base.py")
    lock = tmp_path / "private" / ("first-incremental-" + "1" * 32) / ("b" * 40) / "requirements-core.lock"
    lock.parent.mkdir(parents=True)
    lock.write_bytes((ROOT / "requirements-core.lock").read_bytes())
    locks = {
        name: sha(ROOT / name)
        for name in ("requirements-core.lock", "requirements-charts.lock", "k3-tokenizer.lock.json")
    }
    pin = dict(
        schema="first-release-controller-runtime-pin-v1",
        candidate="b" * 40,
        manifest_sha256="d" * 64,
        core_lock_sha256=sha(lock),
        controller_sha256=sha(HELPER),
        python_sha256=sha(python),
        saver_version="3.1.2",
        saver_init_sha256=sha(package / "__init__.py"),
        saver_base_sha256=sha(package / "base.py"),
        saver_migrations_sha256=hashlib.sha256(
            json.dumps(sql, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest(),
        saver_migrations_count=len(sql),
    )
    return dict(root=str(ROOT), workspace=str(tmp_path), python=str(python), site=str(site), pin=pin, locks=locks), lock


def child(value, mode, *, base=False):
    payload = dict(value, mode=mode, base_process=base)
    python = Path(value["python"])
    if base:
        config = python.parent.parent / "pyvenv.cfg"
        home = next(
            line.split("=", 1)[1].strip() for line in config.read_text().splitlines() if line.startswith("home")
        )
        python = Path(home) / ("python.exe" if os.name == "nt" else "python3.11")
        assert python.is_file(), "REAL_BASE_INTERPRETER_REQUIRED"
    environment = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    environment.update(
        TZ="Asia/Tokyo",
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        OTEL_SDK_DISABLED="true",
        CORE_FEISHU_ENABLED="false",
    )
    result = subprocess.run(
        [str(python), "-I", "-B", "-X", "pycache_prefix=" + os.path.abspath(os.devnull), "-c", CHILD],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
        env=environment,
        cwd=value["workspace"],
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_real_approved_venv_and_loaded_controller_mint_only_local_witness(observed):
    value, _ = observed
    assert child(value, "success")["controller_runtime_verified"] is True


def test_actual_interpreter_mismatch_hash_and_nonvenv_are_rejected(observed):
    value, _ = observed
    assert child(value, "interpreter") == {"rejected": 2}
    assert child(value, "base", base=True) == {"rejected": 1}


def test_unchanged_metadata_cannot_authorize_replaced_saver_or_live_sql(observed):
    value, _ = observed
    assert child(value, "saver") == {"rejected": 2, "metadata_unchanged": True}


def test_real_dependency_closure_rejects_missing_active_pin_in_synthetic_lock(observed):
    value, lock = observed
    lines, omitted = [], False
    for line in lock.read_text(encoding="utf-8").splitlines(keepends=True):
        if line and not line[0].isspace():
            omitted = line.startswith("annotated-types==")
        if not omitted:
            lines.append(line)
    lock.write_text("".join(lines), encoding="utf-8")
    assert "annotated-types==" not in lock.read_text(encoding="utf-8")
    value["pin"]["core_lock_sha256"] = value["locks"]["requirements-core.lock"] = sha(lock)
    assert child(value, "closure") == {"rejected": 1}
