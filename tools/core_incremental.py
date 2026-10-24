"""Local controller for an existing Core PG upgrade; no SSH or auto-publication.

The apply API requires an explicit host adapter. Native host integration is kept
separate so an offline test cannot accidentally select a subprocess/PG backend.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from tools.core_incremental_contracts import (
    Request,
    UpgradeRejected,
    authorize,
    digest,
    require,
    validate_backup,
    validate_restore,
    validate_snapshot,
)


class UpgradePort(Protocol):
    def quiesce(self, request: Request) -> AbstractContextManager[None]: ...
    def snapshot(self, request: Request, *, migrated: bool) -> dict[str, Any]: ...
    def backup(self, request: Request, snapshot: dict[str, Any]) -> dict[str, Any]: ...
    def verify_backup_files(self, backup: dict[str, Any]) -> None: ...
    def migrate_and_grant(self, request: Request) -> None: ...
    def backfill(self, request: Request, owner: str, *, apply: bool) -> dict[str, Any]: ...
    def retarget(self, request: Request) -> dict[str, Any]: ...
    def keep_closed(self, request: Request) -> None: ...


def controller_digest() -> str:
    files = sorted(Path(__file__).parent.glob("core_incremental*.py"))
    files.append(Path(__file__).parent / "b1_runtime_trust.py")
    return digest({path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files})


def backfill_owner(port: UpgradePort, request: Request, owner: str, reviewed: dict[str, Any]) -> dict[str, Any]:
    current = port.backfill(request, owner, apply=False)
    require(reviewed.get(owner) == digest(current), "BACKFILL_REVIEW_REQUIRED")
    first = port.backfill(request, owner, apply=True)
    repeat = port.backfill(request, owner, apply=True)
    require(
        first.get("immutable_originals_preserved") is True and repeat.get("immutable_originals_preserved") is True,
        "BACKFILL_ORIGINAL_CHANGED",
    )
    for key in ("message_metadata", "search_tokens", "assistant_created"):
        require(type(repeat.get(key)) is int and repeat[key] == 0, "BACKFILL_NOT_IDEMPOTENT")
    return {
        "owner_sha256": digest(owner),
        "dry_sha256": digest(current),
        "first": first,
        "repeat": repeat,
    }


def execute(
    raw: dict[str, Any],
    approval: dict[str, Any],
    port: UpgradePort,
    *,
    now: datetime,
    action: str,
    backup: dict[str, Any] | None = None,
    restore: dict[str, Any] | None = None,
    migration: dict[str, Any] | None = None,
    reviewed_backfills: dict[str, Any] | None = None,
    controller: str | None = None,
) -> dict[str, Any]:
    request = authorize(raw, approval, controller or controller_digest(), now)
    require(action in {"backup", "migrate", "backfill"}, "ACTION")
    try:
        with port.quiesce(request):
            return apply_locked(
                request,
                approval,
                port,
                action,
                backup,
                restore,
                migration,
                reviewed_backfills,
            )
    finally:
        # Include a partially failed __enter__, cancellation and failed verification.
        port.keep_closed(request)


def migrate_review(
    port: UpgradePort, request: Request, before: dict[str, Any], backup: dict[str, Any]
) -> dict[str, Any]:
    port.migrate_and_grant(request)
    after = port.snapshot(request, migrated=True)
    validate_snapshot(request, after, migrated=True)
    return {
        "status": "quiesced_schema7_review_required",
        "backup_sha256": digest(backup),
        "before_state_sha256": before["state_sha256"],
        "after_state_sha256": after["state_sha256"],
        "review": {owner: digest(port.backfill(request, owner, apply=False)) for owner in request.owners},
        "publication": False,
    }


def apply_locked(
    request: Request,
    approval: dict[str, Any],
    port: UpgradePort,
    action: str,
    backup: dict[str, Any] | None,
    restore: dict[str, Any] | None,
    migration: dict[str, Any] | None,
    reviewed: dict[str, Any] | None,
) -> dict[str, Any]:
    migrated = action == "backfill"
    before = port.snapshot(request, migrated=migrated)
    validate_snapshot(request, before, migrated=migrated)
    if action == "backup":
        saved = port.backup(request, before)
        validate_backup(request, saved, before)
        port.verify_backup_files(saved)
        return {"status": "quiesced_backup_only", "backup": saved, "publication": False}
    require(backup is not None and restore is not None, "BACKUP_AND_RESTORE_REQUIRED")
    baseline = before
    if migrated:
        require(migration is not None, "MIGRATION_RECEIPT_REQUIRED")
        require(approval.get("migration_sha256") == digest(migration), "MIGRATION_RECEIPT_APPROVAL")
        require(migration.get("backup_sha256") == digest(backup), "MIGRATION_BACKUP_BINDING")
        require(migration.get("after_state_sha256") == before.get("state_sha256"), "MIGRATION_STATE_CHANGED")
        baseline = {"state_sha256": migration.get("before_state_sha256")}
    validate_backup(request, backup, baseline)
    port.verify_backup_files(backup)
    require(approval.get("restore_sha256") == digest(restore), "RESTORE_PROOF_APPROVAL")
    validate_restore(request, backup, restore)
    if action == "migrate":
        return migrate_review(port, request, before, backup)
    require(approval.get("backfill_review_sha256") == digest(reviewed), "BACKFILL_REVIEW_APPROVAL")
    rows = [backfill_owner(port, request, owner, reviewed or {}) for owner in request.owners]
    retarget = port.retarget(request)
    require(retarget.get("source_verified") is True and retarget.get("writers_still_stopped") is True, "RETARGET")
    require(request.scope != "live" or retarget.get("hermes_retired_preserved") is True, "HERMES_RETARGET")
    validate_snapshot(request, port.snapshot(request, migrated=True), migrated=True)
    return {
        "status": "quiesced_upgraded",
        "target": request.release,
        "database": request.database,
        "backfills": rows,
        "retarget": retarget,
        "publication": False,
        "model_calls": 0,
        "external_sends": 0,
        "rollback": "forward_schema7_only; no automatic old-package restart or database restore",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--native",
        action="store_true",
        help="Explicit authorized local Linux host adapter; never SSH",
    )
    parser.add_argument("--action", choices=("backup", "migrate", "backfill"), default="backup")
    for name in (
        "approval",
        "host-config",
        "backup",
        "restore",
        "migration",
        "review",
        "output",
    ):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    try:
        raw = json.loads(args.request.read_text(encoding="utf-8"))
        request = Request.parse(raw)
        if args.apply:
            return native_apply(args, raw)
        print(
            json.dumps(
                {
                    "validated_request": True,
                    "database": request.database,
                    "controller_sha256": controller_digest(),
                }
            )
        )
        return 0
    except (Exception, KeyboardInterrupt) as error:
        code = str(error) if isinstance(error, UpgradeRejected) else "INCREMENTAL_ACTION_FAILED"
        print(json.dumps({"ok": False, "code": code, "publication": False}))
        return 2


def native_apply(args: argparse.Namespace, raw: dict[str, Any]) -> int:
    require(
        args.native and args.approval and args.host_config and args.output,
        "EXPLICIT_HOST_ADAPTER_AND_APPROVAL_REQUIRED",
    )
    from mingjing_core.timekit.clock import get_clock
    from tools.core_incremental_files import HostFiles, private_write, regular
    from tools.core_incremental_host import NativePort

    documents = {}
    for key in ("approval", "host_config", "backup", "restore", "migration", "review"):
        path = getattr(args, key)
        if path:
            regular(path, private=True)
            documents[key] = json.loads(path.read_text(encoding="utf-8"))
    request = authorize(raw, documents["approval"], controller_digest(), get_clock().now())
    require(raw.get("host_config_sha256") == digest(documents["host_config"]), "HOST_CONFIG_APPROVAL")
    if args.action in {"migrate", "backfill"}:
        backup, restore = documents.get("backup"), documents.get("restore")
        require(backup is not None and restore is not None, "BACKUP_AND_RESTORE_REQUIRED")
        require(documents["approval"].get("restore_sha256") == digest(restore), "RESTORE_PROOF_APPROVAL")
        validate_restore(request, backup, restore)
    require(HostFiles().root == Path("/"), "NATIVE_ROOT")
    port = NativePort(request, documents["host_config"])
    result = execute(
        raw,
        documents["approval"],
        port,
        now=get_clock().now(),
        action=args.action,
        backup=documents.get("backup"),
        restore=documents.get("restore"),
        migration=documents.get("migration"),
        reviewed_backfills=documents.get("review"),
    )
    private_write(args.output, (json.dumps(result, sort_keys=True) + "\n").encode())
    print(
        json.dumps(
            {
                "status": result["status"],
                "publication": False,
                "receipt_sha256": digest(result),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
