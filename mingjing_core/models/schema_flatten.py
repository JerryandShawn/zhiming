"""Flatten Pydantic schemas without mutating source contracts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def flatten_schema(
    schema: dict[str, Any], dialect: str = "openai", *, unsupported: tuple[str, ...] = ("default", "examples", "format")
) -> dict[str, Any]:
    if dialect not in {"openai", "openai_partial", "anthropic"}:
        raise ValueError("Unknown schema dialect")
    root = deepcopy(schema)

    def visit(node: Any, stack: tuple[str, ...] = ()) -> Any:
        if isinstance(node, list):
            return [visit(item, stack) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            ref = node["$ref"]
            if not ref.startswith("#/") or ref in stack:
                raise ValueError("Only acyclic local schema references are supported")
            target = root
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
            return visit({**target, **{k: v for k, v in node.items() if k != "$ref"}}, (*stack, ref))
        result = {}
        for key, value in node.items():
            if key in {*unsupported, "$defs", "definitions"}:
                continue
            if key in {"properties", "patternProperties"}:
                result[key] = {name: visit(child, stack) for name, child in value.items()}
            elif key in {"items", "additionalProperties", "anyOf", "oneOf", "allOf", "not"}:
                result[key] = visit(value, stack)
            else:
                result[key] = deepcopy(value)
        variants = result.get("anyOf", [])
        nonnull = [value for value in variants if value.get("type") != "null"]
        if variants and len(nonnull) == 1 and len(variants) != len(nonnull):
            result = {**{k: v for k, v in result.items() if k != "anyOf"}, **nonnull[0]}
        if "properties" in result:
            required = result.get("required", [])
            result["required"] = [name for name in required if not _nullable(node["properties"].get(name, {}))]
        if not any(key in result for key in ("type", "anyOf", "oneOf", "allOf", "enum", "const")):
            if dialect == "openai_partial":
                result.update(type="string", description=result.get("description", "") + " 值可传 JSON 字符串。")
            else:
                result["type"] = ["string", "number", "boolean", "object", "array", "null"]
        return result

    return visit(root)


def _nullable(schema: dict[str, Any]) -> bool:
    return any(item.get("type") == "null" for item in schema.get("anyOf", []))
