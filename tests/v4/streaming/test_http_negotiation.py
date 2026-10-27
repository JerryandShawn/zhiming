"""Explicit JSON opt-in and HTTP quality exclusions are independent of runtime choice."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from mingjing_core.adapters.http_negotiation import NOT_ACCEPTABLE, parse_chat_accept


@pytest.mark.parametrize(
    ("values", "runtime", "expected"),
    [
        ([], "v4", "sse"),
        (["*/*"], "v4", "sse"),
        (["text/event-stream"], "v4", "sse"),
        (["application/json"], "v4", "json"),
        (["APPLICATION/JSON;Q=1"], "v4", "json"),
        (["application/json, text/event-stream"], "v4", "json"),
        (["application/json;q=0.8, text/event-stream;q=1"], "v4", "sse"),
        (["application/json;q=1, text/event-stream;q=0.8"], "v4", "json"),
        (["application/json;q=0, */*"], "v4", "sse"),
        (["application/json;q=1, */*;q=0"], "v4", "json"),
        (["text/event-stream;q=0, text/*;q=1, application/json;q=0.1"], "v4", "json"),
        (["application/json", "text/event-stream"], "v4", "json"),
        (["application/json, text/event-stream"], "v3", "sse"),
        (["application/*, text/*"], "v4", "sse"),
        (["application/vnd.example+json, */*"], "v4", "sse"),
        (["text/event-stream;charset=utf-8"], "v3", "sse"),
    ],
)
def test_chat_representation(values: list[str], runtime: str, expected: str) -> None:
    assert parse_chat_accept(values).representation(runtime) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "application/json;q=NaN",
        "application/json;q=Infinity",
        "application/json;q=-1",
        "application/json;q=1.001",
        "application/json;q=0.0001",
        "application/json;q=.5",
        "application/json;q=0.5;q=0.6",
        "application/json;Q=1;q=1",
        "application/json;q=1;",
        "application/json;q",
        "*/json",
        "app*/json",
        "text/ev*nt-stream",
        "application/json,",
        "x" * 4097,
        ",".join(["text/plain"] * 33),
    ],
)
def test_invalid_accept_is_a_fixed_body_free_406(value: str) -> None:
    with pytest.raises(HTTPException) as caught:
        parse_chat_accept([value])
    assert caught.value.status_code == 406 and caught.value.detail == NOT_ACCEPTABLE
    assert caught.value.headers == {"Vary": "Accept", "Cache-Control": "no-store"}


def test_limits_are_inclusive_and_specific_q0_is_not_revived_by_any_wildcard() -> None:
    boundary = "text/event-stream;extension="
    boundary += "x" * (4096 - len(boundary))
    assert parse_chat_accept([boundary]).representation("v4") == "sse"
    assert (
        parse_chat_accept([",".join(["text/event-stream"] * 32)]).representation("v3")
        == "sse"
    )
    assert (
        parse_chat_accept(["application/json;q=0", "*/*;q=1"]).representation("v4")
        == "sse"
    )
    with pytest.raises(HTTPException):
        parse_chat_accept(
            ["text/event-stream;q=0", "text/*;q=1", "*/*;q=1"]
        ).representation("v4")


@pytest.mark.parametrize(
    ("value", "runtime"),
    [
        ("application/json", "v3"),
        ("application/*", "v4"),
        ("application/vnd.example+json", "v4"),
        ("text/event-stream;q=0, */*;q=1", "v3"),
        ("application/json;q=0, text/event-stream;q=0, */*;q=1", "v4"),
        ("text/plain", "v4"),
    ],
)
def test_unsupported_or_explicitly_excluded_representation(
    value: str, runtime: str
) -> None:
    with pytest.raises(HTTPException) as caught:
        parse_chat_accept([value]).representation(runtime)
    assert caught.value.status_code == 406 and caught.value.detail == NOT_ACCEPTABLE
