"""Independent reference checks fail on drift, missing stars and real mismatch."""

from __future__ import annotations

import json
import os
import subprocess
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mingjing_core.adapters.charts.benchmarks import (
    night28_ziwei_crosscheck as crosscheck,
)
from mingjing_core.adapters.charts.benchmarks.night28_ziwei_reference import (
    ENGLISH_STEMS,
    STAR_NAMES,
    STEMS,
    TABLE,
    day_ganzhi,
    extract_table,
    independent_links,
)

ROOT = Path(__file__).resolve().parents[2]


def source() -> bytes:
    reverse = {value: key for key, value in STAR_NAMES.items()}
    rows = [
        english
        + 'Heavenly:{yinYang:"阳",mutagen:'
        + json.dumps([reverse[name] for name in TABLE[stem]])
        + "}"
        for stem, english in zip(STEMS, ENGLISH_STEMS, strict=True)
    ]
    return ("{" + ",".join(rows) + "}").encode()


def ast() -> SimpleNamespace:
    return SimpleNamespace(
        palaces=[
            SimpleNamespace(
                name=palace, major_stars=[SimpleNamespace(name=name)], minor_stars=[]
            )
            for palace, name in zip(
                ("命宫", "夫妻", "官禄", "财帛"), TABLE["甲"], strict=True
            )
        ]
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2000, 1, 7), "甲子"),
        (date(2000, 1, 1), "戊午"),
        (date(2026, 10, 21), "戊辰"),
    ],
)
def test_independent_day_counter_matches_declared_anchor_and_public_samples(
    value: date, expected: str
) -> None:
    assert day_ganzhi(value) == expected
    assert day_ganzhi(value + timedelta(days=60)) == expected
    assert day_ganzhi(value - timedelta(days=60)) == expected


@pytest.mark.parametrize("value", [None, "2000-01-07", datetime(2000, 1, 7), True])
def test_civil_day_count_does_not_guess_or_accept_a_datetime(value: Any) -> None:
    with pytest.raises(ValueError, match="explicit_civil_date_required"):
        day_ganzhi(value)


def test_source_parser_pins_every_table_cell_and_exact_character_spans() -> None:
    raw = source()
    proof = extract_table(raw)
    assert proof["cells_verified"] == 40
    assert len(proof["sha256"]) == 64
    text = raw.decode()
    for stem, english in zip(STEMS, ENGLISH_STEMS, strict=True):
        row = proof["table"][stem]
        assert row["stars"] == list(TABLE[stem])
        start, end = row["source_character_span"]
        assert text[start:end].startswith(english + "Heavenly:")
        assert "mutagen:" in text[start:end]


@pytest.mark.parametrize(
    "change", ["missing", "duplicate", "wrong_cell", "unknown_star"]
)
def test_changed_or_ambiguous_source_tables_fail_without_silent_fallback(
    change: str,
) -> None:
    raw = source()
    if change == "missing":
        raw = raw.replace(b"jiaHeavenly", b"changedHeavenly")
    elif change == "duplicate":
        raw += raw
    elif change == "wrong_cell":
        raw = raw.replace(b"lianzhenMaj", b"pojunMaj", 1)
    else:
        raw = raw.replace(b"lianzhenMaj", b"UNKNOWN_STAR", 1)
    with pytest.raises(ValueError, match="reference_"):
        extract_table(raw)


def test_independent_scan_preserves_missing_and_duplicate_star_evidence() -> None:
    data = ast()
    actual = independent_links(data, date(2000, 1, 7))
    assert all(row["status"] == "resolved" for row in actual)
    data.palaces[0].major_stars.append(SimpleNamespace(name="廉贞"))
    data.palaces[1].major_stars.clear()
    result = independent_links(data, date(2000, 1, 7))
    assert result[0]["status"] == "ambiguous" and len(result[0]["locations"]) == 2
    assert result[1]["status"] == "missing" and result[1]["locations"] == []
    assert result[2:] == actual[2:]


def test_crosscheck_records_mismatch_without_changing_the_question_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = ast()
    day = date(2000, 1, 7)
    links = independent_links(original, day)
    changed = deepcopy(links)
    changed[0]["star"] = "天府"
    monkeypatch.setattr(
        crosscheck,
        "ziwei_day",
        lambda prepared, target: {
            "horoscope": {"daily": {"ganzhi": "乙丑"}},
            "transformations": {"daily": {"links": changed}},
        },
    )
    report = crosscheck.compare_days(SimpleNamespace(ziwei_ast=original), [day])
    assert report["difference_count"] == 1 and report["dates"] == 1
    row = report["differences"][0]
    assert row["date"] == "2000-01-07"
    assert row["reference_ganzhi"] == "甲子" and row["actual_ganzhi"] == "乙丑"
    assert row["reference"] == links


def test_duplicate_targets_cannot_inflate_the_crosscheck_denominator() -> None:
    with pytest.raises(ValueError, match="duplicate_target_dates"):
        crosscheck.compare_days(None, [date(2000, 1, 7)] * 2)


def test_fixed_sample_covers_a_leap_day_all_ten_stems_and_the_requested_week() -> None:
    dates = crosscheck.target_days()
    assert dates == sorted(dates) and len(dates) == len(set(dates)) == 1000
    assert dates == crosscheck.target_days()
    assert date(1988, 2, 29) in dates
    assert all(date(2026, 10, day) in dates for day in range(21, 28))
    assert {day_ganzhi(day)[0] for day in dates} == set(STEMS)


def test_actual_isolated_crosscheck_uses_one_thousand_dates_and_pinned_source(
    tmp_path: Path,
) -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    env = {
        key: value
        for key, value in os.environ.items()
        if "API_KEY" not in key.upper()
        and not key.upper().startswith(("LANGCHAIN", "LANGSMITH"))
    }
    env.update(PYTHONUTF8="1", LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false")
    output = tmp_path / "ziwei.json"
    process = subprocess.run(
        [
            python,
            "-m",
            "mingjing_core.adapters.charts.benchmarks.night28_ziwei_crosscheck",
            "--mode",
            "scripted",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        encoding="utf8",
        timeout=120,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    report = json.loads(output.read_text("utf8"))
    assert report["dates"] == 1000 and report["difference_count"] == 0
    assert report["comparison_cell_count"] == 4000
    assert report["table_source"]["cells_verified"] == 40
    assert report["snapshot_time_index"] == 6
    assert (
        report["real_model_requests"]
        == report["server_requests"]
        == report["writes_to_profiles"]
        == 0
    )
    assert report["recorded_at_beijing"].endswith("+08:00")
    assert len(report["natal_request_sha256"]) == 64
    assert len(report["shared_natal_palaces_sha256"]) == 64
