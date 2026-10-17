"""Withdrawal traverses every derived layer, including incomplete old run lineage."""

from mingjing_core.application.memory import MemoryService


def run(repo, operation, versions):
    value = repo.begin_run("alice", operation, {"message": "合成请求"})
    repo.set_run_dependencies("alice", value["id"], versions, value["lease_token"])
    repo.commit_run(
        "alice",
        value["id"],
        versions,
        {"schema_version": "core3.0", "validation": {"status": "validated"}, "answer": "待撤销的合成回答"},
        value["lease_token"],
    )
    return value


def test_fact_only_withdrawal_propagates_backwards_and_forwards_across_all_layers(p2_repo):
    memory = MemoryService(p2_repo)
    source = memory.receive("alice", content="请记住，我不能上夜班", source_id="original")
    fact = memory.save_fact("alice", "self", source["id"], "我不能上夜班", "constraint")
    # Historical originating run lacks fact-level dependencies: reply lineage is authoritative too.
    first = run(p2_repo, "first", {})
    assistant = memory.record_assistant_message(
        "alice", "self", "life:self", "夜班安排", run_id=first["id"], used_fact_ids=[fact["id"]], channel="web"
    )
    p2_repo.put(
        "alice", "reminder", "last", {"content": "后续安排", "source_ids": ["second-reply"]}, expected_revision=0
    )
    p2_repo.put("alice", "profile_doc", "profile", {"content": "画像", "source_ids": ["note"]}, expected_revision=0)
    p2_repo.put(
        "alice", "thread_summary", "summary", {"content": "摘要", "source_ids": ["profile"]}, expected_revision=0
    )
    p2_repo.put("alice", "note", "note", {"content": "笔记", "source_ids": [assistant["id"]]}, expected_revision=0)
    second = run(p2_repo, "second", {"profile_doc:profile": 1})
    next_reply = memory.record_assistant_message(
        "alice", "self", "life:self", "下一轮回答", run_id=second["id"], channel="web"
    )
    p2_repo.update("alice", "reminder", "last", {"source_ids": [next_reply["id"]]}, expected_revision=1)
    p2_repo.put("alice", "note", "unrelated", {"content": "保留", "source_ids": ["other"]}, expected_revision=0)
    p2_repo.put("bob", "note", "note", {"content": "另一个所有者"}, expected_revision=0)
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"])
    for reply in (assistant, next_reply):
        assert p2_repo.get("alice", "message", reply["id"])["content"] == "〔已删除的内容〕"
    for kind, ident in (
        ("note", "note"),
        ("profile_doc", "profile"),
        ("thread_summary", "summary"),
        ("reminder", "last"),
    ):
        assert p2_repo.get("alice", kind, ident, include_deleted=True)["status"] == "deleted"
    for value in (first, second):
        after = p2_repo.fetch_run("alice", value["id"])
        assert after["status"] == "revoked" and after["result"] is None and after["request"] == {}
    assert p2_repo.get("alice", "note", "unrelated")["content"] == "保留"
    assert p2_repo.get("bob", "note", "note")["content"] == "另一个所有者"


def test_restore_ledger_explicit_note_deletion_seeds_typed_dependencies(p2_repo):
    p2_repo.put("alice", "note", "n", {"content": "原笔记"}, expected_revision=0)
    p2_repo.put("alice", "profile_doc", "p", {"content": "派生画像", "source_ids": ["n"]}, expected_revision=0)
    affected = run(p2_repo, "uses-note", {"note:n": 1})
    ledger = {
        "schema_version": "core3.0",
        "owner_user_id": "alice",
        "revocations": [{"kind": "note", "entity_id": "n", "operation": "deleted", "metadata": {}}],
    }
    p2_repo.apply_privacy("alice", ledger)
    p2_repo.apply_privacy("alice", ledger)
    assert p2_repo.get("alice", "profile_doc", "p", include_deleted=True)["status"] == "deleted"
    assert p2_repo.fetch_run("alice", affected["id"])["result"] is None


def test_correction_invalidates_same_closure_but_preserves_recomputable_request(p2_repo):
    memory = MemoryService(p2_repo)
    source = memory.receive("alice", content="请记住，我不能上夜班", source_id="old")
    fact = memory.save_fact("alice", "self", source["id"], "我不能上夜班", "constraint")
    affected = run(p2_repo, "recompute", {"fact:" + fact["id"]: fact["revision"]})
    newer = memory.receive("alice", content="更正：我现在可以上夜班", source_id="new")
    memory.correct_fact("alice", fact["id"], newer["id"], "更正：我现在可以上夜班", expected_revision=fact["revision"])
    after = p2_repo.fetch_run("alice", affected["id"])
    assert after["status"] == "stale" and after["result"] is None
    assert after["request"]["message"] == "合成请求"


def test_full_source_delete_includes_unlinked_legacy_reply_in_same_closure(p2_repo):
    memory = MemoryService(p2_repo)
    source = memory.receive("alice", content="请记住，我不吃辣", source_id="original")
    fact = memory.save_fact("alice", "self", source["id"], "我不吃辣", "preference")
    legacy = memory.receive(
        "alice", content="旧助手无完整依赖", source_id="legacy", role="assistant", origin="migration"
    )
    p2_repo.update("alice", "message", legacy["id"], {"legacy_derived": True}, expected_revision=legacy["revision"])
    p2_repo.put(
        "alice", "note", "legacy-note", {"content": "旧助手派生", "source_ids": [legacy["id"]]}, expected_revision=0
    )
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
    assert p2_repo.get("alice", "message", legacy["id"], include_deleted=True)["status"] == "deleted"
    assert p2_repo.get("alice", "note", "legacy-note", include_deleted=True)["status"] == "deleted"
