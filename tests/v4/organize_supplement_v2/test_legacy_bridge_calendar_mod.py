"""The fifteen legacy-bridge expectations were frozen before the first product call."""

import os
import socket
from copy import deepcopy
from typing import Any

import pytest
from legacy_bridge_calendar_support_mod import (
    SCOPE,
    fictional_values,
    frozen_cases,
    make_case,
    observed_call,
    protected_fingerprint,
)

from mingjing_core.organize.changes import ChangeSet
from mingjing_core.organize.contracts import Message
from tools.mod_week import completed_regression as runner

CASES = frozen_cases()


@pytest.fixture(autouse=True)
def offline_legacy_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    clean = runner.environment()
    for name in tuple(os.environ):
        if name not in clean:
            monkeypatch.delenv(name, raising=False)
    for name, value in clean.items():
        monkeypatch.setenv(name, value)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("独立旧消息桥验收禁止网络")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


def assert_error_matches(error: Exception, expected: dict[str, Any]) -> None:
    error_type = type(error).__name__
    if "error_type" in expected:
        assert error_type == expected["error_type"]
        assert str(error) == expected["reason"]
    else:
        assert error_type in expected["error_types_exact"]
        assert error_type not in expected["forbidden_error_types"]
        assert str(error).strip()
    values = fictional_values()
    for name in ("source_text", "changed_text", "topic_title"):
        assert values[name] not in str(error)


def assert_preserved_success(result: ChangeSet, document: dict[str, Any], expected: dict[str, Any]) -> None:
    assert result.ops and result.owner_id == SCOPE.owner_id and result.subject_id == SCOPE.subject_id
    assert all(op.collection == expected["operations_collection"] for op in result.ops)
    assert {op.field for op in result.ops} <= set(expected["allowed_changed_fields"])
    projected = deepcopy(document)
    for op in result.ops:
        record = projected["messages"][op.entity_id]
        if op.after.present:
            record[op.field] = op.after.value
        else:
            record.pop(op.field, None)
    before = document["messages"]["synthetic-message-legacy-001"]
    after = projected["messages"]["synthetic-message-legacy-001"]
    assert "revision" not in before and "revision" not in after
    for key, value in before.items():
        if key not in expected["allowed_changed_fields"]:
            assert key in after and after[key] == value
    assert after["space_id"] == "career"


@pytest.mark.parametrize("specification", CASES, ids=[case["id"] for case in CASES])
def test_frozen_legacy_bridge_boundary(specification: dict[str, Any]) -> None:
    case_id = specification["id"]
    case = make_case(case_id)
    before = protected_fingerprint(case)
    if case_id == "LB08":
        record = case.document["messages"]["synthetic-message-legacy-001"]
        with pytest.raises(ValueError):
            Message(**record)
    result = observed_call(case_id, case)
    assert protected_fingerprint(case) == before
    expected = specification["expected"]
    if expected["returns_changeset"]:
        assert isinstance(result, ChangeSet)
        assert_preserved_success(result, case.document, expected)
    else:
        if not isinstance(result, Exception):
            pytest.fail(case_id + " returned a ChangeSet instead of the frozen controlled rejection")
        assert_error_matches(result, expected)
