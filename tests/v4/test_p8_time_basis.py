"""IANA historical clock semantics and published NOAA numeric checks."""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from importlib.resources import files
from pathlib import Path

import pytest

from mingjing_core.adapters.charts import time_basis_zones
from mingjing_core.adapters.charts.time_basis import resolve_birth_instants, solar_time
from mingjing_core.adapters.charts.time_basis_solar import equation_of_time

SHANGHAI = {"tz": "Asia/Shanghai", "lon": 120}
REFERENCE = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "mingjing_core/knowledge/time_basis_noaa_reference.json"
    ).read_text(encoding="utf-8")
)


@pytest.mark.parametrize("day", ["1986-05-04", "1988-04-17", "1991-04-14"])
def test_prc_dst_start_has_gap_not_a_silent_one_hour_shift(day: str) -> None:
    before = resolve_birth_instants(day, "01:59", SHANGHAI, "clock")
    gap = resolve_birth_instants(day, "02:30", SHANGHAI, "clock")
    after = resolve_birth_instants(day, "03:00", SHANGHAI, "clock")
    assert before[0]["offset_minutes"] == 480
    assert gap[0]["status"] == "nonexistent" and gap[0]["utc"] is None
    assert gap[0]["requires_confirmation"]
    assert after[0]["offset_minutes"] == 540 and after[0]["standard"].endswith(
        "02:00:00"
    )
    with pytest.raises(ValueError):
        solar_time(gap[0], 120)


@pytest.mark.parametrize("day", ["1986-09-14", "1988-09-11", "1991-09-15"])
def test_prc_dst_end_returns_both_occurrences_with_distinct_utc(day: str) -> None:
    rows = resolve_birth_instants(day, "01:30", SHANGHAI, "clock")
    assert len(rows) == 2
    assert [row["fold"] for row in rows] == [0, 1]
    assert [row["standard"][-8:] for row in rows] == ["00:30:00", "01:30:00"]
    left, right = [
        datetime.fromisoformat(row["utc"].replace("Z", "+00:00")) for row in rows
    ]
    assert (right - left).total_seconds() == 3600
    assert all(row["requires_confirmation"] for row in rows)


def test_unknown_dst_basis_keeps_clock_and_already_standard_branches() -> None:
    rows = resolve_birth_instants("1988-07-15", "09:30", SHANGHAI, "unknown")
    assert [row["standard"][-8:] for row in rows] == ["08:30:00", "09:30:00"]
    assert [row["assumptions"] for row in rows] == [["clock"], ["already_standard"]]
    assert all(row["requires_confirmation"] for row in rows)


def test_unknown_gap_has_explicit_nonexistent_clock_and_valid_standard_hypothesis() -> (
    None
):
    rows = resolve_birth_instants("1988-04-17", "02:30", SHANGHAI, "unknown")
    assert {row["status"] for row in rows} == {"valid", "nonexistent"}
    valid = next(row for row in rows if row["status"] == "valid")
    assert valid["standard"].endswith("02:30:00") and valid["clock"].startswith(
        "1988-04-17T03:30"
    )


def test_unknown_fold_deduplicates_physical_instants_without_losing_assumptions() -> (
    None
):
    rows = resolve_birth_instants("1988-09-11", "01:30", SHANGHAI, "unknown")
    assert len(rows) == 2 and len({row["utc"] for row in rows}) == 2
    assert rows[1]["assumptions"] == ["clock", "already_standard"]


def test_winter_unknown_basis_collapses_identical_instants() -> None:
    rows = resolve_birth_instants("1988-01-15", "09:30", SHANGHAI, "unknown")
    assert len(rows) == 1 and not rows[0]["requires_confirmation"]
    assert rows[0]["assumptions"] == ["clock", "already_standard"]


@pytest.mark.parametrize("zone", ["Asia/Shanghai", "Asia/Hong_Kong", "Asia/Taipei"])
def test_historical_dst_is_read_from_supplied_zone_not_assumed_plus_eight(
    zone: str,
) -> None:
    day = "1940-07-15" if zone == "Asia/Shanghai" else "1979-07-15"
    row = resolve_birth_instants(day, "09:30", {"tz": zone}, "clock")[0]
    assert row["offset_minutes"] == 540 and row["standard"].endswith("08:30:00")
    assert (
        row["timezone_source"]["iana_version"]
        and len(row["timezone_source"]["zone_sha256"]) == 64
    )
    if day.startswith("1940"):
        assert any("历史时区" in item for item in row["warnings"])


@pytest.mark.parametrize(
    "place", [{}, {"tz": 8}, {"tz": "../Shanghai"}, {"tz": "Unknown/Not_A_Zone"}]
)
def test_missing_or_invalid_historical_timezone_does_not_guess(place: dict) -> None:
    with pytest.raises(ValueError):
        resolve_birth_instants("1988-07-15", "09:30", place, "clock")


@pytest.mark.parametrize("row", REFERENCE["rows"])
def test_equation_of_time_matches_noaa_published_cached_numeric_cells(
    row: dict,
) -> None:
    observed = equation_of_time(
        datetime.fromisoformat(row["utc"].replace("Z", "+00:00"))
    )
    assert abs(observed - row["eot_minutes"]) <= REFERENCE["tolerance_minutes"]


