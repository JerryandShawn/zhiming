"""Input contract boundaries independent of native chart computation."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from mingjing_core.adapters.charts.benchmarks.handoff_build import BIRTH

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (ROOT / "docs/v4/contracts/synastry.schema.json").read_text(encoding="utf8")
)
REQUEST = {**SCHEMA, "$ref": "#/$defs/Request"}
for _key in ("type", "properties", "required", "additionalProperties"):
    REQUEST.pop(_key, None)


def request() -> dict:
    chart = {
        "owner_user_id": "synthetic-owner-ayuan",
        "subject_id": "synthetic-ayuan",
        "revision": 1,
        "operation_id": "synthetic-ayuan-synastry",
        "birth": deepcopy(BIRTH),
    }
    other = deepcopy(chart)
    other.update(subject_id="synthetic-xiaohe", operation_id="synthetic-xiaohe")
    other["birth"].update(
        date="1995-08-27",
        reported_time="14:10",
        gender="女",
        place={"tz": "Asia/Shanghai", "lon": 120.15, "lat": 30.28},
    )
    return {
        "chart_a": chart,
        "chart_b": other,
        "kind": "romantic",
        "consent": "user_confirmed",
        "as_of_date": "2026-10-21",
    }


@pytest.mark.parametrize("kind", ["romantic", "friendship", "collaboration"])
@pytest.mark.parametrize("orb", [0, 6.0, 10])
def test_schema_accepts_declared_kinds_and_orb_boundaries(
    kind: str, orb: float
) -> None:
    value = request()
    value.update(kind=kind, orb_degrees=orb)
    Draft202012Validator(REQUEST).validate(value)


@pytest.mark.parametrize(
    "consent", [None, "", "yes", True, "pending", "USER_CONFIRMED"]
)
def test_schema_does_not_promote_an_unconfirmed_value_to_consent(consent) -> None:
    value = dict(request(), consent=consent)
    assert list(Draft202012Validator(REQUEST).iter_errors(value))


@pytest.mark.parametrize("key", ["consent", "as_of_date", "chart_a", "chart_b", "kind"])
def test_required_input_has_no_silent_defaults(key: str) -> None:
    value = request()
    del value[key]
    assert list(Draft202012Validator(REQUEST).iter_errors(value))


@pytest.mark.parametrize("basis", ["clock", "standard", "unknown"])
def test_birth_clock_basis_is_not_an_internal_assumption_name(basis: str) -> None:
    value = request()
    value["chart_a"]["birth"]["clock_basis"] = basis
    Draft202012Validator(REQUEST).validate(value)
    value["chart_a"]["birth"]["clock_basis"] = "already_standard"
    assert list(Draft202012Validator(REQUEST).iter_errors(value))


def test_schema_self_validation_and_success_consent_are_explicit() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["$defs"]["Data"]["properties"]["consent"] == {
        "const": "user_confirmed"
    }
    assert SCHEMA["$defs"]["Ziwei"]["properties"]["compatibility_score"] == {
        "const": None
    }
