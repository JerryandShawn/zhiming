"""Fail closed at the untrusted in-memory contract boundary."""

from collections.abc import Iterable


def require_bool(*values: object) -> None:
    if any(type(value) is not bool for value in values):
        raise ValueError("memory_boolean_required")


def require_int(value: object, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError("memory_integer_required")


def require_text(*values: object) -> None:
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("memory_identifier_required")


def frozen_tuple(values: object, expected: type) -> tuple:
    if not isinstance(values, (tuple, list)) or any(not isinstance(value, expected) for value in values):
        raise ValueError("memory_collection_invalid")
    return tuple(values)


def unique(values: Iterable[object]) -> None:
    values = tuple(values)
    if len(set(values)) != len(values):
        raise ValueError("memory_duplicate_identifier")
