"""Local, opt-in candidate preflight; its reviewed worker never replays business effects."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.first_release_contracts import RestoreRejected, digest, ordinary, read_json, require
from tools.first_release_local_inputs import LocalInputs, file_hash
from tools.first_release_local_upgrade import _require_creator

WORKER = Path(__file__).with_name("first_release_replay_worker.py")
PIN_FIELDS = {"candidate", "manifest_sha256", "dump_sha256", "ledger_sha256", "python_sha256", "worker_sha256"}
BOOTSTRAP = """import hashlib,json,pathlib,runpy,sys
value=json.load(sys.stdin)
path=pathlib.Path(value['worker'])
if hashlib.sha256(path.read_bytes()).hexdigest()!=value['pin']['worker_sha256']:
    raise SystemExit(2)
runpy.run_path(str(path),run_name='__main__',init_globals={'_PREFLIGHT_INPUT':value})
"""


@dataclass(frozen=True)
class CandidatePreflight:
    python: Path
    ledger: Path
    pin: tuple[tuple[str, str], ...]

    @classmethod
    def parse(cls, python: Path, ledger: Path, pin: dict[str, Any]) -> CandidatePreflight:
        require(set(pin) == PIN_FIELDS | {"schema"}, "CANDIDATE_PREFLIGHT_PIN_FIELDS")
        require(pin["schema"] == "first-release-local-preflight-pin-v1", "CANDIDATE_PREFLIGHT_PIN_SCHEMA")
        return cls(python, ledger, tuple(sorted((key, pin[key]) for key in PIN_FIELDS)))

    def validate(self, inputs: LocalInputs) -> dict[str, Any]:
        inputs.validate()
        require(
            type(self.pin) is tuple and all(type(row) is tuple and len(row) == 2 for row in self.pin),
            "IMMUTABLE_PREFLIGHT_PIN",
        )
        pin = dict(self.pin)
        require(set(pin) == PIN_FIELDS and len(self.pin) == len(PIN_FIELDS), "CANDIDATE_PREFLIGHT_PIN_FIELDS")
        require(
            all(digest(value, 40 if key == "candidate" else 64) for key, value in self.pin),
            "CANDIDATE_PREFLIGHT_PIN_DIGEST",
        )
        require(
            (pin["candidate"], pin["manifest_sha256"], pin["dump_sha256"])
            == (inputs.release.candidate, inputs.release.manifest_sha256, inputs.dump_pin.dump_sha256),
            "CANDIDATE_PREFLIGHT_BINDING",
        )
        require(
            self.ledger == inputs.contract.candidate_source.parent / "latest-withdrawals.json", "FIXED_PREFLIGHT_LEDGER"
        )
        for path, expected in (
            (self.python, pin["python_sha256"]),
            (self.ledger, pin["ledger_sha256"]),
            (WORKER, pin["worker_sha256"]),
        ):
            ordinary(path)
            require(file_hash(path) == expected, "PREFLIGHT_REVIEWED_FILE_CHANGED")
        require(os.access(self.python, os.X_OK), "PREFLIGHT_PYTHON_EXECUTABLE_REQUIRED")
        document = read_json(self.ledger)
        require(
            set(document) == {"schema", "owners", "tarot_requests", "deleted_draws", "delivery_receipts"},
            "PREFLIGHT_LEDGER_FIELDS",
        )
        require(document["schema"] == "core3-withdrawals-v2", "PREFLIGHT_LEDGER_SCHEMA")
        require(all(isinstance(document[key], list) for key in document if key != "schema"), "PREFLIGHT_LEDGER_ARRAYS")
        owners = []
        for ledger in document["owners"]:
            require(
                isinstance(ledger, dict) and set(ledger) == {"schema_version", "owner_user_id", "revocations"},
                "PREFLIGHT_OWNER_FIELDS",
            )
            require(
                ledger["schema_version"] == "core3.0" and isinstance(ledger["revocations"], list),
                "PREFLIGHT_OWNER_SCHEMA",
            )
            owners.append(ledger["owner_user_id"])
        require(
            all(isinstance(owner, str) and owner for owner in owners) and len(set(owners)) == len(owners),
            "PREFLIGHT_OWNER_SET",
        )
        manifest = read_json(inputs.contract.candidate_source / "__release_manifest__.json")
        required = {
            "tools/deploy_core.py",
            "tools/deploy_core_withdrawals.py",
            "mingjing_core/repositories/postgres.py",
            "mingjing_core/application/memory.py",
            "mingjing_core/runtime/graph.py",
        }
        require(required <= set(manifest["files"]), "COMPLETE_CANDIDATE_APPLICATION_REQUIRED")
        return document


def _environment(owner_dsn: str) -> dict[str, str]:
    result = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    result.update(
        FIRST_RELEASE_CANDIDATE_OWNER_DSN=owner_dsn,
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        OTEL_SDK_DISABLED="true",
        CORE_FEISHU_ENABLED="false",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
    )
    return result


def _receipt(raw: str, request: CandidatePreflight, inputs: LocalInputs) -> dict[str, Any]:
    try:
        receipt = json.loads(raw)
        fields = {
            "schema",
            "candidate",
            "database",
            "manifest_sha256",
            "python_sha256",
            "worker_sha256",
            "ledger_sha256",
            "core_lock_sha256",
            "active_core_pins",
            "active_dependency_edges",
            "python_version",
            "owners_checked",
            "active_runs",
            "live_leases",
            "central_tables_empty",
            "candidate_modules_checked",
            "database_connections",
            "read_only",
            "mutations",
            "local_preflight_completed",
            "latest_withdrawals_replayed",
            "runtime_verified",
            "native_restore_completed",
            "linux_attestation",
            "publication",
            "model_calls",
            "external_sends",
        }
        require(isinstance(receipt, dict) and set(receipt) == fields, "PREFLIGHT_RECEIPT_INVALID")
        require(receipt["schema"] == "first-release-local-candidate-preflight-v1", "PREFLIGHT_RECEIPT_INVALID")
        require(
            receipt["candidate"] == inputs.release.candidate and receipt["database"] == inputs.contract.database,
            "PREFLIGHT_RECEIPT_BINDING",
        )
        for name in ("manifest_sha256", "python_sha256", "worker_sha256", "ledger_sha256"):
            require(receipt[name] == dict(request.pin)[name], "PREFLIGHT_RECEIPT_BINDING")
        require(
            receipt["read_only"] is True and receipt["database_connections"] == 1 and receipt["mutations"] == 0,
            "PREFLIGHT_RECEIPT_EFFECTS",
        )
        for flag in (
            "runtime_verified",
            "native_restore_completed",
            "linux_attestation",
            "publication",
            "latest_withdrawals_replayed",
        ):
            require(receipt[flag] is False, "PREFLIGHT_RECEIPT_AUTHORITY")
    except (ValueError, TypeError, KeyError):
        raise RestoreRejected("PREFLIGHT_RECEIPT_INVALID") from None
    return receipt


def candidate_preflight(
    request: CandidatePreflight, inputs: LocalInputs, dsns: dict[str, str], creator: Any
) -> dict[str, Any]:
    _require_creator(inputs, dsns, creator)
    document = request.validate(inputs)
    payload = {
        "worker": str(WORKER),
        "python": str(request.python),
        "root": str(inputs.contract.candidate_source),
        "database": inputs.contract.database,
        "pin": dict(request.pin),
        "migrations": dict(inputs.release.migrations),
        "core_lock_sha256": dict(inputs.release.locks)["requirements-core.lock"],
        "owners": sorted(row["owner_user_id"] for row in document["owners"]),
    }
    try:
        result = subprocess.run(
            [str(request.python), "-I", "-B", "-X", "pycache_prefix=" + os.path.abspath(os.devnull), "-c", BOOTSTRAP],
            input=json.dumps(payload),
            env=_environment(dsns["owner"]),
            capture_output=True,
            encoding="utf-8",
            timeout=120,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RestoreRejected("LOCAL_CANDIDATE_PREFLIGHT_PROCESS_FAILED") from None
    if result.returncode:
        # Neither an unexpected bootstrap error nor dependency text may echo private input or stderr.
        try:
            value = json.loads(result.stdout)
        except (ValueError, TypeError):
            value = {}
        if not isinstance(value, dict):
            value = {}
        safe = {
            "PREFLIGHT_PRELOADED_BUSINESS",
            "PREFLIGHT_IMPORT_ORIGIN",
            "PREFLIGHT_SOURCE_CHANGED",
            "PREFLIGHT_CORE_LOCK",
            "PREFLIGHT_DEPENDENCY",
            "PREFLIGHT_RUNTIME",
            "PREFLIGHT_TARGET",
            "PREFLIGHT_OWNER_SET",
            "PREFLIGHT_ACTIVE_RUN",
            "PREFLIGHT_CENTRAL_NOT_EMPTY",
        }
        raise RestoreRejected(value.get("code") if value.get("code") in safe else "LOCAL_CANDIDATE_PREFLIGHT_FAILED")
    receipt = _receipt(result.stdout, request, inputs)
    require(request.validate(inputs) == document, "PREFLIGHT_INPUT_CHANGED_AFTER_PROCESS")
    return receipt
