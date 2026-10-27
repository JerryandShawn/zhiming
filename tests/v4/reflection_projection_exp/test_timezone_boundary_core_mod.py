"""Nested deepcopy rejection and deliberately narrower standalone timezone support are distinct."""

import io
import pickle
import struct
from datetime import datetime, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.reflection_projection_exp import ProjectionError, projection_fingerprint
from mingjing_core.application.reflection_v3.validation import dataclass_json, digest
from mingjing_core.memory2.reflection import ReflectionProposal


class UncopyableZone(tzinfo):
    def utcoffset(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    def tzname(self, dt: datetime | None) -> str:
        return "synthetic"

    def __deepcopy__(self, memo: dict[int, Any]) -> Any:
        raise TypeError("synthetic_timezone_copy_forbidden")


def proposal(at: datetime) -> ReflectionProposal:
    return ReflectionProposal("synthetic-proposal", 1, "synthetic-title", "synthetic", (), (), at)


def test_nested_uncopyable_timezone_never_expands_the_old_fingerprint_boundary() -> None:
    value = proposal(datetime(2026, 10, 21, tzinfo=UncopyableZone()))
    with pytest.raises(TypeError):
        digest(dataclass_json(value))
    with pytest.raises(ProjectionError):
        projection_fingerprint(value)


def test_standalone_custom_timezone_is_explicitly_narrower_than_the_old_oracle() -> None:
    value = datetime(2026, 10, 21, tzinfo=UncopyableZone())
    assert digest(dataclass_json(value))
    with pytest.raises(ProjectionError):
        projection_fingerprint(value)


def test_uncopyable_standard_zoneinfo_from_file_is_also_not_a_new_nested_acceptance() -> None:
    header = b"TZif\0" + b"\0" * 15 + struct.pack(">6l", 0, 0, 0, 0, 1, 4)
    payload = header + struct.pack(">lbb", 0, 0, 0) + b"UTC\0"
    zone = ZoneInfo.from_file(io.BytesIO(payload), key="Synthetic/UTC")
    assert type(zone) is ZoneInfo
    value = proposal(datetime(2026, 10, 21, tzinfo=zone))
    with pytest.raises(pickle.PicklingError):
        digest(dataclass_json(value))
    with pytest.raises(ProjectionError):
        projection_fingerprint(value)
