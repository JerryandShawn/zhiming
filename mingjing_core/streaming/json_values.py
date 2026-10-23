"""JSON-only deep copies isolate callers, stores, and transport projections."""

import math
from collections.abc import Mapping
from types import MappingProxyType

from .event_errors import EventValidationError


def freeze_json(value: object) -> object:
    if type(value) is str:
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeError:
            raise EventValidationError("json_unicode_invalid") from None
        return value
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise EventValidationError("json_key_invalid")
        for key in value:
            freeze_json(key)
        return MappingProxyType({key: freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    raise EventValidationError("json_value_invalid")


def thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


def json_object(value: object) -> dict:
    try:
        result = thaw_json(freeze_json(value))
    except RecursionError:
        raise EventValidationError("json_nesting_invalid") from None
    if not isinstance(result, dict):
        raise EventValidationError("json_object_required")
    return result
