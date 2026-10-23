"""Compiled synthetic-only schema4 specification; parsing never opens a connection."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tools.core_incremental_contracts import EXPECTED_MANIFEST, MIGRATIONS, TARGET

PROFILE = "b1-bootstrap-replay-fixture-v1"
DSN_ENV = "B1_BOOTSTRAP_OWNER_DSN"
SOURCE_TEXT = "我喜欢合成安静书房"
CASE_TITLE = "合成 B1 撤销事项"
QUESTION = "合成 B1 牌阵问题"
SOURCE_KEY = "b1-bootstrap-source-v1"
OPERATIONS = {"message": "b1-bootstrap-message-v1", "fact": "b1-bootstrap-fact-v1", "case": "b1-bootstrap-case-v1"}
RUN_OPERATION = "b1-bootstrap-run-v1"
DRAW_KEY = "b1-bootstrap-draw-v1"
STAMP = "2026-10-17T02:00:00+00:00"
PRIVATE_CHECKPOINT = "SYNTHETIC_B1_CHECKPOINT_VALUE"
REPLY = "SYNTHETIC_B1_LEGACY_REPLY"
BASE_MESSAGES = {
    ("primary", "message", "synthetic-message"): {
        "content": "synthetic original",
        "role": "user",
        "at": "2026-10-17T02:30:00+00:00",
    },
    ("secondary", "message", "synthetic-secondary"): {"content": "synthetic untouched"},
}
PENDING_IDS = ("b1-bootstrap-sent", "b1-bootstrap-uncertain")
PROTECTED_IDS = ("synthetic-sent", "synthetic-uncertain")
SCHEMA4 = {str(key): MIGRATIONS[str(key)] for key in range(1, 5)}
SPEC = {
    "profile": PROFILE,
    "source": SOURCE_TEXT,
    "case": CASE_TITLE,
    "question": QUESTION,
    "source_key": SOURCE_KEY,
    "operations": OPERATIONS,
    "run_operation": RUN_OPERATION,
    "draw_key": DRAW_KEY,
    "stamp": STAMP,
    "legacy_reply": REPLY,
    "base_ids": [list(key) for key in BASE_MESSAGES],
    "pending_ids": PENDING_IDS,
    "protected_ids": PROTECTED_IDS,
}


class SeedBlocked(RuntimeError):
    """Only fixed codes, never database/provider diagnostics, cross the boundary."""


def require(value: object, code: str) -> None:
    if not value:
        raise SeedBlocked(code)


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def static_ids() -> dict[str, str]:
    source = "msg_" + fingerprint(["primary", "web", SOURCE_KEY, "user"])[:32]
    return {
        "source": source,
        "fact": "fact_" + fingerprint(["primary", source, 0, len(SOURCE_TEXT), "preference", None, None, None])[:32],
        "case": "case_" + fingerprint(["primary", OPERATIONS["case"]])[:32],
    }


def payloads() -> dict[str, dict[str, Any]]:
    ids = static_ids()
    return {
        "source": {
            "thread_id": "life:self",
            "at_ms": int(datetime.fromisoformat(STAMP).timestamp() * 1000),
            "origin_conversation_id": "default",
            "content": SOURCE_TEXT,
            "role": "user",
            "channel": "web",
            "source_id": SOURCE_KEY,
            "external_id": None,
            "conversation_id": "default",
            "case_ids": [],
            "at": STAMP,
            "policy": {"origin": "current_user", "run_context": True},
        },
        "fact": {
            "kind": "preference",
            "content": SOURCE_TEXT,
            "source_refs": [
                {"message_id": ids["source"], "version": 1, "start": 0, "end": len(SOURCE_TEXT), "quote": SOURCE_TEXT}
            ],
            "assertion_status": "user_asserted",
            "consent": "granted",
            "status": "active",
            "field": None,
            "value": None,
            "valid_from": STAMP,
            "valid_to": None,
            "retention": "until_revoked",
        },
        "case": {
            "title": CASE_TITLE,
            "state": {"goal": "", "pending": []},
            "source_refs": [],
            "conversation_id": "default",
            "status": "open",
        },
    }


def scopes(snapshot: dict[str, Any]) -> None:
    require({row["id"] for row in snapshot["owners"]} == {"primary", "secondary"}, "SEED_OWNER_SET")
    require(all(row["settings"] == {"auto_save_low_sensitivity": True} for row in snapshot["owners"]), "SEED_SETTINGS")
    require(
        snapshot["subjects"]
        == [
            {"owner": owner, "id": "self", "label": "synthetic", "consent": "granted"}
            for owner in ("primary", "secondary")
        ],
        "SEED_SUBJECT_SET",
    )


def outbox(snapshot: dict[str, Any], ids: dict[str, str] | None = None) -> None:
    expected_ids = {*PROTECTED_IDS, *(PENDING_IDS if ids else ())}
    require({row["id"] for row in snapshot["outbox"]} == expected_ids, "SEED_RECEIPT_SET")
    for row in snapshot["outbox"]:
        pending = row["id"] in PENDING_IDS
        expected = {
            "owner": "primary",
            "subject": "self",
            "business_id": row["id"],
            "channel": "synthetic",
            "target": "synthetic",
            "run_id": ids["run"] if pending and ids else "synthetic-run",
            "payload": {} if pending else None,
            "dependencies": {} if pending else None,
            "status": "pending" if pending else "sent" if row["id"] == "synthetic-sent" else "uncertain",
            "attempts": 0 if pending else 1,
            "claim_token": None,
            "lease_until": None,
            "receipt": "synthetic-receipt" if row["id"] == "synthetic-sent" else "",
            "error": "",
            "reconciliation": {},
        }
        require(all(row[key] == value for key, value in expected.items()), "SEED_RECEIPT_CONTENT")
        require(
            row["due"] == datetime.fromisoformat(STAMP if pending else "2026-10-17T02:30:00+00:00"), "SEED_RECEIPT_DUE"
        )


@dataclass(frozen=True)
class SeedRequest:
    operation_id: str
    phase: str
    candidate_source: Path
    candidate_python: Path

    def validate(self) -> None:
        require(re.fullmatch(r"b1-[a-z0-9-]{8,70}", self.operation_id), "SEED_OPERATION_ID")
        require(self.phase in {"seed", "withdraw"}, "SEED_PHASE")
        require(self.candidate_source.is_absolute() and self.candidate_python.is_absolute(), "SEED_ABSOLUTE_PATH")

    def dsn(self) -> str:
        require(not any(value for key, value in os.environ.items() if key.startswith("PG")), "SEED_IMPLICIT_PG_ENV")
        try:
            fields = conninfo_to_dict(os.environ.get(DSN_ENV, ""))
        except Exception:
            raise SeedBlocked("SEED_DSN_INVALID") from None
        allowed = {"host", "hostaddr", "port", "dbname", "user", "password", "passfile", "connect_timeout"}
        require(not set(fields) - allowed, "SEED_DSN_OPTIONS")
        require(fields.get("host") in {"127.0.0.1", "::1"}, "SEED_LOOPBACK_ONLY")
        require(not fields.get("hostaddr") or fields["hostaddr"] == fields["host"], "SEED_HOSTADDR")
        require(re.fullmatch(r"b1_application_[0-9a-f]{32}", fields.get("dbname", "")), "SEED_RANDOM_DATABASE")
        require(fields.get("user") == fields["dbname"] + "_owner", "SEED_ROLE")
        require(fields.get("port") in {"55480", "55481"}, "SEED_PORT")
        require(not fields.get("passfile") or fields["passfile"] == os.devnull, "SEED_DSN_OPTIONS")
        return make_conninfo(**dict(fields, hostaddr=fields["host"], passfile=os.devnull, connect_timeout="5"))


def baseline(snapshot: dict[str, Any]) -> None:
    scopes(snapshot)
    require(all(row["revision"] == 0 for row in snapshot["owners"]), "SEED_INITIAL_OWNER_REVISION")
    require(len(snapshot["entities"]) == 2, "SEED_INITIAL_ENTITIES")
    for row in snapshot["entities"]:
        key = (row["owner"], row["kind"], row["id"])
        require(key in BASE_MESSAGES and row["data"] == BASE_MESSAGES[key], "SEED_INITIAL_ENTITIES")
        require(
            row["subject"] == "self" and row["case_id"] is None and row["status"] == "active" and row["revision"] == 1,
            "SEED_INITIAL_ENTITIES",
        )
    require(len(snapshot["runs"]) == 1, "SEED_INITIAL_RUNS")
    run = snapshot["runs"][0]
    require(
        run["id"] == "synthetic-run"
        and run["owner"] == "primary"
        and run["status"] == "succeeded"
        and run["request"] == {}
        and run["result"] is None
        and run["calls"] == 0
        and run["lease_token"] is None
        and run["state_version"] == {}
        and run["checkpoint"] == {}
        and run["subject"] == "self"
        and run["operation_id"] == "synthetic-operation"
        and run["fingerprint"] == "synthetic-fingerprint"
        and run["attempts"] == run["retry_epoch"] == 0
        and run["call_limit"] == 6
        and run["repair_used"] is False
        and run["error"] == ""
        and run["lease_until"] is None,
        "SEED_INITIAL_RUNS",
    )
    outbox(snapshot)
    require(all(not rows for rows in snapshot["other"].values()), "SEED_INITIAL_OTHER_ROWS")


def seeded_entities(snapshot: dict[str, Any], ids: dict[str, str], searchable: Any) -> None:
    rows = {(row["owner"], row["kind"], row["id"]): row for row in snapshot["entities"]}
    require(
        set(rows)
        == {
            *BASE_MESSAGES,
            ("primary", "message", ids["source"]),
            ("primary", "fact", ids["fact"]),
            ("primary", "case", ids["case"]),
        },
        "SEED_ENTITY_SET",
    )
    for key, value in BASE_MESSAGES.items():
        row = rows[key]
        require(
            row["data"] == value
            and row["revision"] == 1
            and row["status"] == "active"
            and row["subject"] == "self"
            and row["case_id"] is None,
            "SEED_LEGACY_ORIGINAL_CHANGED",
        )
    for name, kind in (("source", "message"), ("fact", "fact"), ("case", "case")):
        row, data = rows[("primary", kind, ids[name])], payloads()[name]
        status = data.get("status", "active")
        require(
            row["data"] == searchable(kind, {key: value for key, value in data.items() if key != "status"})
            and row["status"] == status
            and row["revision"] == 1
            and row["subject"] == "self"
            and row["case_id"] is None,
            "SEED_ENTITY_PROVENANCE",
        )
        operation = next(
            (
                item
                for item in snapshot["other"]["core_operations"]
                if item["operation_id"] == OPERATIONS["message" if name == "source" else name]
            ),
            None,
        )
        require(
            operation is not None
            and operation["owner"] == "primary"
            and operation["kind"] == kind
            and operation["result_id"] == ids[name]
            and operation["fingerprint"] == fingerprint([kind, ids[name], "self", None, data]),
            "SEED_OPERATION",
        )


def seeded_runs(snapshot: dict[str, Any], ids: dict[str, str]) -> None:
    require({row["id"] for row in snapshot["runs"]} == {"synthetic-run", ids["run"]}, "SEED_RUN_SET")
    expected_request = {"source_message_id": ids["source"], "fact_ids": [ids["fact"]], "draw_id": ids["draw"]}
    for row in snapshot["runs"]:
        old = row["id"] == "synthetic-run"
        expected = {
            "owner": "primary",
            "subject": "self",
            "status": "succeeded" if old else "failed",
            "request": {"source_message_id": "synthetic-message", "message": "synthetic original"}
            if old
            else expected_request,
            "result": {"answer": REPLY} if old else None,
            "checkpoint": {},
            "calls": 0,
            "call_limit": 6,
            "lease_token": None,
            "lease_until": None,
            "repair_used": False,
            "retry_epoch": 0,
            "attempts": 0 if old else 1,
            "error": "" if old else "SYNTHETIC_FAILED",
            "operation_id": "synthetic-operation" if old else RUN_OPERATION,
            "fingerprint": "synthetic-fingerprint" if old else fingerprint(["self", "standard", expected_request]),
            "state_version": {"versions": {"message:synthetic-message": 1}}
            if old
            else {"versions": {"message:" + ids["source"]: 1, "fact:" + ids["fact"]: 1}, "case_ids": [ids["case"]]},
        }
        require(all(row[key] == value for key, value in expected.items()), "SEED_RUN_PROVENANCE")


def seeded(snapshot: dict[str, Any], ids: dict[str, str], searchable: Any) -> None:
    expected = static_ids()
    require({key: ids.get(key) for key in expected} == expected and set(ids) == {*expected, "draw", "run"}, "SEED_IDS")
    require(re.fullmatch(r"[0-9a-f]{32}", ids["draw"]) and re.fullmatch(r"run_[0-9a-f]{32}", ids["run"]), "SEED_IDS")
    scopes(snapshot)
    require(
        {row["id"]: row["revision"] for row in snapshot["owners"]} == {"primary": 4, "secondary": 0},
        "SEED_OWNER_REVISION",
    )
    seeded_entities(snapshot, ids, searchable)
    seeded_runs(snapshot, ids)
    outbox(snapshot, ids)
    versions = {(r["owner"], r["dependency"]): r["revision"] for r in snapshot["other"]["core_versions"]}
    require(versions == {("primary", "global:self"): 1, ("primary", "case:" + ids["case"]): 2}, "SEED_VERSIONS")
    require(
        {row["operation_id"] for row in snapshot["other"]["core_operations"]} == set(OPERATIONS.values()),
        "SEED_OPERATION_SET",
    )
    draws, requests = snapshot["other"]["tarot_draws"], snapshot["other"]["tarot_requests"]
    require(
        len(draws) == len(requests) == 1
        and draws[0]["id"] == ids["draw"]
        and draws[0]["case_id"] == ids["case"]
        and draws[0]["payload"].get("question") == QUESTION,
        "SEED_DRAW",
    )
    require(
        requests[0]["owner"] == draws[0]["owner"] == "primary"
        and draws[0]["subject"] == "self"
        and draws[0]["stage"] == "open"
        and requests[0]["operation"] == "create"
        and requests[0]["result_type"] == "draw"
        and requests[0]["request_key"] == DRAW_KEY
        and requests[0]["result_id"] == ids["draw"]
        and requests[0]["deleted"] is False,
        "SEED_DRAW_REQUEST",
    )
    for table in set(snapshot["other"]) - {"core_operations", "core_versions", "tarot_draws", "tarot_requests"}:
        require(not snapshot["other"][table], "SEED_OTHER_ROWS")


def receipt(value: dict[str, Any], request: SeedRequest, database: str) -> dict[str, str]:
    require(isinstance(value, dict) and value.get("schema") == "b1-schema4-seed-v1", "SEED_RECEIPT_SCHEMA")
    require(
        set(value)
        == {
            "schema",
            "operation_id",
            "phase",
            "at",
            "database",
            "identity",
            "target",
            "manifest_sha256",
            "profile",
            "spec_sha256",
            "ids",
            "checksums",
            "state_sha256",
            "checkpoints",
            "admissible",
            "real_linux",
            "models",
            "sends",
            "details",
        },
        "SEED_RECEIPT_FIELDS",
    )
    require(
        value.get("operation_id") == request.operation_id
        and value.get("database") == database
        and value.get("target") == TARGET
        and value.get("manifest_sha256") == EXPECTED_MANIFEST
        and value.get("profile") == PROFILE
        and value.get("spec_sha256") == fingerprint(SPEC),
        "SEED_RECEIPT_SCOPE",
    )
    require(value.get("checksums") == SCHEMA4 and value.get("admissible") is False, "SEED_RECEIPT_SCHEMA4")
    require(
        value.get("phase") in {"seed", "withdraw"}
        and value.get("models") == value.get("sends") == 0
        and value.get("real_linux") is False,
        "SEED_RECEIPT_LOCAL_ONLY",
    )
    ids = value.get("ids")
    require(isinstance(ids, dict), "SEED_IDS")
    return ids
