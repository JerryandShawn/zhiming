"""Conservative JSON projection without asdict/deepcopy; never used by a live entry point."""

import math
from datetime import date, datetime, timezone
from pickle import PicklingError
from typing import Any
from zoneinfo import ZoneInfo

from mingjing_core.application.reflection_v3.validation import ReflectionError, digest, instant

from .types import FIELD_NAMES

MAX_DEPTH = 64


class ProjectionError(ReflectionError):
    def __init__(self) -> None:
        super().__init__("experimental_projection_input_invalid")


def project_json(value: Any) -> Any:
    """Fresh containers only; exact supported types and a bounded, non-concurrent input graph.

    Like the frozen oracle, a Python string is not itself an assurance of valid UTF-8.
    The fingerprint boundary remains the frozen digest, including its encoding check.
    """
    try:
        return _walk(value, set(), 0)
    except (AttributeError, TypeError, ValueError, OverflowError, RecursionError):
        raise ProjectionError() from None


def projection_fingerprint(value: Any) -> str:
    """Use the existing canonical encoder; equality proves no authorization or semantic claim."""
    try:
        return digest(project_json(value))
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ProjectionError() from None


def _walk(value: Any, active: set[int], depth: int) -> Any:
    if depth > MAX_DEPTH:
        raise ProjectionError()
    kind = type(value)
    if value is None or kind is str or kind is bool or kind is int:
        return value
    if kind is float:
        if not math.isfinite(value):
            raise ProjectionError()
        return value
    if kind is datetime:
        return _standard_datetime(value)
    if kind is date:
        return value.isoformat()
    entry = FIELD_NAMES.get(id(kind))
    names = entry[1] if entry is not None and kind is entry[0] else None
    if names is None and kind is not dict and kind is not tuple and kind is not list:
        raise ProjectionError()
    identity = id(value)
    if identity in active:
        raise ProjectionError()
    active.add(identity)
    try:
        return _container(value, kind, names, active, depth)
    finally:
        active.remove(identity)


def _container(value: Any, kind: type, names: tuple[str, ...] | None, active: set[int], depth: int) -> Any:
    if names is not None:
        return {name: _walk(getattr(value, name), active, depth + 1) for name in names}
    if kind is dict:
        if any(type(key) is not str for key in value):
            raise ProjectionError()
        return {key: _walk(item, active, depth + 1) for key, item in value.items()}
    return [_walk(item, active, depth + 1) for item in value]


def _standard_datetime(value: datetime) -> str:
    zone = value.tzinfo
    kind = type(zone)
    if kind is not timezone and kind is not ZoneInfo:
        raise ProjectionError()
    if kind is ZoneInfo:
        try:
            # from_file ZoneInfo cannot be copied by old asdict, even though it is an exact standard type.
            zone.__reduce__()
        except (PicklingError, TypeError, ValueError):
            raise ProjectionError() from None
    return instant(value).isoformat()
