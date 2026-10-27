"""Keyword-mode throughput only; scaled repetitions are not an independent accuracy set."""

import json
from collections.abc import Callable
from dataclasses import fields, replace
from pathlib import Path

from mingjing_core.organize.contracts import Message
from mingjing_core.organize.engine import OrganizeEngine
from mingjing_core.organize.local_vectors import KeywordVectorizer

ROOT = Path(__file__).resolve().parents[2]


def _messages(copies: int) -> tuple[Message, ...]:
    records = json.loads((ROOT / "tests/v4/organize/fixtures/history_600.json").read_text(encoding="utf-8"))
    allowed = {item.name for item in fields(Message)}
    original = [Message(**{key: value for key, value in record.items() if key in allowed}) for record in records]
    return tuple(
        replace(message, id=f"perf-{batch}-{message.id}", at_ms=message.at_ms + batch * 31 * 86_400_000)
        for batch in range(copies)
        for message in original
    )


def _case(copies: int) -> Callable[[], object]:
    messages = _messages(copies)
    engine = OrganizeEngine(KeywordVectorizer())

    def operation() -> int:
        result = engine.organize(messages)
        assert len(result.message_labels) == len(messages)
        assert len({identity for topic in result.topics for identity in topic.message_ids}) == len(messages)
        return len(result.message_labels)

    return operation


def cases() -> list[tuple[str, Callable[[], object], int]]:
    return [("organize_keyword_600", _case(1), 600), ("organize_keyword_6000_scaled", _case(10), 6000)]
