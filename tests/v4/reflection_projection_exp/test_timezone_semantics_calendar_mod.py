"""Copy-transforming custom zones are excluded; ordinary no-cache DST instants keep oracle parity."""

import json
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.reflection_projection_exp import ProjectionError, project_json, projection_fingerprint
from mingjing_core.application.reflection_v3.validation import dataclass_json, digest
from mingjing_core.memory2.reflection import ReflectionProposal


class CopyChangesOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> timedelta:
        return timedelta(hours=2)

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    def __deepcopy__(self, memo: dict[int, Any]) -> timezone:
        return timezone.utc


def proposal(at: datetime) -> ReflectionProposal:
    root = Path(__file__).resolve().parents[3]
    path = root / "tools/eval/fixtures/mod_20261021/reflection_projection_vectors_synthetic.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["synthetic"] is True
    return ReflectionProposal("synthetic-proposal", 1, "synthetic-title", data["strings"][0], (), (), at)


def test_custom_timezone_copy_transform_cannot_change_accepted_nested_json() -> None:
    at = datetime(2026, 10, 21, 8, tzinfo=CopyChangesOffset())
    value = proposal(at)
    # asdict copies the zone before UTC conversion; skipping that operation would change the accepted value.
    oracle = dataclass_json(value)
    assert oracle["updated_at"] == "2026-10-21T08:00:00+00:00"
    assert dataclass_json(at) == "2026-10-21T06:00:00+00:00"
    assert digest(oracle)
    with pytest.raises(ProjectionError):
        project_json(value)
    with pytest.raises(ProjectionError):
        projection_fingerprint(value)


@pytest.mark.parametrize("fold,hour", ((0, 5), (1, 6)))
def test_exact_no_cache_zoneinfo_preserves_both_dst_fold_instants(fold: int, hour: int) -> None:
    zone = ZoneInfo.no_cache("America/New_York")
    assert type(zone) is ZoneInfo
    at = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=fold)
    value = proposal(at)
    oracle = dataclass_json(value)
    assert oracle["updated_at"] == f"2026-11-01T{hour:02d}:30:00+00:00"
    assert project_json(value) == oracle
    assert projection_fingerprint(value) == digest(oracle)
