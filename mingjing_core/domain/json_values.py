"""Strict JSON boundaries shared by calculators and released knowledge packs."""
from __future__ import annotations

import math


def ensure_finite_json(value, path="$"):
    """Reject non-finite numbers and non-JSON objects without echoing values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite number at " + path)
        return value
    if isinstance(value, list):
        for index, child in enumerate(value):
            ensure_finite_json(child, path + "/" + str(index))
        return value
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("non-string JSON object key at " + path)
            ensure_finite_json(child, path + "/" + key)
        return value
    raise ValueError("non-JSON value at " + path)
