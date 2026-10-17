"""History windows are precise beyond the old 10,000-created-row boundary."""

from datetime import UTC, datetime, timedelta

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.memory import MemoryService
from mingjing_core.memory.backfill import _run_context
from mingjing_core.memory.history import history_window, sort_key


def test_backfill_prefers_exact_feishu_request_source_and_rejects_cross_subject(p2_repo):
    memory = MemoryService(p2_repo)
    old = memory.receive("alice", content="旧网站问题", source_id="web-old", channel="web")
    p2_repo.bind_channel("alice", "feishu", "synthetic-ou")
    current = memory.receive(
        "alice", content="当前飞书问题", source_id="om-id", channel="feishu", external_id="synthetic-ou"
    )
    value = {
        "subject": "self",
        "operation_id": "feishu:message:om-id",
        "state_version": {"message:" + old["id"]: 1, "message:" + current["id"]: 1},
        "request": {"source_message_id": current["id"], "message": current["content"]},
    }
    assert _run_context(p2_repo, "alice", value, [])[1]["channel"] == "feishu"
    value["request"]["source_message_id"] = old["id"]
    assert _run_context(p2_repo, "alice", value, []) is None
    value["subject"] = "someone-else"
    assert _run_context(p2_repo, "alice", value, []) is None
    value["subject"] = "self"
    value["request"]["source_message_id"] = "missing-original"
    assert _run_context(p2_repo, "alice", value, []) is None


def test_history_after_10001_old_backfilled_replies_preserves_latest_user_and_precise_cursor(p2_repo):
    memory = MemoryService(p2_repo)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    latest = datetime(2026, 10, 17, 10, tzinfo=UTC)
    first = memory.receive(
        "alice", content="最新用户甲", source_id="z", at=latest + timedelta(microseconds=100), conversation_id="current"
    )
    second = memory.receive(
        "alice", content="最新用户乙", source_id="a", at=latest + timedelta(microseconds=900), conversation_id="current"
    )
    with p2_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET created_at=%s WHERE owner='alice'").format(p2_repo.table("core_entities")), (base,)
        )
        with connection.cursor() as cursor:
            cursor.executemany(
                sql.SQL(
                    "INSERT INTO {}(owner,kind,id,subject,case_id,status,data,revision) "
                    "VALUES('alice','message',%s,'self',NULL,'active',%s,1)"
                ).format(p2_repo.table("core_entities")),
                [
                    (
                        f"backfilled-{index:05}",
                        Jsonb(
                            {
                                "content": "旧助手回答",
                                "role": "assistant",
                                "channel": "web",
                                "at": (base + timedelta(seconds=index)).isoformat(),
                                "at_ms": int((base + timedelta(seconds=index)).timestamp() * 1000),
                                "source_id": f"old-{index}",
                                "conversation_id": "current",
                            }
                        ),
                    )
                    for index in range(10001)
                ],
            )
    page = history_window(p2_repo, "alice", "self", "shared", 1, None, "")
    assert page[0]["id"] == second["id"]
    older = history_window(p2_repo, "alice", "self", "shared", 1, sort_key(page[0]), "")
    assert older[0]["id"] == first["id"]
    assert page[0]["cursor"].startswith("2026-10-17T10:00:00.000900")
    assert history_window(p2_repo, "alice", "self", "current", 1, None, "用户甲")[0]["id"] == first["id"]
    assert history_window(p2_repo, "alice", "self", "other-topic", 20, None, "") == []
    assert history_window(p2_repo, "bob", "self", "shared", 20, None, "") == []


def test_unknown_legacy_time_preserves_raw_source_and_uses_created_instant(p2_repo):
    from mingjing_core.timekit.timestamps import history_instant

    memory = MemoryService(p2_repo)
    source = memory.receive(
        "alice", content="合成未知旧时间", source_id="unknown", channel="migration", at="旧时间未知"
    )
    row = history_window(p2_repo, "alice", "self", "shared", 10, None, "")[0]
    assert row["at"] == source["at"] == "旧时间未知"
    assert row["at_ms"] == int(history_instant(source["created_at"]).timestamp() * 1000)
    assert row["cursor"].startswith(history_instant(source["created_at"]).isoformat(timespec="microseconds"))
    assert memory.snapshot("alice")["history"][0]["id"] == source["id"]
