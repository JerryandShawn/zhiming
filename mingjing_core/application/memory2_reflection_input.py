"""Switch, daily budget, cursor and minimal input for real-model idle reflection (plan 50 §3, §6)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import sql

from mingjing_core.application.agent_tools_policy import CREDENTIAL, sensitivity_categories
from mingjing_core.application.memory import SECRET
from mingjing_core.application.memory2_profile_reflection import checked_profile
from mingjing_core.domain.contracts import CoreError, EvidenceError
from mingjing_core.memory.policy import has_optout
from mingjing_core.memory.private import is_private
from mingjing_core.models.config_policy import ConfigError

SWITCH_ENV = "MEMORY_REFLECTION_MODEL"
MODES = ("scripted", "real")
DAILY_LIMIT = 20
MESSAGE_LIMIT = 40
PROFILE_LIMIT = 30
TASK = "memory2_reflection_real"


def reflection_mode(environment: Mapping[str, str] | None = None) -> str:
    value = (os.environ if environment is None else environment).get(SWITCH_ENV, "scripted")
    if value not in MODES:
        raise ConfigError("MEMORY_REFLECTION_MODEL 只能是 scripted 或 real")
    return value


def memory_enabled(repo: Any, owner: str, subject: str) -> bool:
    # No separate memory toggle exists; turning off low-sensitivity auto-save is the user's "memory off".
    return repo.assert_scope(owner, subject)["settings"].get("auto_save_low_sensitivity", True) is not False


def owner_day(repo: Any, owner: str, subject: str, now: Any) -> str:
    zone = repo.assert_scope(owner, subject)["settings"].get("timezone", "Asia/Shanghai")
    return now.astimezone(ZoneInfo(zone)).date().isoformat()


def budget_id(day: str) -> str:
    return "memory2-reflect-budget:" + day


def cursor_id(thread_id: str) -> str:
    return "memory2-reflect-cursor:" + thread_id


def _runtime_row(repo: Any, owner: str, ident: str) -> dict[str, Any] | None:
    from mingjing_core.domain.contracts import ScopeError

    try:
        return repo.get(owner, "runtime_step", ident)
    except ScopeError:
        return None


def reserve_budget(repo: Any, owner: str, subject: str, day: str, operation_id: str) -> bool:
    """Counts model attempts, not successes; caller holds the owner transaction so reservations serialize."""
    row = _runtime_row(repo, owner, budget_id(day))
    used = row["used"] if row else 0
    if used >= DAILY_LIMIT:
        return False
    data = {"task": "memory2_reflection_budget", "day": day, "used": used + 1, "limit": DAILY_LIMIT}
    if row is None:
        repo.put(
            owner,
            "runtime_step",
            budget_id(day),
            data,
            subject=subject,
            expected_revision=0,
            operation_id=operation_id + ":budget",
        )
    else:
        repo.update(
            owner,
            "runtime_step",
            row["id"],
            data,
            expected_revision=row["revision"],
            operation_id=operation_id + ":budget",
        )
    return True


def read_cursor(repo: Any, owner: str, thread_id: str) -> int:
    row = _runtime_row(repo, owner, cursor_id(thread_id))
    return int(row["through_ms"]) if row else 0


def advance_cursor(repo: Any, owner: str, subject: str, thread_id: str, through_ms: int, operation_id: str) -> None:
    # The cursor carries no source ids, so revoking an original never rewinds it into re-sending older text.
    row = _runtime_row(repo, owner, cursor_id(thread_id))
    data = {"task": "memory2_reflection_cursor", "thread_id": thread_id, "through_ms": through_ms}
    if row is None:
        repo.put(
            owner,
            "runtime_step",
            cursor_id(thread_id),
            data,
            subject=subject,
            expected_revision=0,
            operation_id=operation_id + ":cursor",
        )
    elif int(row["through_ms"]) < through_ms:
        repo.update(
            owner,
            "runtime_step",
            row["id"],
            data,
            expected_revision=row["revision"],
            operation_id=operation_id + ":cursor",
        )


def _new_messages(repo: Any, owner: str, subject: str, thread_id: str, after_ms: int) -> list[dict[str, Any]]:
    with repo.transaction(owner) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT id FROM {} WHERE owner=%s AND kind='message' AND subject=%s AND status='active' "
                "AND data->>'thread_id'=%s AND (data->>'at_ms')::bigint>%s ORDER BY (data->>'at_ms')::bigint, id "
                "LIMIT %s"
            ).format(repo.table("core_entities")),
            (owner, subject, thread_id, after_ms, MESSAGE_LIMIT),
        ).fetchall()
    return [repo.get(owner, "message", row["id"]) for row in rows]


def _withheld(repo: Any, owner: str, message: dict[str, Any]) -> bool:
    content = message.get("content", "")
    policy = message.get("policy", {})
    if message.get("role") != "user" or policy.get("origin") != "current_user":
        return True
    if is_private(message) or policy.get("persist_allowed") is False or has_optout(content):
        return True
    if SECRET.search(content) or CREDENTIAL.search(content):
        return True
    return any(
        row["kind"] == "source_span" and row["metadata"].get("message_id") == message["id"]
        for row in repo.revocations(owner)
    )


def _profile_summary(repo: Any, memory: Any, owner: str, subject: str) -> list[dict[str, Any]]:
    rows = []
    for row in repo.list(owner, "profile_doc", subject=subject):
        if len(rows) >= PROFILE_LIMIT:
            break
        try:
            checked = checked_profile(memory, owner, subject, row["id"])
        except CoreError:
            continue
        rows.append({"section": checked["section"], "text": checked["text"][:200]})
    return rows


def build_input(repo: Any, memory: Any, owner: str, subject: str, thread_id: str) -> dict[str, Any] | None:
    """Only new, active, persistent user originals; sensitive ones go as a bare needs_ask marker."""
    after = read_cursor(repo, owner, thread_id)
    rows = _new_messages(repo, owner, subject, thread_id, after)
    if not rows:
        return None
    sent: list[dict[str, Any]] = []
    for message in rows:
        if _withheld(repo, owner, message):
            continue
        content = message["content"]
        categories = sensitivity_categories(content, content, 0, len(content))
        if categories:
            sent.append({"id": message["id"], "needs_ask": True})
        else:
            sent.append({"id": message["id"], "content": content})
    through = max(int(row["at_ms"]) for row in rows)
    if not any("content" in row for row in sent):
        return {"through_ms": through, "messages": [], "profile": []}
    return {"through_ms": through, "messages": sent, "profile": _profile_summary(repo, memory, owner, subject)}


def require_thread_message(repo: Any, owner: str, subject: str, thread_id: str, message_id: str) -> dict[str, Any]:
    message = repo.get(owner, "message", message_id)
    if message["subject_id"] != subject or message.get("thread_id") != thread_id or message["status"] != "active":
        raise EvidenceError("反思条目的原话已不在本线程或已撤销")
    if _withheld(repo, owner, message):
        raise EvidenceError("反思条目的原话不能用于长期记忆")
    return message
