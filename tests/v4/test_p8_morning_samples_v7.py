"""Readable offline samples preserve provenance and expose source repetition."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import timedelta

import pytest

from mingjing_core.adapters.charts.benchmarks.final_prep_v7 import ROOT
from mingjing_core.adapters.charts.benchmarks.morning_samples_v7 import (
    START,
    readable_sample,
    repetition_audit,
)

SOURCE = ROOT / "docs/v4/contracts/samples/daily_transit"
OUTPUT = ROOT / "docs/v4/contracts/final_prep_20261027/morning"
DAYS = [(START + timedelta(days=i)).isoformat() for i in range(7)]


def sample(day: str) -> dict:
    value = json.loads((SOURCE / f"ayuan_{day}.json").read_bytes())
    return readable_sample(value, expected_scope=value["scope"], target_date=day)


@pytest.mark.parametrize("day", DAYS)
def test_seven_readable_samples_match_verified_source_and_saved_output(
    day: str,
) -> None:
    value = sample(day)
    assert value["markdown"] == (OUTPUT / f"ayuan_{day}.md").read_text(encoding="utf-8")
    assert value == json.loads((OUTPUT / f"ayuan_{day}.json").read_bytes())
    assert value["content"]["effects"] == {"model_calls": 0, "writes": 0, "sends": 0}
    for point in value["content"]["points"]:
        assert point["observation"] in value["markdown"]
        assert all(
            f"〔{a}〕" in value["markdown"]
            for a in point["c_aliases"] + point["r_aliases"]
        )
        assert point["school"] in value["markdown"]
        assert point["source"]["status"] in value["markdown"]
    assert "正午12点" in value["markdown"]
    assert "编辑建议，不由盘面推导" in value["markdown"]
    assert not any(
        word in value["markdown"]
        for word in ("打卡", "连签", "别错过", "灾祸", "保证", "每天来看")
    )


@pytest.mark.parametrize("field", ["document_id", "scope", "aliases", "snapshot"])
def test_forged_or_cross_subject_provenance_is_rejected(field: str) -> None:
    value = json.loads((SOURCE / f"ayuan_{DAYS[0]}.json").read_bytes())
    expected = deepcopy(value["scope"])
    if field == "document_id":
        value["document_id"] = "forged"
    elif field == "scope":
        value["scope"]["subject_id"] = "other-subject"
    elif field == "aliases":
        value["aliases"]["r"][0]["evidence_aliases"] = ["c999"]
    else:
        value["data"]["snapshot_at"] = DAYS[0] + "T07:00:00+08:00"
    with pytest.raises(ValueError, match="morning_content_input_invalid"):
        readable_sample(value, expected_scope=expected, target_date=DAYS[0])


def test_repetition_is_reported_instead_of_fabricating_novel_facts() -> None:
    values = [sample(day) for day in DAYS]
    report = repetition_audit(values)
    assert report["computed_points"] == 21
    assert report["unique_editorial_actions"] == 7
    assert sorted(report["original_repeated_reflections"].values()) == [7, 7, 7]
    assert report["repeated_observations"]
    with pytest.raises(ValueError, match="ordered_seven_days"):
        repetition_audit(list(reversed(values)))
    with pytest.raises(ValueError, match="week_only"):
        readable_sample({}, expected_scope={}, target_date="2026-10-28")
