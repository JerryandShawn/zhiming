"""Small synthetic packed candidate and explicit test-owned PG identities."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from tools.first_release_contracts import LOCKS, MIGRATIONS, PROFILE, ReleasePin, RestoreContract

ROOT = Path(__file__).resolve().parents[3]


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def packed_source(workspace: Path) -> tuple[ReleasePin, RestoreContract]:
    ident, candidate = uuid.uuid4().hex, "a" * 40
    root = workspace / "private" / ("first-release-" + ident) / candidate
    root.mkdir(parents=True)
    names = [
        path.relative_to(ROOT).as_posix() for path in (ROOT / "mingjing_core/repositories/migrations").glob("*.sql")
    ]
    names += list(LOCKS)
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    contract = RestoreContract("fr-" + ident, "fr_restore_" + ident, root, local_drill=True)
    return repin(root), contract


def repin(root: Path) -> ReleasePin:
    files = {}
    for path in root.rglob("*"):
        if not path.is_file() or path.name == "__release_manifest__.json":
            continue
        content = path.read_bytes()
        files[path.relative_to(root).as_posix()] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "git_blob_sha1": hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest(),
            "mode": 0o644,
        }
    manifest = root / "__release_manifest__.json"
    write_json(manifest, {"schema": "core3-release-v1", "commit": root.name, "files": files})
    return ReleasePin(
        root.name,
        hashlib.sha256(manifest.read_bytes()).hexdigest(),
        tuple(sorted(MIGRATIONS.items())),
        tuple((name, hashlib.sha256((root / name).read_bytes()).hexdigest()) for name in LOCKS),
    )


def pin_document(pin: ReleasePin) -> dict[str, Any]:
    return {
        "schema": "first-release-pin-v1",
        "profile": PROFILE,
        "candidate": pin.candidate,
        "manifest_sha256": pin.manifest_sha256,
        "migrations": dict(pin.migrations),
        "locks": dict(pin.locks),
    }


def contract_document(contract: RestoreContract) -> dict[str, Any]:
    return {
        "schema": "first-release-restore-contract-v1",
        "operation_id": contract.operation_id,
        "database": contract.database,
        "candidate_source": str(contract.candidate_source),
        "local_drill": contract.local_drill,
    }


def environment(contract: RestoreContract, *, port: str = "55480") -> dict[str, str]:
    return {
        "FIRST_RELEASE_"
        + role.upper()
        + "_DSN": f"host=127.0.0.1 port={port} dbname={contract.database} user={contract.database}_{role}"
        for role in ("owner", "writer")
    }
