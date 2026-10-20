"""Bounded publication inputs; JSON parameters never replace the brain's review."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path, PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo

from tools.core_incremental_contracts import LIVE_UNITS, PREVIOUS, TARGET, digest

ZONE = ZoneInfo("Asia/Shanghai")
SHA = re.compile(r"[0-9a-f]{64}")
ROOT = "/root/zhiming-core-backups/"
GATE = "/www/wwwroot/p-acme/core-maintenance.flag"
LOCK = "/root/zhiming-core-secrets/core-skill-writer.lock"
MODEL_BASE = "https://api.kimi.com/coding/v1"
ENV_FILES = ("/root/.hermes/.env", "/root/zhiming-core-secrets/live-runtime.env")
SKILL = "/root/.hermes/skills/zhiming"
FILES = tuple("/etc/systemd/system/" + name for name in LIVE_UNITS) + ENV_FILES + (
    SKILL + "/core_consultation.py", SKILL + "/__core_skill_manifest__.json",
)


class PublicationRejected(RuntimeError):
    """Only this fixed public code is allowed to leave the CLI."""


def require(value: object, code: str) -> None:
    if not value:
        raise PublicationRejected(code)


def stamp(value: Any) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise PublicationRejected("PUBLICATION_TIME") from None
    require(result.utcoffset() == timedelta(hours=8), "BEIJING_OFFSET_REQUIRED")
    return result.astimezone(ZONE)


def secure_name(value: Any) -> str:
    require(isinstance(value, str) and value.startswith(ROOT), "OPERATION_PATH")
    path = PurePosixPath(value)
    require(".." not in path.parts and "\\" not in value, "OPERATION_PATH")
    return value


@dataclass(frozen=True)
class Plan:
    raw: dict[str, Any]
    operation_id: str
    hostname: str
    operation_dir: str
    start: datetime
    end: datetime
    written_at: datetime

    @classmethod
    def parse(cls, value: dict[str, Any]) -> Plan:
        expected = {"schema", "operation_id", "scope", "hostname", "target", "previous", "operation_dir",
                    "review_file", "review_sha256", "review_written_at", "window_start", "window_end",
                    "file_sha256", "original_files", "unit_states", "upgrade_receipt", "rollback_proof",
                    "opening_mode"}
        require(isinstance(value, dict) and set(value) == expected, "PUBLICATION_PLAN_FIELDS")
        require(value["schema"] == "b1-publication-plan-v1" and value["scope"] == "live", "PUBLICATION_SCOPE")
        require(value["target"] == TARGET and value["previous"] == PREVIOUS, "PINNED_PUBLICATION")
        require(value["opening_mode"] == "web_then_background", "OPENING_MODE")
        require(re.fullmatch(r"[A-Za-z0-9_-]{8,80}", str(value["operation_id"])), "OPERATION_ID")
        require(re.fullmatch(r"[A-Za-z0-9.-]{1,200}", str(value["hostname"])), "HOST_IDENTITY")
        root = secure_name(value["operation_dir"])
        require(PurePosixPath(root).name == "incremental-" + value["operation_id"], "OPERATION_DIRECTORY")
        start, end, written = (stamp(value[key]) for key in ("window_start", "window_end", "review_written_at"))
        require(start < end and start.date() == end.date() and start.weekday() < 5, "WORKDAY_WINDOW")
        require(time(10) <= start.time() < end.time() <= time(13), "PUBLICATION_WINDOW")
        require(written + timedelta(hours=12) <= start, "REVIEW_ADVANCE_NOTICE")
        require(SHA.fullmatch(str(value["review_sha256"])), "REVIEW_HASH")
        require(secure_name(value["review_file"]).startswith(root + "/"), "REVIEW_PATH")
        validate_files(value, root)
        return cls(value, value["operation_id"], value["hostname"], root, start, end, written)


def validate_files(value: dict[str, Any], root: str) -> None:
    expected = value["file_sha256"]
    originals, states = value["original_files"], value["unit_states"]
    require(isinstance(expected, dict) and set(expected) == set(FILES), "EXACT_PUBLICATION_FILES")
    require(all(isinstance(item, str) and SHA.fullmatch(item) for item in expected.values()), "FILE_HASH")
    require(isinstance(originals, dict) and set(originals) == set(FILES), "EXACT_ORIGINAL_FILES")
    for item in originals.values():
        require(isinstance(item, dict) and set(item) == {"path", "sha256"}, "ORIGINAL_FILE")
        require(secure_name(item["path"]).startswith(root + "/"), "ORIGINAL_BACKUP_PATH")
        require(isinstance(item["sha256"], str) and SHA.fullmatch(item["sha256"]), "ORIGINAL_FILE_HASH")
    require(isinstance(states, dict) and set(states) == set(LIVE_UNITS), "EXACT_UNIT_STATES")
    for item in states.values():
        require(isinstance(item, dict) and set(item) == {"active", "enabled"}, "UNIT_STATE")
        require(all(type(child) is bool for child in item.values()), "UNIT_STATE_TYPE")
    require(states["mingjingtai.service"]["active"] is True, "WEB_MUST_HAVE_BEEN_ACTIVE")
    for key in ("upgrade_receipt", "rollback_proof"):
        record = value[key]
        require(isinstance(record, dict) and set(record) == {"path", "sha256"}, "RECEIPT_FILE")
        require(secure_name(record["path"]).startswith(root + "/"), "RECEIPT_PATH")
        require(isinstance(record["sha256"], str) and SHA.fullmatch(record["sha256"]), "RECEIPT_HASH")


def authorize(plan: Plan, approval: dict[str, Any], action: str, now: datetime, controller: str) -> None:
    require(action in {"verify", "open", "rollback"}, "PUBLICATION_ACTION")
    require(now.utcoffset() is not None, "AWARE_CLOCK_REQUIRED")
    now = now.astimezone(ZONE)
    require(plan.start <= now < plan.end, "OUTSIDE_PUBLICATION_WINDOW")
    expected = {"schema", "operation_id", "scope", "plan_sha256", "controller_sha256", "action",
                "review_sha256", "expires_at", "model_calls", "external_sends"}
    require(isinstance(approval, dict) and set(approval) == expected, "PUBLICATION_APPROVAL_FIELDS")
    require(approval["schema"] == "b1-publication-approval-v1" and approval["scope"] == "live", "APPROVAL_SCOPE")
    require(approval["operation_id"] == plan.operation_id and approval["action"] == action, "APPROVAL_ACTION")
    require(approval["plan_sha256"] == digest(plan.raw), "APPROVAL_PLAN_HASH")
    require(approval["controller_sha256"] == controller, "PUBLICATION_CONTROLLER_HASH")
    require(approval["review_sha256"] == plan.raw["review_sha256"], "APPROVAL_REVIEW_HASH")
    require(now < stamp(approval["expires_at"]) <= plan.end, "APPROVAL_EXPIRED")
    require(all(type(approval[key]) is int and approval[key] == 0 for key in ("model_calls", "external_sends")),
            "PUBLICATION_NO_MODEL_OR_SEND")


def validate_review(plan: Plan, raw: bytes) -> None:
    require(hashlib.sha256(raw).hexdigest() == plan.raw["review_sha256"], "BRAIN_REVIEW_CHANGED")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise PublicationRejected("BRAIN_REVIEW_ENCODING") from None
    require(re.search(r"(?mi)^\s*(?:#+\s*)?(?:\*\*)?结论\s*[:：]\s*(?:\*\*)?Go(?:\*\*)?\s*$", text),
            "BRAIN_REVIEW_NOT_GO")
    require("web_then_background" in text, "NONATOMIC_OPENING_NOT_REVIEWED")
    require(all(plan.raw[key] in text for key in ("review_written_at", "window_start", "window_end")),
            "REVIEW_WINDOW_NOT_BOUND")
    require(TARGET in text and "上线" in text, "REVIEW_PUBLICATION_SCOPE")
    require(re.search(r"(?m)^\s*用户本人已对大脑说[“\"]?上线[”\"]?\s*$", text),
            "USER_PUBLICATION_CONFIRMATION_NOT_REFERENCED")


def controller_hash() -> str:
    root = Path(__file__).parent
    paths = sorted({*root.glob("b1_publication*.py"), *root.glob("core_incremental*.py")})
    rows = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths}
    return digest(rows)
