"""P8 input mapping requires explicit IANA/time basis and exact native fields."""

from copy import deepcopy

import pytest

from mingjing_core.application.charts_natal import P8InputsRequired, natal_request
from mingjing_core.domain.contracts import ScopeError


def snapshot() -> dict:
    return {
        "owner_user_id": "alice",
        "subject_id": "self",
        "revision": 7,
        "profile": {
            "gender": "男",
            "birth.solar_datetime": "1994-03-12T08:20:31.125",
            "birth.location.lng": 104.07,
            "birth.location.lat": 30.67,
            "birth.location.tz": "Asia/Shanghai",
            "birth.clock_basis": "clock",
            "birth.precision": "exact",
        },
    }


def request(value: dict) -> dict:
    return natal_request(value, owner="alice", subject="self", operation_id="native-step", as_of="2026-10-27")


def test_native_fields_are_mapped_exactly_without_changing_source_or_truncating_seconds() -> None:
    value = snapshot()
    before = deepcopy(value)
    result = request(value)
    assert value == before
    assert result["birth"]["reported_time"] == "08:20:31.125000"
    assert result["birth"]["place"] == {"tz": "Asia/Shanghai", "lon": 104.07, "lat": 30.67}
    assert result["birth"]["precision"] == "reported" and result["revision"] == 7
    assert "consent" not in result and result["operation_id"] == "native-step"


@pytest.mark.parametrize(
    "key,value",
    [
        ("birth.location.tz", None),
        ("birth.location.tz", "+08:00"),
        ("birth.location.tz", 8),
        ("birth.clock_basis", None),
        ("birth.clock_basis", "inferred"),
        ("birth.precision", "unknown"),
        ("birth.precision", "interval"),
        ("birth.precision", "approximate"),
        ("birth.solar_datetime", "1994-03-12"),
        ("birth.solar_datetime", "bad"),
        ("birth.solar_datetime", "2099-01-01T10:00"),
        ("birth.time_unknown", True),
        ("birth.time_uncertainty_minutes", 30),
        ("birth.time_uncertainty_minutes", False),
        ("birth.location.lng", float("nan")),
        ("birth.location.lng", True),
        ("birth.location.lat", 91),
        ("birth.location.lat", 90),
        ("gender", "not-confirmed"),
    ],
)
def test_no_inferred_or_ambiguous_birth_values(key: str, value: object) -> None:
    current = snapshot()
    current["profile"][key] = value
    with pytest.raises(P8InputsRequired) as error:
        request(current)
    assert error.value.code == "MISSING_INPUT" and error.value.fields
    assert "1994" not in str(error.value)


def test_conflicted_fact_and_wrong_owner_are_not_used() -> None:
    value = snapshot()
    value["profile_conflicts"] = ["birth.clock_basis"]
    with pytest.raises(P8InputsRequired):
        request(value)
    value["owner_user_id"] = "bob"
    with pytest.raises(ScopeError):
        request(value)
