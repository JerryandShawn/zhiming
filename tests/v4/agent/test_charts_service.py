"""Shared services preserve native legacy data and scope; calculators are injected."""

from __future__ import annotations

from copy import deepcopy

import pytest

from mingjing_core.adapters.charts import ChartAdapter
from mingjing_core.application.charts_projection import chart_diagnostics, public_errors
from mingjing_core.application.charts_service import ChartsService, authorized_archive, verify_calculation_scope
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from tests.test_core_charts import archive, fake_bazi


def factory(owner: str) -> ChartAdapter:
    return ChartAdapter(owner, runner=lambda system, args: fake_bazi(args))


def snapshot() -> dict:
    source = archive()
    return {
        "owner_user_id": "owner-a",
        "subject_id": "self",
        "revision": 7,
        "profile": {
            "gender": source["user"]["gender"],
            "birth.solar_datetime": "2012-05-03 13:18",
            "birth.timezone_offset": 8,
            "birth.precision": "exact",
            "birth.location.lng": 104.07,
            "birth.location.lat": 30.67,
        },
    }


def test_legacy_shared_calculation_is_byte_semantic_equivalent() -> None:
    snap = snapshot()
    expected = factory("owner-a").calculate(
        authorized_archive("owner-a", "self", snap), "2026-10-17", ["bazi"], 7, "self"
    )
    result = ChartsService(factory).calculate("owner-a", "self", snap, "2026-10-17", ["bazi"])
    assert result == expected
    verify_calculation_scope(result, "owner-a", "self", 7)
    evaluated = ChartsService(factory).evaluate(
        "owner-a", "self", snap, "2026-10-17", ["bazi"], topic="general", scale="natal"
    )
    assert evaluated["calculation"]["profiles"]
    assert all(row["owner_user_id"] == "owner-a" for row in evaluated["claims"])


def test_snapshot_scope_cannot_be_replaced_by_model_profile() -> None:
    with pytest.raises(ScopeError):
        authorized_archive("owner-b", "self", snapshot())
    with pytest.raises(ScopeError):
        authorized_archive("owner-a", "other", snapshot())


@pytest.mark.parametrize("group", ["profiles", "artifacts", "features", "branches"])
def test_all_native_results_require_exact_scope_and_revision(group: str) -> None:
    result = ChartsService(factory).calculate("owner-a", "self", snapshot(), "2026-10-17", ["bazi"])
    rows = list(result[group].values()) if isinstance(result[group], dict) else result[group]
    changed = deepcopy(result)
    values = list(changed[group].values()) if isinstance(changed[group], dict) else changed[group]
    assert rows and values
    values[0]["owner_user_id"] = "owner-b"
    with pytest.raises(ScopeError):
        verify_calculation_scope(changed, "owner-a", "self", 7)
    values[0]["owner_user_id"], values[0]["revision"] = "owner-a", True
    with pytest.raises(EvidenceError):
        verify_calculation_scope(changed, "owner-a", "self", 7)


def test_public_diagnostics_never_emit_raw_error_reason_or_paths() -> None:
    errors = [
        {"system": "bazi", "code": "CALCULATION_ERROR", "reason": "PRIVATE-BIRTH-RAW-STDERR"},
        {"system": "attacker", "code": "new", "token": "PRIVATE-TOKEN"},
    ]
    public = public_errors(errors)
    assert "PRIVATE" not in str(public)
    result = {"errors": errors, "profiles": {}, "artifacts": {}}
    assert chart_diagnostics(result, [])["calculation_errors"] == public


@pytest.mark.parametrize("change", ["pointer", "value", "profile", "target", "system"])
def test_native_references_and_requested_intent_are_verified(change: str) -> None:
    result = ChartsService(factory).calculate("owner-a", "self", snapshot(), "2026-10-17", ["bazi"])
    artifact = next(iter(result["artifacts"].values()))
    feature = next(iter(result["features"].values()))
    if change == "pointer":
        feature["path"] = "/data/does_not_exist"
    elif change == "value":
        feature["value"] = {"different": True}
    elif change == "profile":
        artifact["profile_id"] = "missing-profile"
    elif change == "target":
        artifact["target_date"] = "2026-10-18"
    else:
        artifact["system"] = "astro"
    with pytest.raises(EvidenceError):
        verify_calculation_scope(result, "owner-a", "self", 7, target="2026-10-17", system="bazi")