def test_no_double_dst_or_longitude_correction_and_no_input_mutation() -> None:
    original = copy.deepcopy(SHANGHAI)
    row = resolve_birth_instants("1988-07-15", "09:30", SHANGHAI, "clock")[0]
    snapshot = copy.deepcopy(row)
    result = solar_time(row, 120)
    assert result["standard"] == result["mean_solar"] == "1988-07-15T08:30:00"
    assert result["longitude_correction_minutes"] == 0
    assert row == snapshot and original == SHANGHAI


def test_naive_datetime_is_not_an_instant_for_equation_of_time() -> None:
    with pytest.raises(ValueError):
        equation_of_time(datetime(1988, 7, 15, 9, 30))


@pytest.fixture
def unpinned_zone_directory(tmp_path: Path) -> Path:
    target = tmp_path / "Asia" / "Shanghai"
    target.parent.mkdir()
    target.write_bytes(
        files("tzdata.zoneinfo").joinpath("Asia", "Shanghai").read_bytes()
    )
    (tmp_path / "tzdata.zi").write_text(
        "# version unpinned-system-test\n", encoding="utf-8"
    )
    return tmp_path


def test_installed_package_precedes_unpinned_os_tzpath(
    monkeypatch: pytest.MonkeyPatch, unpinned_zone_directory: Path
) -> None:
    import tzdata

    monkeypatch.delenv("PYTHONTZPATH", raising=False)
    monkeypatch.setattr(
        time_basis_zones.zoneinfo, "TZPATH", (str(unpinned_zone_directory),)
    )
    zone, source = time_basis_zones.load_zone("Asia/Shanghai")
    assert zone.key == "Asia/Shanghai"
    assert source["source"] == "tzdata_package"
    assert source["iana_version"] == tzdata.IANA_VERSION
    assert source["tzdata_package_version"] == tzdata.__version__
    assert source["iana_version"] != "unpinned-system-test"


def test_current_explicit_environment_overrides_import_time_search_path(
    monkeypatch: pytest.MonkeyPatch, unpinned_zone_directory: Path
) -> None:
    monkeypatch.setattr(time_basis_zones.zoneinfo, "TZPATH", ())
    monkeypatch.setenv("PYTHONTZPATH", str(unpinned_zone_directory))
    _, source = time_basis_zones.load_zone("Asia/Shanghai")
    assert source["source"] == "explicit_environment_tzpath"
    assert source["iana_version"] == "unpinned-system-test"
    assert source["tzdata_package_version"] is None
    assert "may_differ_from_package_lock" in source["source_limits"]


def test_current_explicit_path_list_is_searched_in_order(
    monkeypatch: pytest.MonkeyPatch, unpinned_zone_directory: Path, tmp_path: Path
) -> None:
    paths = (str(tmp_path / "missing"), str(unpinned_zone_directory))
    monkeypatch.setenv("PYTHONTZPATH", os.pathsep.join(paths))
    _, source = time_basis_zones.load_zone("Asia/Shanghai")
    assert source["source"] == "explicit_environment_tzpath"
    assert source["iana_version"] == "unpinned-system-test"


@pytest.mark.parametrize("relative", ["relative-zone-data", "../zone-data"])
def test_relative_override_is_rejected_instead_of_ignored(
    monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    monkeypatch.setenv("PYTHONTZPATH", relative)
    with pytest.raises(ValueError, match="绝对路径"):
        time_basis_zones.load_zone("Asia/Shanghai")


def test_explicit_nonempty_missing_zone_does_not_silently_select_package(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PYTHONTZPATH", str(tmp_path))
    with pytest.raises(ValueError, match="显式PYTHONTZPATH没有所需时区文件"):
        time_basis_zones.load_zone("Asia/Shanghai")


def test_empty_override_disables_os_data_and_still_allows_package(
    monkeypatch: pytest.MonkeyPatch, unpinned_zone_directory: Path
) -> None:
    monkeypatch.setenv("PYTHONTZPATH", "")
    monkeypatch.setattr(
        time_basis_zones.zoneinfo, "TZPATH", (str(unpinned_zone_directory),)
    )
    _, source = time_basis_zones.load_zone("Asia/Shanghai")
    assert source["source"] == "tzdata_package"
    monkeypatch.setattr(time_basis_zones, "_from_package", lambda _: None)
    with pytest.raises(ValueError, match="没有可用的出生时区数据"):
        time_basis_zones.load_zone("Asia/Shanghai")


def test_last_resort_os_source_is_explicitly_unpinned(
    monkeypatch: pytest.MonkeyPatch, unpinned_zone_directory: Path
) -> None:
    monkeypatch.delenv("PYTHONTZPATH", raising=False)
    monkeypatch.setattr(time_basis_zones, "_from_package", lambda _: None)
    monkeypatch.setattr(
        time_basis_zones.zoneinfo, "TZPATH", (str(unpinned_zone_directory),)
    )
    _, source = time_basis_zones.load_zone("Asia/Shanghai")
    assert source["source"] == "system_unpinned_fallback"
    assert source["iana_version"] == "unpinned-system-test"
    assert source["tzdata_package_version"] is None
    assert "OS_data_unpinned" in source["source_limits"]
    assert "not_established" in source["source_limits"]


def test_no_package_and_no_system_source_does_not_guess_an_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYTHONTZPATH", raising=False)
    monkeypatch.setattr(time_basis_zones, "_from_package", lambda _: None)
    monkeypatch.setattr(time_basis_zones.zoneinfo, "TZPATH", ())
    with pytest.raises(ValueError, match="没有可用的出生时区数据"):
        time_basis_zones.load_zone("Asia/Shanghai")
