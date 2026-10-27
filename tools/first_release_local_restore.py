"""Explicit native restore into a brand-new local test database; never stage or production."""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psycopg
from psycopg.conninfo import conninfo_to_dict

from tools.first_release_contracts import ReleasePin, RestoreContract, RestoreRejected, read_json, require
from tools.first_release_local_inputs import DumpPin, LocalInputs, file_hash
from tools.first_release_local_pg import new_target, verify_original
from tools.first_release_restore import SafeParser

if TYPE_CHECKING:
    from tools.first_release_candidate_process import CandidatePreflight, CandidateReplay
    from tools.first_release_capture_binding import CaptureBinding
    from tools.first_release_target_proof import TargetProof, TargetProofPin


def process_environment(owner_dsn: str) -> dict[str, str]:
    fields = conninfo_to_dict(owner_dsn)
    result = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    result.update(
        PGPASSFILE=os.devnull,
        PGCONNECT_TIMEOUT="5",
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        OTEL_SDK_DISABLED="true",
        CORE_FEISHU_ENABLED="false",
    )
    if fields.get("password"):
        result["PGPASSWORD"] = fields["password"]
    return result


def run_program(inputs: LocalInputs, arguments: list[str], environment: dict[str, str]) -> bytes:
    require(file_hash(inputs.pg_restore) == inputs.dump_pin.pg_restore_sha256, "REVIEWED_PG_RESTORE_CHANGED")
    try:
        result = subprocess.run(
            [str(inputs.pg_restore), *arguments],
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=180,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RestoreRejected("LOCAL_PG_RESTORE_PROCESS_FAILED") from None
    require(result.returncode == 0, "LOCAL_PG_RESTORE_PROCESS_FAILED")
    return result.stdout


def preflight_program(inputs: LocalInputs, environment: dict[str, str]) -> None:
    version = run_program(inputs, ["--version"], environment)
    require(re.search(rb"PostgreSQL\) 15\.[0-9]+", version), "LOCAL_PG_RESTORE15_REQUIRED")
    listing = run_program(inputs, ["--list", str(inputs.dump)], environment)
    require(
        not re.search(rb"\bcore_model_(?:accounts|usage|batches|authorizations)(?:\b|_)", listing),
        "CENTRAL_LEDGER_ARCHIVE_REJECTED",
    )


def restore_command(inputs: LocalInputs, owner_dsn: str) -> list[str]:
    fields = conninfo_to_dict(owner_dsn)
    return [
        "--host=" + fields["host"],
        "--port=" + fields["port"],
        "--username=" + fields["user"],
        "--dbname=" + fields["dbname"],
        "--no-password",
        "--no-owner",
        "--no-acl",
        "--exit-on-error",
        "--single-transaction",
        str(inputs.dump),
    ]


def _validate_modes(inputs: LocalInputs, apply: bool, upgrade: bool, preflight: Any, replay: Any, capture: Any) -> None:
    require(type(upgrade) is bool and (not upgrade or apply), "LOCAL_UPGRADE_REQUIRES_APPLY")
    if preflight is not None:
        require(apply and upgrade, "PREFLIGHT_REQUIRES_SAME_CALL_APPLY_UPGRADE")
        preflight.validate(inputs)
    if replay is not None:
        from tools.first_release_candidate_process import CandidateReplay

        require(type(replay) is CandidateReplay and preflight is None, "EXPLICIT_REPLAY_PIN_REQUIRED")
        require(apply and upgrade, "REPLAY_REQUIRES_SAME_CALL_APPLY_UPGRADE")
        replay.validate(inputs)
    if capture is not None:
        from tools.first_release_capture_binding import CaptureBinding

        require(type(capture) is CaptureBinding and apply is True, "CAPTURE_BINDING_REQUIRES_SAME_CALL_APPLY")
        capture.validate(inputs)


def _verified_original(inputs: LocalInputs, dsns: dict[str, str], creator: Any, capture: Any) -> dict[str, Any]:
    original = verify_original(inputs, dsns["owner"])
    if capture is not None:
        from tools.first_release_capture_binding import verify_capture_binding

        original["capture_binding"] = verify_capture_binding(capture, inputs, dsns, creator)
    return original


def _target_stages(
    inputs: LocalInputs, dsns: dict[str, str], creator: Any, upgrade: bool, preflight: Any, replay: Any
) -> dict[str, Any]:
    upgraded = {}
    if upgrade:
        from tools.first_release_local_upgrade import _upgrade_new_target

        upgraded = _upgrade_new_target(inputs, dsns, creator)
    if preflight is not None:
        from tools.first_release_candidate_process import candidate_preflight

        upgraded["replay_preflight"] = candidate_preflight(preflight, inputs, dsns, creator)
        upgraded["database_connections"] = 8
    if replay is not None:
        from tools.first_release_candidate_process import candidate_replay

        upgraded["withdrawals_replay"] = candidate_replay(replay, inputs, dsns, creator)
        upgraded["latest_withdrawals_replayed"] = True
        upgraded["database_connections"] = 9
    return upgraded


@contextmanager
def _applied_target(
    inputs: LocalInputs,
    receipt: dict[str, Any],
    *,
    upgrade: bool,
    preflight: Any,
    replay: Any,
    capture: Any,
    environment: Mapping[str, str] | None,
) -> Iterator[Any]:
    dsns = inputs.connections(environment)
    child_environment = process_environment(dsns["owner"])
    preflight_program(inputs, child_environment)
    with new_target(inputs, dsns) as creator:
        # Recheck immutable bytes immediately before the only restore; failure never retries or removes its target.
        require(file_hash(inputs.dump) == inputs.dump_pin.dump_sha256, "REVIEWED_DUMP_CHANGED")
        run_program(inputs, restore_command(inputs, dsns["owner"]), child_environment)
        require(file_hash(inputs.dump) == inputs.dump_pin.dump_sha256, "REVIEWED_DUMP_CHANGED")
        original = _verified_original(inputs, dsns, creator, capture)
        upgraded = _target_stages(inputs, dsns, creator, upgrade, preflight, replay)
        upgraded["database_connections"] = upgraded.get("database_connections", 4) + int(capture is not None)
        yield _restore_receipt(receipt, original, upgraded), dsns, creator


def _restore_receipt(receipt: dict[str, Any], original: dict[str, Any], upgraded: dict[str, Any]) -> dict[str, Any]:
    receipt.pop("mutations", None)
    return {
        **receipt,
        **original,
        "schema": "first-release-local-original-restore-v1",
        "local_pg_restore_completed": True,
        "actual_pg_restore": True,
        "forward_migrations": [],
        "latest_withdrawals_replayed": False,
        "runtime_acl_verified": False,
        "native_restore_completed": False,
        "source_restore_content_verified": False,
        "linux_attestation": False,
        "publication": False,
        "database_connections": 4,
        "created_roles": 2,
        "created_databases": 1,
        "mutation_scope": "new-local-database-only",
        **upgraded,
    }


def execute(
    inputs: LocalInputs,
    *,
    apply_local: bool = False,
    upgrade_local: bool = False,
    replay_preflight: CandidatePreflight | None = None,
    withdrawals_replay: CandidateReplay | None = None,
    capture_binding: CaptureBinding | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    receipt = inputs.validate()
    _validate_modes(inputs, apply_local, upgrade_local, replay_preflight, withdrawals_replay, capture_binding)
    if not apply_local:
        return receipt
    with _applied_target(
        inputs,
        receipt,
        upgrade=upgrade_local,
        preflight=replay_preflight,
        replay=withdrawals_replay,
        capture=capture_binding,
        environment=environment,
    ) as scope:
        return scope[0]


@contextmanager
def _proved_target(
    inputs: LocalInputs,
    *,
    apply_local: bool = False,
    upgrade_local: bool = False,
    capture_binding: CaptureBinding,
    withdrawals_replay: CandidateReplay,
    target_proof_pin: TargetProofPin,
    environment: Mapping[str, str] | None = None,
) -> Iterator[TargetProof]:
    from tools.first_release_target_proof import TargetProofPin, _held_proof

    require(apply_local is True and upgrade_local is True, "TARGET_PROOF_EXPLICIT_APPLY_UPGRADE_REQUIRED")
    require(type(target_proof_pin) is TargetProofPin, "TARGET_PROOF_REVIEW_PIN_REQUIRED")
    receipt = inputs.validate()
    _validate_modes(inputs, apply_local, upgrade_local, None, withdrawals_replay, capture_binding)
    target_proof_pin.validate(inputs, capture_binding, withdrawals_replay)
    with _applied_target(
        inputs,
        receipt,
        upgrade=True,
        preflight=None,
        replay=withdrawals_replay,
        capture=capture_binding,
        environment=environment,
    ) as scope:
        _, dsns, creator = scope
        with _held_proof(inputs, capture_binding, withdrawals_replay, target_proof_pin, dsns, creator) as proof:
            yield proof


def _parser() -> SafeParser:
    parser = SafeParser(description=__doc__)
    for name in ("pin", "contract", "dump-pin", "dump", "pg-restore"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--apply-local", action="store_true")
    parser.add_argument("--upgrade-local", action="store_true")
    parser.add_argument("--replay-preflight-local", action="store_true")
    parser.add_argument("--replay-withdrawals-local", action="store_true")
    parser.add_argument("--capture-bind-local", action="store_true")
    for name in ("capture-inputs", "capture-pin"):
        parser.add_argument("--" + name, type=Path)
    for name in ("preflight-pin", "preflight-ledger", "candidate-python"):
        parser.add_argument("--" + name, type=Path)
    for name in ("replay-pin", "replay-ledger"):
        parser.add_argument("--" + name, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        inputs = LocalInputs(
            ReleasePin.parse(read_json(args.pin)),
            RestoreContract.parse(read_json(args.contract)),
            DumpPin.parse(read_json(args.dump_pin)),
            args.dump,
            args.pg_restore,
            Path.cwd(),
        )
        replay_preflight = withdrawals_replay = None
        fields = (args.candidate_python, args.preflight_ledger, args.preflight_pin)
        if args.replay_withdrawals_local:
            from tools.first_release_candidate_process import CandidateReplay

            require(
                not args.replay_preflight_local and not args.preflight_pin and not args.preflight_ledger,
                "MUTUALLY_EXCLUSIVE_REPLAY_MODE",
            )
            require(args.candidate_python and args.replay_pin and args.replay_ledger, "REPLAY_ARGUMENTS_REQUIRED")
            withdrawals_replay = CandidateReplay.parse(
                args.candidate_python, args.replay_ledger, read_json(args.replay_pin)
            )
        elif args.replay_preflight_local:
            from tools.first_release_candidate_process import CandidatePreflight

            require(all(fields), "PREFLIGHT_ARGUMENTS_REQUIRED")
            replay_preflight = CandidatePreflight.parse(*fields[:2], read_json(fields[2]))
        else:
            require(not any(fields), "PREFLIGHT_ARGUMENTS_WITHOUT_FLAG")
        require(
            args.replay_withdrawals_local or not (args.replay_pin or args.replay_ledger),
            "REPLAY_ARGUMENTS_WITHOUT_FLAG",
        )
        capture = _capture_request(args)
        receipt = execute(
            inputs,
            apply_local=args.apply_local,
            upgrade_local=args.upgrade_local,
            replay_preflight=replay_preflight,
            withdrawals_replay=withdrawals_replay,
            capture_binding=capture,
        )
    except RestoreRejected as error:
        print(json.dumps({"status": "blocked", "code": str(error), "automatic_cleanup": False}))
        return 2
    except (psycopg.Error, OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "blocked", "code": "LOCAL_RESTORE_FAILED_TARGETS_RETAINED"}))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


def _capture_request(args: Any) -> Any:
    from tools.first_release_capture_binding import CaptureBinding

    if args.capture_bind_local:
        require(args.capture_inputs and args.capture_pin, "CAPTURE_ARGUMENTS_REQUIRED")
        return CaptureBinding.parse(args.capture_inputs, read_json(args.capture_pin))
    require(not args.capture_inputs and not args.capture_pin, "CAPTURE_ARGUMENTS_WITHOUT_FLAG")
    return None


if __name__ == "__main__":
    raise SystemExit(main())
