"""Target-year calculations cannot silently reuse a fixed-date professional chart."""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any

import pytest

from mingjing_core.adapters.charts.adapter import stable_id
from mingjing_core.adapters.charts.benchmarks.annual_v2 import annual_basis, annual_view
from mingjing_core.adapters.charts.benchmarks.contexts_v2 import hit_list
from mingjing_core.adapters.charts.benchmarks.engine import P8Engine
from mingjing_core.adapters.charts.benchmarks.protocol_v2 import run_configuration_v2
from mingjing_core.adapters.charts.benchmarks.records import (
    CalculationInputs,
    fingerprint,
)
from mingjing_core.adapters.charts.benchmarks.scripted_v2 import fixtures


def test_professional_chart_configuration_requires_year_aware_provider() -> None:
    def unavailable(_: Any) -> Any:
        raise AssertionError("birth-only professional provider must not be called")

    with pytest.raises(ValueError, match="question_aware_chart_provider"):
        run_configuration_v2(
            [replace(fixtures()[0], source="MingLi-Bench")],
            "C1",
            unavailable,
            unavailable,
            unavailable,
            seed=1,
        )


def test_c0_professional_configuration_still_never_computes_charts() -> None:
    class Provider:
        def __call__(self, _: Any) -> Any:
            raise AssertionError("C0 chart called")

        def for_question(self, _: Any, **kwargs: Any) -> Any:
            raise AssertionError("C0 question chart called")

    result = run_configuration_v2(
        [replace(fixtures()[0], source="BaziQA")],
        "C0",
        Provider(),
        lambda _: {},
        lambda _: "A",
        seed=1,
    )
    assert result["chart_year_binding"] == "no_chart_c0"
    assert result["protocol_stage_calls"] == 1


@pytest.mark.parametrize("year", [None, True, 1500, 2200, "2025"])
def test_annual_convention_rejects_unregistered_or_guessed_years(year: Any) -> None:
    with pytest.raises(ValueError, match="explicit_target_year"):
        annual_basis(year)


def test_annual_view_rejects_bundle_with_wrong_bound_sampling_date() -> None:
    with pytest.raises(ValueError, match="bound_bazi_sampling_date"):
        annual_view(
            {"artifacts": {"a": {"system": "bazi", "target_date": "2026-07-01"}}}, 2025
        )


def _assert_annual(bundle: dict[str, Any], year: int, expected: str) -> None:
    artifact = next(iter(bundle["artifacts"].values()))
    data = artifact["data"]
    assert artifact["target_date"] == f"{year}-07-01"
    assert all(
        profile["input"]["target_date"] == f"{year}-07-01"
        for profile in bundle["profiles"].values()
    )
    assert data["p8"]["calendar_layers"]["year"]["ganzhi"] == expected
    assert set(data["p8"]["calendar_layers"]) == {
        "method",
        "requested_gregorian_year",
        "year",
        "limits",
    }
    assert (
        not {"day", "dayun", "target_month", "target_liuyue", "target_liunian"}
        & data.keys()
    )
    assert "decade_luck" not in data["p8"] and "features" not in bundle
    assert [
        node["id"]
        for node in data["p8"]["time_interactions"]["nodes"]
        if node["id"].startswith("target.")
    ] == ["target.yearly"]
    basis = bundle["benchmark_time_basis"]
    assert basis["sampling_date_is_not_event_date"] is True
    assert basis["event_date"] is basis["event_month"] is basis["event_day"] is None
    assert data["e2_time_basis"] == basis


def test_native_same_birth_target_years_have_distinct_profiles_and_cache() -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured isolated CHART_PYTHON")
    record = fixtures()[0]
    birth_key = fingerprint(record.birth.public_input())
    engine = P8Engine(
        python,
        {birth_key: CalculationInputs(120, 8, "explicit_synthetic_annual_test", True)},
        "2099-01-01",
    )
    rows = [replace(record, text=f"请问{year}年事业如何？") for year in (2024, 2025)]
    bundles = [engine.for_question(row) for row in rows]
    assert len(engine.cache) == 2 and birth_key not in engine.cache
    assert bundles[0] is engine.for_question(rows[0])
    assert set(bundles[0]["profiles"]).isdisjoint(bundles[1]["profiles"])
    for year, expected, bundle in zip(
        (2024, 2025), ("甲辰", "乙巳"), bundles, strict=True
    ):
        _assert_annual(bundle, year, expected)
    changed = replace(record, text="今年事业如何？")
    with pytest.raises(ValueError, match="explicit_target_year"):
        engine.for_question(changed)
    assert len(engine.cache) == 2


def test_native_annual_view_has_content_ids_source_lineage_and_no_input_mutation() -> (
    None
):
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured isolated CHART_PYTHON")
    record = fixtures()[0]
    key = fingerprint(record.birth.public_input())
    engine = P8Engine(
        python,
        {key: CalculationInputs(120, 8, "explicit_synthetic_source", True)},
        "2024-07-01",
    )
    source = engine(record.birth)
    before = fingerprint(source)
    view = annual_view(source, 2024)
    assert fingerprint(source) == before
    old_artifact = next(iter(source["artifacts"].values()))
    old_profile = source["profiles"][old_artifact["profile_id"]]
    artifact = next(iter(view["artifacts"].values()))
    profile = view["profiles"][artifact["profile_id"]]
    assert artifact["id"] != old_artifact["id"] and profile["id"] != old_profile["id"]
    assert artifact["id"] == stable_id(
        "chart-", [profile["id"], artifact["target_date"], artifact["data"]]
    )
    assert set(view["artifacts"]) == {artifact["id"]}
    basis = profile["actual_method"]["e2_annual_view"]
    assert profile["id"] == stable_id(
        "profile-", [basis["method"], {k: v for k, v in profile.items() if k != "id"}]
    )
    assert basis["source_profile_sha256"] == fingerprint(old_profile)
    assert basis["source_artifact_sha256"] == fingerprint(old_artifact)
    assert basis["source_natal_sha256"] == fingerprint(old_artifact["data"]["pillars"])
    assert basis["source_annual_layer_sha256"] == fingerprint(
        old_artifact["data"]["p8"]["calendar_layers"]["year"]
    )
    assert artifact["data"]["pillars"] == old_artifact["data"]["pillars"]
    assert profile["input"] == old_profile["input"]
    hits = hit_list(view)
    assert hits and all(hit["artifact_id"] == artifact["id"] for hit in hits)
