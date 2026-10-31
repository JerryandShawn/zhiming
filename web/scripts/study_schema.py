"""Small fail-closed validator for the two audited glossary JSON Schemas.

This is the supported local keyword subset, not a general draft-2020-12 engine.
No schema or source URL is dereferenced. Errors never include source values.
"""

from __future__ import annotations

import json
import math
import re
from urllib.parse import urlsplit


class StudyExportError(ValueError):
    def __init__(self) -> None:
        super().__init__("study_glossary_invalid")


def require(condition: bool) -> None:
    if not condition:
        raise StudyExportError()


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def invalid_constant(_value: str) -> None:
    raise StudyExportError()


def finite_float(value: str) -> float:
    number = float(value)
    require(math.isfinite(number))
    return number


def parse(body: bytes) -> object:
    try:
        return json.loads(
            body, object_pairs_hook=unique_object, parse_constant=invalid_constant, parse_float=finite_float
        )
    except (ValueError, UnicodeError, RecursionError):
        raise StudyExportError() from None


KEYWORDS = frozenset(
    (
        "$schema",
        "$defs",
        "$ref",
        "title",
        "description",
        "type",
        "properties",
        "required",
        "additionalProperties",
        "allOf",
        "if",
        "then",
        "const",
        "enum",
        "pattern",
        "minLength",
        "maxLength",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "anyOf",
        "minimum",
        "maximum",
        "format",
    )
)


def type_matches(value: object, kind: str) -> bool:
    checks = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) is int,
        "boolean": type(value) is bool,
        "null": value is None,
        "number": type(value) is int or (type(value) is float and math.isfinite(value)),
    }
    require(kind in checks)
    return checks[kind]


def conforms(value: object, schema: dict, root: dict) -> bool:
    try:
        validate(value, schema, root)
        return True
    except StudyExportError:
        return False


def composition(value: object, schema: dict, root: dict) -> None:
    if "$ref" in schema:
        path = schema["$ref"]
        require(isinstance(path, str) and re.fullmatch(r"#/\$defs/[A-Za-z]+", path) is not None)
        definition = root.get("$defs", {}).get(path.rsplit("/", 1)[1])
        require(isinstance(definition, dict))
        validate(value, definition, root)
    for item in schema.get("allOf", []):
        validate(value, item, root)
    if "anyOf" in schema:
        require(any(conforms(value, item, root) for item in schema["anyOf"]))
    if "if" in schema and conforms(value, schema["if"], root):
        validate(value, schema.get("then", {}), root)


def scalar(value: object, schema: dict) -> None:
    if "format" in schema:
        require(schema["format"] == "uri")
    if "type" in schema:
        kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        require(any(type_matches(value, kind) for kind in kinds))
    if "const" in schema:
        require(canonical(value) == canonical(schema["const"]))
    if "enum" in schema:
        require(any(canonical(value) == canonical(item) for item in schema["enum"]))
    if isinstance(value, str):
        require(len(value) >= schema.get("minLength", 0) and len(value) <= schema.get("maxLength", 16000))
        if "pattern" in schema:
            require(re.search(schema["pattern"], value, flags=re.ASCII) is not None)
        if schema.get("format") == "uri":
            try:
                parts = urlsplit(value)
            except ValueError:
                raise StudyExportError() from None
            require(bool(parts.scheme) and bool(parts.netloc))
    if type(value) in (int, float):
        require((type(value) is int or math.isfinite(value)) and value >= schema.get("minimum", -math.inf))
        require(value <= schema.get("maximum", math.inf))


def children(value: object, schema: dict, root: dict) -> None:
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        require(all(key in value for key in schema.get("required", [])))
        if schema.get("additionalProperties") is False:
            require(set(value) <= set(properties))
        for key, item in properties.items():
            if key in value:
                validate(value[key], item, root)
    if isinstance(value, list):
        require(len(value) >= schema.get("minItems", 0) and len(value) <= schema.get("maxItems", 2000))
        if schema.get("uniqueItems") is True:
            require(len({canonical(item) for item in value}) == len(value))
        if "items" in schema:
            for item in value:
                validate(item, schema["items"], root)


def validate(value: object, schema: dict, root: dict | None = None) -> None:
    require(isinstance(schema, dict) and set(schema) <= KEYWORDS)
    root = schema if root is None else root
    composition(value, schema, root)
    scalar(value, schema)
    children(value, schema, root)
