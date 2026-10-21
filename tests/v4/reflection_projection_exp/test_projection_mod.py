"""Frozen oracle parity is separate from performance and from source/permission authenticity."""

import copy
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import Any

import pytest

from mingjing_core.application.reflection_projection_exp import (
    SUPPORTED_TYPES,
    ProjectionError,
    project_json,
    projection_fingerprint,
)
from mingjing_core.application.reflection_v3.validation import dataclass_json, digest

from .vectors_mod import DATA, mutable_ids, typed_values, vector


@pytest.mark.parametrize("index", range(1200))
def test_seeded_typed_json_fingerprint_and_independence(index: int) -> None:
    value = vector(index)
    original = copy.deepcopy(value)
    oracle = dataclass_json(value)
    first, second = project_json(value), project_json(value)
    assert first == second == oracle
    assert digest(first) == projection_fingerprint(value) == digest(oracle)
    assert value == original
    assert not mutable_ids(first) & mutable_ids(second)
    assert not mutable_ids(first) & mutable_ids(oracle)
    first["shared"][0][1]["empty"].append(index)
    assert not second["shared"][0][1]["empty"] and not value["shared"][0][1]["empty"]
    assert not first["shared"][1][1]["empty"]
    assert value == original


def test_exact_registered_classes_all_appear_in_frozen_shapes() -> None:
    values = typed_values()
    assert tuple(type(value) for value in values) == SUPPORTED_TYPES
    assert len(SUPPORTED_TYPES) == 22 and DATA["synthetic"] is True and DATA["vector_count"] == 1200
    for value in values:
        assert project_json(value) == dataclass_json(value)


@pytest.mark.parametrize("value", [None, False, True, 0, -1, 1.0, -0.0, [], {}, (), date(2024, 2, 29)])
def test_scalar_types_and_empty_values_are_exact(value: Any) -> None:
    assert project_json(value) == dataclass_json(value)
    assert json.dumps(project_json(value), allow_nan=False) == json.dumps(dataclass_json(value), allow_nan=False)


@pytest.mark.parametrize(
    "value",
    [object(), set(), b"x", MappingProxyType({}), float("nan"), float("inf"), float("-inf"), datetime(2026, 10, 21)],
)
def test_inputs_the_combined_oracle_rejects_are_never_accepted(value: Any) -> None:
    with pytest.raises((TypeError, ValueError, OverflowError, RecursionError)):
        digest(dataclass_json(value))
    with pytest.raises(ProjectionError) as error:
        projection_fingerprint(value)
    assert error.value.reason_code == "experimental_projection_input_invalid"
    assert "x" not in str(error.value)


@pytest.mark.parametrize("kind", [list, dict])
def test_cycles_are_rejected_without_mutation(kind: type) -> None:
    value: Any = [] if kind is list else {}
    if kind is list:
        value.append(value)
    else:
        value["cycle"] = value
    with pytest.raises(RecursionError):
        digest(dataclass_json(value))
    with pytest.raises(ProjectionError):
        project_json(value)
    assert (value[0] if kind is list else value["cycle"]) is value


def test_invalid_unicode_remains_rejected_at_the_fingerprint_boundary() -> None:
    value = "\ud800"
    assert project_json(value) == dataclass_json(value)
    with pytest.raises(UnicodeError):
        digest(dataclass_json(value))
    with pytest.raises(ProjectionError):
        projection_fingerprint(value)


def test_narrower_unknown_dataclass_subclasses_and_nonstr_keys_are_explicit() -> None:
    @dataclass(frozen=True)
    class Unknown:
        value: int

    class StringSubclass(str):
        __slots__ = ()

    for value in (Unknown(1), StringSubclass("synthetic"), {1: "synthetic"}):
        assert digest(dataclass_json(value))
        with pytest.raises(ProjectionError):
            project_json(value)


def test_over_depth_is_a_documented_conservative_rejection() -> None:
    value: Any = None
    for _ in range(70):
        value = [value]
    assert digest(dataclass_json(value))
    with pytest.raises(ProjectionError):
        project_json(value)


def test_utc_representation_uses_the_unchanged_oracle() -> None:
    from datetime import timedelta, timezone

    local = datetime(2026, 10, 21, 8, tzinfo=timezone(timedelta(hours=8)))
    utc = datetime(2026, 10, 21, tzinfo=UTC)
    assert project_json(local) == project_json(utc) == dataclass_json(local) == "2026-10-21T00:00:00+00:00"
