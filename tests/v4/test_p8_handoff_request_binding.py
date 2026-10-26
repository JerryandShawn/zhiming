"""The fixed offline fixture cannot be relabeled as another request."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.benchmarks.handoff_refs import (
    claim_id,
    digest,
    document_id,
    resolve,
)
from mingjing_core.adapters.charts.benchmarks.handoff_validate import validate_preview

SAMPLES = Path(__file__).resolve().parents[2] / "docs/v4/contracts/samples"


@pytest.fixture(scope="module")
def samples() -> dict:
    return {
        system: json.loads(
            (SAMPLES / f"ayuan_{system}.json").read_text(encoding="utf-8")
        )
        for system in ("bazi", "ziwei", "astro")
    }


def _request_change(preview: dict, path: tuple[str, ...], value) -> None:
    target = preview["request"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def _rebind(preview: dict, doc: dict) -> None:
    previous = doc["document_id"]
    current = document_id(
        preview["scope"], doc["kind"], doc["source_sha256"], doc["payload"]
    )
    doc["document_id"] = current
    for group in preview["view"].values():
        for ref in group:
            if ref["document_id"] == previous:
                ref["document_id"] = current
    docs = {item["document_id"]: item for item in preview["documents"]}
    for group in preview["aliases"].values():
        for row in group:
            if row["ref"]["document_id"] == previous:
                row["ref"]["document_id"] = current
            ref = row["ref"]
            row["value_sha256"] = digest(
                resolve(docs[ref["document_id"]]["payload"], ref["path"])
            )
            row["claim_id"] = claim_id(row)


@pytest.mark.parametrize("system", ["bazi", "ziwei", "astro"])
def test_unmodified_samples_remain_valid_and_are_not_rewritten(
    samples: dict, system: str
) -> None:
    preview = deepcopy(samples[system])
    before = deepcopy(preview)
    file_before = (SAMPLES / f"ayuan_{system}.json").read_bytes()
    validate_preview(preview, verify_runtime_sources=True)
    assert preview == before
    assert (SAMPLES / f"ayuan_{system}.json").read_bytes() == file_before


@pytest.mark.parametrize("system", ["bazi", "ziwei", "astro"])
@pytest.mark.parametrize(
    "path,bad",
    [
        (("birth", "date"), "1994-03-13"),
        (("birth", "reported_time"), "08:21"),
        (("birth", "place", "tz"), "Asia/Tokyo"),
        (("birth", "clock_basis"), "standard"),
        (("birth", "clock_basis"), "unknown"),
        (("birth", "gender"), "女"),
        (("birth", "place", "lon"), 104.08),
        (("birth", "place", "lat"), -20),
        (("target_date",), "2027-10-19"),
        (("time_scale",), "annual"),
        (("physical_birth_at_utc",), "1994-03-12T01:20:00Z"),
    ],
)
def test_all_request_birth_fields_and_target_are_bound_to_fixed_fixture(
    samples: dict, system: str, path: tuple[str, ...], bad
) -> None:
    preview = deepcopy(samples[system])
    _request_change(preview, path, bad)
    with pytest.raises(ValueError, match="canonical_fixture_request_required"):
        validate_preview(preview)


@pytest.mark.parametrize("system", ["bazi", "ziwei", "astro"])
@pytest.mark.parametrize("field,bad", [("date", "2027-10-19"), ("year", True)])
def test_native_basis_target_is_checked_even_after_document_rehash(
    samples: dict, system: str, field: str, bad
) -> None:
    preview = deepcopy(samples[system])
    doc = next(row for row in preview["documents"] if row["kind"] == "time_basis")
    layers = doc["payload"]["charts"][0]["data"]["p8"]["calendar_layers"]
    if field == "date":
        layers["day"]["date"] = bad
    else:
        layers["requested_gregorian_year"] = bad
    _rebind(preview, doc)
    with pytest.raises(ValueError, match="basis_target_mismatch"):
        validate_preview(preview)


@pytest.mark.parametrize(
    "mutation",
    ["latitude", "longitude", "declared_latitude", "declared_date", "target", "offset"],
)
def test_astro_native_inputs_cannot_diverge_from_request_after_rehash(
    samples: dict, mutation: str
) -> None:
    preview = deepcopy(samples["astro"])
    doc = next(
        row for row in preview["documents"] if row["kind"] == "calculation_bundle"
    )
    profile = next(iter(doc["payload"]["profiles"].values()))
    values = profile["input"]
    if mutation in ("latitude", "longitude"):
        values[mutation] = -20
    elif mutation == "declared_latitude":
        values["declared_birth"]["location"]["lat"] = -20
    elif mutation == "declared_date":
        values["declared_birth"]["solar_datetime"] = "1994-03-13 08:20"
    elif mutation == "target":
        values["target_date"] = "2027-10-19"
    else:
        values["declared_birth"]["timezone_offset"] = 9
    _rebind(preview, doc)
    with pytest.raises(
        ValueError, match="astro_(input_coordinates|declared_input)_mismatch"
    ):
        validate_preview(preview)


@pytest.mark.parametrize(
    "mutation",
    ["progression_target", "return_year", "return_year_bool", "return_latitude"],
)
def test_native_western_timing_target_and_explicit_fixture_location_are_bound(
    samples: dict, mutation: str
) -> None:
    preview = deepcopy(samples["astro"])
    version = (
        "p8-secondary-progressions-v1"
        if mutation == "progression_target"
        else "p8-solar-return-v1"
    )
    doc = next(
        row
        for row in preview["documents"]
        if row["kind"] == "western_timing"
        and row["payload"]["data"]["version"] == version
    )
    data = doc["payload"]["data"]
    if mutation == "progression_target":
        data["actual_UTC"]["target_at"] = "2027-10-19T00:00:00Z"
    elif mutation == "return_latitude":
        data["houses"]["location"]["latitude"] = -20
    else:
        data["return_year"] = True if mutation == "return_year_bool" else 2027
    _rebind(preview, doc)
    with pytest.raises(ValueError):
        validate_preview(preview)
