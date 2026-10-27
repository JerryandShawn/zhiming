"""Natural withdrawal cannot use a guessed id, quoted instruction or ambiguous topic."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest

from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.forget_intent import forget_topic
from mingjing_core.repositories.postgres import PostgresRepository

from .test_memory2_withdrawals_pg import seeded as base_seeded


@pytest.fixture(name="seeded")
def natural_seeded(p2_repo: PostgresRepository) -> Iterator[tuple]:
    yield from base_seeded.__wrapped__(p2_repo)


@pytest.mark.parametrize(
    "text,topic",
    [
        ("把我焦虑症的事忘了", "焦虑症"),
        ("把我夜班的信息忘记。", "夜班"),
        ("不要把我焦虑症的事忘了", None),
        ("别忘了我喜欢夜班", None),
        ("“把我焦虑症的事忘了”", None),
        ("假如把我焦虑症的事忘了", None),
        ("把我焦虑症的事忘了？", None),
        ("把我所有信息忘了", "所有信息"),
    ],
)
def test_complete_withdrawal_intent_only(text: str, topic: str | None) -> None:
    assert forget_topic(text) == topic


def test_natural_topic_deletes_the_unique_fact_among_other_retained_facts(seeded: tuple) -> None:
    memory, source, fact, at = seeded
    other = memory.receive(
        "alice", content="请记住，我喜欢合成绿茶", source_id="other-fact", at=at - timedelta(hours=1)
    )
    retained = memory.save_fact("alice", "self", other["id"], "我喜欢合成绿茶", "preference")
    command = memory.receive("alice", content="把我夜班的事忘了", source_id="natural-delete", at=at)
    result = memory.retire_from_message("alice", fact["id"], command["id"], "natural-delete")
    assert result["write_status"] == "deleted"
    assert memory.retire_from_message("alice", fact["id"], command["id"], "natural-delete")["write_status"] == "deleted"
    assert memory.repo.get("alice", "fact", retained["id"])["status"] == "active"
    assert memory.repo.get("alice", "note", "derived-note", include_deleted=True)["status"] == "deleted"


@pytest.mark.parametrize("change", ["ambiguous", "wrong_id", "assistant", "old", "quoted"])
def test_natural_forget_rejects_unproven_target_or_action(seeded: tuple, change: str) -> None:
    memory, _, fact, at = seeded
    extra = memory.receive(
        "alice", content="请记住，我喜欢夜班的安静", source_id="ambiguous", at=at - timedelta(hours=1)
    )
    second = memory.save_fact("alice", "self", extra["id"], "我喜欢夜班的安静", "preference")
    topic = "绿茶" if change == "wrong_id" else "夜班"
    text = f"把我{topic}的事忘了"
    if change == "quoted":
        text = '有人说："' + text + '"'
    command = memory.receive(
        "alice",
        content=text,
        source_id="unsafe-natural",
        role="assistant" if change == "assistant" else "user",
        at=at - timedelta(days=2) if change == "old" else at,
    )
    with pytest.raises((EvidenceError, ScopeError)):
        memory.retire_from_message("alice", fact["id"], command["id"], "unsafe-natural")
    assert memory.repo.get("alice", "fact", fact["id"])["status"] == "active"
    assert memory.repo.get("alice", "fact", second["id"])["status"] == "active"


@pytest.mark.parametrize(
    "text",
    [
        "不要把我夜班的事忘记",
        "把我夜班的事忘记？",
        "假如把我夜班的事忘记",
        "有人说：“把我夜班的事忘记”",
    ],
)
def test_sole_fact_fallback_cannot_turn_denial_question_or_quote_into_deletion(seeded: tuple, text: str) -> None:
    memory, _, fact, at = seeded
    command = memory.receive("alice", content=text, source_id="not-an-action", at=at)
    with pytest.raises(EvidenceError):
        memory.retire_from_message("alice", fact["id"], command["id"], "not-an-action")
    assert memory.repo.get("alice", "fact", fact["id"])["status"] == "active"
