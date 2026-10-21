"""Finite JSON integrity primitives; errors never echo source values."""

from __future__ import annotations

import hashlib
import json
import math
import re

ERROR = "learning_public_projection_invalid"
COMMIT = "0f1d6e676259b961819de4da5ea3f343d58dbe98"
SYSTEMS = ("bazi", "ziwei", "astro")
PREFIX = "docs/v4/contracts/samples/"


def need(condition: bool) -> None:
    if not condition:
        raise ValueError(ERROR)


def finite(value: object, depth: int = 0) -> None:
    need(depth < 100)
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        need(math.isfinite(value))
    elif type(value) is list:
        for item in value:
            finite(item, depth + 1)
    elif type(value) is dict:
        need(all(type(key) is str for key in value))
        for item in value.values():
            finite(item, depth + 1)
    else:
        need(False)


def digest(value: object) -> str:
    finite(value)
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(body.encode("utf8")).hexdigest()


def same(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(same(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right, strict=True))
    return left == right


def pointer(value: object, path: str) -> object:
    need(type(path) is str and (path == "" or path.startswith("/")))
    if path == "":
        return value
    for token in path[1:].split("/"):
        need(re.search(r"~(?![01])", token) is None)
        key = token.replace("~1", "/").replace("~0", "~")
        if type(value) is list:
            need(re.fullmatch(r"0|[1-9][0-9]*", key) is not None and int(key) < len(value))
            value = value[int(key)]
        else:
            need(type(value) is dict and key in value)
            value = value[key]
    return value


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        need(key not in result)
        result[key] = value
    return result


def parse(raw: bytes) -> dict:
    try:
        value = json.loads(raw, object_pairs_hook=unique_object)
        finite(value)
        need(type(value) is dict)
        return value
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise ValueError(ERROR) from None
