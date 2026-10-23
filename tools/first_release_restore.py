"""Validate-only core-first-release inputs and optional read-only ACLs; no apply command exists."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tools.first_release_contracts import ReleasePin, RestoreContract, RestoreRejected, read_json
from tools.first_release_source import verify_source


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise RestoreRejected("VALIDATION_ARGUMENTS_REJECTED")


def validate_inputs(pin: ReleasePin, contract: RestoreContract, *, workspace: Path | None = None) -> dict[str, Any]:
    contract.validate_scope(pin, workspace=workspace)
    source = verify_source(contract.candidate_source, pin)
    return {
        **source,
        "schema": "first-release-validation-v1",
        "operation_id": contract.operation_id,
        "database": contract.database,
        "local_drill": contract.local_drill,
        "database_connections": 0,
        "mutations": 0,
        "linux_attestation": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = SafeParser(description=__doc__)
    parser.add_argument("--pin", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--check-acl", action="store_true")
    try:
        args = parser.parse_args(argv)
        pin = ReleasePin.parse(read_json(args.pin))
        contract = RestoreContract.parse(read_json(args.contract))
        receipt = validate_inputs(pin, contract, workspace=Path.cwd())
        if args.check_acl:
            from tools.first_release_acl import verify_database_acl

            receipt["acl"] = verify_database_acl(contract, pin)
            receipt["database_connections"] = 2
    except RestoreRejected as error:
        print(json.dumps({"status": "blocked", "code": str(error)}))
        return 2
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "blocked", "code": "RESTORE_VALIDATION_FAILED"}))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
