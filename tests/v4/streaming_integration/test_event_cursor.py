"""Canonical syntax, duplicate detection and explicit agreement have no database side effects."""

from __future__ import annotations

import pytest
from starlette.datastructures import Headers

from mingjing_core.adapters.event_cursor import (
    header_cursors,
    parse_cursor_text,
    resolve_event_cursor,
)
from mingjing_core.domain.contracts import EvidenceError


@pytest.mark.parametrize(
    "text",
    [
        "",
        "01",
        "00",
        "+1",
        "-1",
        "1.0",
        "1e3",
        " 1",
        "1 ",
        "1\n",
        "１２",
        "١",
        True,
        None,
        1,
        "9" * 100,
    ],
)
def test_noncanonical_text_is_never_coerced(text):
    with pytest.raises(EvidenceError, match="事件游标无效") as caught:
        parse_cursor_text(text)
    assert str(caught.value) == "事件游标无效"


def test_canonical_bigint_boundaries():
    assert parse_cursor_text("0") == 0 and parse_cursor_text("1") == 1
    assert parse_cursor_text(str(2**63 - 1)) == 2**63 - 1
    with pytest.raises(EvidenceError, match="事件游标无效"):
        parse_cursor_text(str(2**63))


@pytest.mark.parametrize(
    "header,after,after_seq,expected",
    [
        ([], [], [], 0),
        (["0"], [], [], 0),
        ([], ["0"], ["0"], 0),
        (["7"], [], [], 7),
        ([], ["7"], [], 7),
        ([], [], ["7"], 7),
        (["7"], ["7"], ["7"], 7),
    ],
)
def test_all_supplied_sources_agree(header, after, after_seq, expected):
    assert resolve_event_cursor(header, after=after, after_seq=after_seq) == expected


@pytest.mark.parametrize(
    "header,after,after_seq",
    [(["7"], ["0"], []), (["0"], [], ["7"]), ([], ["7"], ["8"]), (["7"], ["7"], ["0"])],
)
def test_explicit_zero_participates_in_conflicts(header, after, after_seq):
    with pytest.raises(EvidenceError, match="事件游标不一致"):
        resolve_event_cursor(header, after=after, after_seq=after_seq)


@pytest.mark.parametrize("source", ["header", "after", "after_seq"])
@pytest.mark.parametrize("values", [["1", "1"], ["1", "2"], "1", None])
def test_duplicate_or_non_list_sources_are_rejected(source, values):
    options = {"after": (), "after_seq": ()}
    headers = values if source == "header" else ()
    if source != "header":
        options[source] = values
    with pytest.raises(EvidenceError, match="事件游标无效"):
        resolve_event_cursor(headers, **options)


@pytest.mark.parametrize("value", [True, False, "0", 1.0, -1, 2**63])
def test_trusted_internal_cursor_still_requires_exact_integer(value):
    with pytest.raises(EvidenceError, match="事件游标无效"):
        resolve_event_cursor([], trusted_after_seq=value)


def test_trusted_integer_is_consistent_with_header_and_mapping_adapter():
    assert (
        resolve_event_cursor(
            header_cursors({"Last-Event-ID": "7"}), trusted_after_seq=7
        )
        == 7
    )
    assert resolve_event_cursor(header_cursors({"last-event-id": "0"})) == 0
    with pytest.raises(EvidenceError, match="不一致"):
        resolve_event_cursor(["7"], trusted_after_seq=0)


def test_actual_http_header_multimap_keeps_duplicate_evidence():
    headers = Headers(raw=[(b"last-event-id", b"1"), (b"last-event-id", b"1")])
    assert header_cursors(headers) == ["1", "1"]
    with pytest.raises(EvidenceError, match="无效"):
        resolve_event_cursor(header_cursors(headers))
    with pytest.raises(EvidenceError, match="无效"):
        resolve_event_cursor(
            header_cursors({"Last-Event-ID": "1", "last-event-id": "2"})
        )
