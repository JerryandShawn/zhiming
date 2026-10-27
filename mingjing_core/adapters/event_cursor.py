"""Canonical cursor syntax and agreement do not grant any event-read authority."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from mingjing_core.domain.contracts import EvidenceError

MAX_CURSOR = 2**63 - 1
CANONICAL = re.compile(r"0|[1-9][0-9]{0,18}")


def parse_cursor_text(value: object) -> int:
    if not isinstance(value, str) or CANONICAL.fullmatch(value) is None:
        raise EvidenceError("事件游标无效")
    result = int(value)
    if result > MAX_CURSOR:
        raise EvidenceError("事件游标无效")
    return result


def header_cursors(headers: Any) -> list[str]:
    getter = getattr(headers, "getlist", None)
    if callable(getter):
        return getter("last-event-id")
    if isinstance(headers, Mapping):
        # Trusted single-value adapters may provide a dict; HTTP uses raw getlist.
        return [
            value
            for name, value in headers.items()
            if isinstance(name, str) and name.lower() == "last-event-id"
        ]
    raise EvidenceError("事件游标无效")


def resolve_event_cursor(
    last_event_ids: Sequence[str],
    *,
    after: Sequence[str] = (),
    after_seq: Sequence[str] = (),
    trusted_after_seq: int | None = None,
) -> int:
    values = []
    for source in (last_event_ids, after, after_seq):
        if not isinstance(source, (list, tuple)) or len(source) > 1:
            raise EvidenceError("事件游标无效")
        if source:
            values.append(parse_cursor_text(source[0]))
    if trusted_after_seq is not None:
        if (
            type(trusted_after_seq) is not int
            or not 0 <= trusted_after_seq <= MAX_CURSOR
        ):
            raise EvidenceError("事件游标无效")
        values.append(trusted_after_seq)
    if values and any(value != values[0] for value in values):
        raise EvidenceError("事件游标不一致")
    return values[0] if values else 0
