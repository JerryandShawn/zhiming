"""Holdout integrity only; intentionally contains no classifier accuracy threshold."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "history_holdout_mod.json"
SPACES = {"daily", "career", "relationships", "family", "wellbeing", "finance", "metaphysics"}


@pytest.fixture
def history() -> list[dict[str, object]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_holdout_has_seven_spaces_with_independent_clear_user_coverage(history: list[dict[str, object]]) -> None:
    assert len(history) == len({item["id"] for item in history}) == 98
    clear_user_counts = Counter(
        item["expected_space"] for item in history if item["role"] == "user" and item["clear_assignment"]
    )
    assert set(clear_user_counts) == SPACES
    assert all(count >= 5 for count in clear_user_counts.values())
    assert set(clear_user_counts.values()) == {7}
    assert Counter(item["role"] for item in history) == {"user": 49, "assistant": 49}
    assert len({item["expected_topic"] for item in history}) == 14


def test_holdout_pairs_and_segments_preserve_scope_and_context(history: list[dict[str, object]]) -> None:
    required = {
        "id",
        "role",
        "content",
        "at_ms",
        "owner_id",
        "subject_id",
        "expected_space",
        "expected_topic",
        "clear_assignment",
        "expected_segment",
        "expected_secondary",
    }
    segment_labels: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for index, item in enumerate(history):
        assert set(item) == required
        assert item["owner_id"] == "synthetic-owner"
        assert item["subject_id"] == "synthetic-subject"
        assert isinstance(item["content"], str) and len(item["content"]) > 5
        assert isinstance(item["at_ms"], int) and item["at_ms"] > 0
        assert isinstance(item["clear_assignment"], bool)
        assert item["expected_space"] in SPACES
        assert item["expected_secondary"] in SPACES | {None}
        assert item["expected_secondary"] != item["expected_space"]
        segment_labels[item["expected_segment"]].add((item["expected_space"], item["expected_topic"]))
        if index % 2:
            previous = history[index - 1]
            assert previous["role"] == "user" and item["role"] == "assistant"
            assert previous["expected_segment"] == item["expected_segment"]
            assert previous["at_ms"] < item["at_ms"]
    assert len(segment_labels) == 14
    assert all(len(labels) == 1 for labels in segment_labels.values())
    assert [item["at_ms"] for item in history] == sorted(item["at_ms"] for item in history)
    assert sum(item["expected_secondary"] is not None for item in history) >= 10


def test_holdout_topics_are_separate_from_development_corpus(history: list[dict[str, object]]) -> None:
    development = json.loads(FIXTURE.with_name("history_600.json").read_text(encoding="utf-8"))
    assert {item["content"] for item in history}.isdisjoint({item["content"] for item in development})
    assert {item["expected_topic"] for item in history}.isdisjoint({item["expected_topic"] for item in development})


def test_holdout_frozen_before_implementation_review() -> None:
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
        "223370d1b28cb8eb36ca194126c8e7b09ec86b41dc82195f19fbc13d270ee6d8"
    )
