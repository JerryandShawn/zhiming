"""External-chart provenance and explicit field mapping without reinterpretation."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .records import fingerprint


def external_chart(
    data: dict[str, Any], system: str, source_sha256: str
) -> dict[str, Any]:
    if system not in ("bazi", "ziwei", "astro") or not re.fullmatch(
        r"[a-f0-9]{64}", source_sha256
    ):
        raise ValueError("external_chart_requires_system_and_pinned_source_hash")
    ident = "external-" + fingerprint([system, source_sha256, data])[:24]
    return {
        "artifacts": {
            ident: {
                "id": ident,
                "system": system,
                "data": deepcopy(data),
                "origin": "external_chart_not_our_engine_computation",
                "source_sha256": source_sha256,
            }
        },
        "external_chart": True,
        "calculated_by_our_engine": False,
    }


def _pointer(value: Any, path: str) -> Any:
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("comparison_requires_explicit_json_pointers")
    for item in path[1:].split("/"):
        if re.search(r"~(?![01])", item):
            raise ValueError("invalid_json_pointer_escape")
        key = item.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", key) or int(key) >= len(value):
                raise ValueError("invalid_or_out_of_range_json_pointer_array_index")
            value = value[int(key)]
        else:
            value = value[key]
    return value


def compare_fields(
    ours: dict[str, Any], external: dict[str, Any], mappings: list[tuple[str, str]]
) -> dict[str, Any]:
    if not mappings or len(set(mappings)) != len(mappings):
        raise ValueError("nonempty_unique_explicit_field_mapping_required")
    rows = []
    for own_path, source_path in mappings:
        missing = []
        try:
            own_value = _pointer(ours, own_path)
        except (KeyError, IndexError, TypeError):
            missing.append("our_field")
            own_value = None
        try:
            source_value = _pointer(external, source_path)
        except (KeyError, IndexError, TypeError):
            missing.append("external_field")
            source_value = None
        rows.append(
            {
                "our_path": own_path,
                "external_path": source_path,
                "status": "missing"
                if missing
                else "equal"
                if own_value == source_value
                else "different",
                "missing": missing,
                "our_value_hash": fingerprint(own_value),
                "external_value_hash": fingerprint(source_value),
            }
        )
    return {
        "fields": rows,
        "all_mapped_fields_equal": all(row["status"] == "equal" for row in rows),
        "scope": "only_explicit_mapped_fields_no_automatic_method_or_time_conversion",
        "raw_values_in_report": False,
        "claim_of_chart_correctness": False,
    }
