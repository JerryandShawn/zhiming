"""Exercise the real pure pipeline, user edits, stale-source gates and inverse writes."""

import copy
import json
import socket
from dataclasses import asdict, fields, replace
from pathlib import Path

import pytest

from mingjing_core.organize.changes import MemoryChangeStore
from mingjing_core.organize.contracts import Message
from mingjing_core.organize.engine import OrganizeEngine
from mingjing_core.organize.onnx_vectors import configured_vectorizer
from tools.mod_overnight.evaluate_organize import evaluate


def messages() -> list[Message]:
    return [
        Message("m1", "user", "准备跳槽面试和简历", 0, "o", "s"),
        Message("m2", "assistant", "先整理已完成的项目", 1, "o", "s"),
        Message("m3", "user", "我妈最近住院了，需要陪诊", 2, "o", "s"),
        Message("m4", "assistant", "可以安排家人的轮值", 3, "o", "s"),
        Message("m5", "user", "准备考研的复习和考试", 4, "o", "s"),
        Message("m6", "assistant", "先按备考时间拆分", 5, "o", "s"),
    ]


def document(items: list[Message]) -> dict:
    return {
        "owner_id": "o",
        "subject_id": "s",
        "messages": {item.id: asdict(item) for item in items},
        "topics": {},
        "private_untouched": {"nested": [1, None, "合成数据"]},
    }


def test_end_to_end_apply_then_revert_is_field_exact_and_replay_safe() -> None:
    items = messages()
    original = document(items)
    proposal = OrganizeEngine().organize(items)
    assert len(proposal.topics) == 3
    batch = proposal.to_changeset(original, "batch-test")
    assert batch.ops and batch.inverse_ops
    json.dumps(batch.as_dict())
    store = MemoryChangeStore(original)
    changed = store.apply(batch)
    assert changed != original
    assert changed["messages"]["m3"]["space_id"] == "family"
    assert changed["messages"]["m3"]["space_secondary"] == "wellbeing"
    assert changed["messages"]["m3"]["route_confidence"] > 0
    assert store.apply(batch) == changed
    assert store.revert(batch.batch_id) == original
    assert store.revert(batch.batch_id) == original
    assert document(items) == original


def test_rename_move_merge_split_and_ignore_do_not_mutate_source_proposal() -> None:
    proposal = OrganizeEngine().organize(messages())
    initial = proposal.summary()
    career = [topic for topic in proposal.topics if topic.space_id == "career"]
    merged = proposal.merge(tuple(topic.id for topic in career), "工作与复习")
    target = next(topic for topic in merged.topics if topic.title == "工作与复习")
    split = merged.split(target.id, ("m1", "m2"), "面试")
    interview = next(topic for topic in split.topics if topic.title == "面试")
    edited = split.rename(interview.id, "求职准备").move(interview.id, "daily")
    moved = next(topic for topic in edited.topics if topic.title == "求职准备")
    assert moved.space_id == "daily"
    ignored = edited.ignore(moved.id)
    assert set(ignored.ignored_ids) == {"m1", "m2"}
    assert proposal.summary() == initial
    assert set(ident for topic in ignored.topics for ident in topic.message_ids) == {"m3", "m4", "m5", "m6"}
    after = MemoryChangeStore(document(messages())).apply(ignored.to_changeset(document(messages()), "edited"))
    assert "space_id" not in after["messages"]["m1"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("content", "修改后的合成文字"),
        ("revision", 2),
        ("status", "withdrawn"),
        ("owner_id", "other-owner"),
        ("role", "assistant"),
    ],
)
def test_source_changes_since_preview_reject_application(field: str, value: object) -> None:
    proposal = OrganizeEngine().organize(messages())
    state = document(messages())
    state["messages"]["m1"][field] = value
    with pytest.raises(ValueError):
        proposal.to_changeset(state, "stale")


def test_proposal_summary_only_previews_eighty_characters_and_reports_fallback() -> None:
    item = replace(messages()[0], content="面试" * 200)
    proposal = OrganizeEngine().organize([item])
    summary = proposal.summary()
    assert summary["encoder_mode"] == "keyword"
    assert summary["degradation"] == "local_model_not_configured"
    previews = [topic["sample"] for space in summary["spaces"] for topic in space["topics"]]
    assert len(previews[0]) == 80
    assert "面试" * 20 not in repr(proposal)


def test_model_missing_or_remote_looking_path_never_uses_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("organization must not access network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    missing = configured_vectorizer("https://example.invalid/no-download")
    assert missing.mode == "keyword" and missing.degradation == "local_model_files_missing"
    assert OrganizeEngine(missing).organize(messages()).topics


@pytest.mark.parametrize(
    "changes",
    [
        {"incognito": True},
        {"thread_id": "incognito:private"},
        {"retention_scope": "temporary"},
        {"status": "withdrawn"},
    ],
)
def test_explicit_temporary_or_retired_sources_cannot_be_organized(changes: dict) -> None:
    with pytest.raises(ValueError):
        OrganizeEngine().organize([replace(messages()[0], **changes)])


def test_message_repr_hides_body_and_orphan_assistant_cannot_create_user_fact_label() -> None:
    item = replace(messages()[0], content="SYNTHETIC_PRIVATE_MARKER", role="assistant")
    assert "SYNTHETIC_PRIVATE_MARKER" not in repr(item)
    proposal = OrganizeEngine().organize([replace(item, content="用户没有说过的住院信息")])
    assert proposal.needs_review == (item.id,)
    assert proposal.topics[0].space_id == "daily"


def test_600_message_frozen_acceptance_and_no_expected_labels_reach_engine() -> None:
    result = evaluate()
    assert result["messages"] == 600 and result["ground_truth_segments"] == 300
    assert result["space_accuracy"] >= 0.85
    assert result["topic_ari_all"] >= 0.6
    assert result["low_confidence_without_review"] == 0
    assert result["ambiguous_reviewed"] == result["ambiguous_total"] == 120
    assert result["elapsed_seconds"] < 60
    records = json.loads((Path(__file__).parent / "fixtures/history_600.json").read_text(encoding="utf-8"))
    allowed = {field.name for field in fields(Message)}
    raw = [Message(**{key: value for key, value in record.items() if key in allowed}) for record in records]
    before = copy.deepcopy(raw)
    proposal = OrganizeEngine().organize(raw)
    assert raw == before
    assert len({ident for topic in proposal.topics for ident in topic.message_ids}) == 600


@pytest.mark.parametrize("edit", ["empty_rename", "bad_space", "self_merge", "empty_split", "whole_split"])
def test_invalid_edits_fail_closed_without_partial_mutation(edit: str) -> None:
    proposal = OrganizeEngine().organize(messages())
    topic = proposal.topics[0]
    old = proposal.summary()
    calls = {
        "empty_rename": lambda: proposal.rename(topic.id, " "),
        "bad_space": lambda: proposal.move(topic.id, "unknown"),
        "self_merge": lambda: proposal.merge((topic.id, topic.id)),
        "empty_split": lambda: proposal.split(topic.id, (), "x"),
        "whole_split": lambda: proposal.split(topic.id, topic.message_ids, "x"),
    }
    with pytest.raises(ValueError):
        calls[edit]()
    assert proposal.summary() == old
