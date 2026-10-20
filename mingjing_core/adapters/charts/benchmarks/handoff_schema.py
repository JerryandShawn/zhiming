"""JSON Schema for the synthetic chart-compute handoff, not a runtime API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

LEGACY_CONTRACT_VERSION = "p8-chart-compute-preview-v1"
CONTRACT_VERSION = "p8-chart-compute-preview-v1.1"
SCHEMA_FILENAME = "chart_compute.schema.json"
VIEW_KEYS = (
    "time_basis",
    "primary",
    "comparisons",
    "diagnostics",
    "rules",
    "assessments",
    "interactions",
    "flying",
    "transits",
    "timings",
    "boundary_alerts",
)


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _ref(name: str) -> dict[str, str]:
    return {"$ref": "#/$defs/" + name}


def _array(items: dict[str, Any], minimum: int = 0) -> dict[str, Any]:
    return {"type": "array", "items": items, "minItems": minimum}


def _text() -> dict[str, Any]:
    return {"type": "string", "minLength": 1, "pattern": r"\S"}


def _sha256() -> dict[str, str]:
    return {"type": "string", "pattern": "^[a-f0-9]{64}$"}


def _scope() -> dict[str, Any]:
    return _object(
        {
            "owner_user_id": _text(),
            "subject_id": _text(),
            "revision": {"type": "integer", "minimum": 0},
            "operation_id": _text(),
        }
    )


def _birth() -> dict[str, Any]:
    return _object(
        {
            "date": {"type": "string", "format": "date"},
            "reported_time": {
                "type": "string",
                "pattern": r"^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$",
            },
            "gender": {"enum": ["男", "女"]},
            "place": _object(
                {
                    "tz": _text(),
                    "lon": {"type": "number", "minimum": -180, "maximum": 180},
                    "lat": {
                        "type": "number",
                        "exclusiveMinimum": -90,
                        "exclusiveMaximum": 90,
                    },
                }
            ),
            "clock_basis": {"enum": ["clock", "standard", "unknown"]},
            "precision": {"const": "reported"},
        }
    )


def _request() -> dict[str, Any]:
    return _object(
        {
            "system": {"enum": ["bazi", "ziwei", "astro"]},
            "target_date": {"type": "string", "format": "date"},
            "time_scale": _text(),
            "birth": _ref("Birth"),
            "physical_birth_at_utc": {"type": "string", "format": "date-time"},
        }
    )


def _payload_condition(kind: str, required: dict[str, Any]) -> dict[str, Any]:
    return {
        "if": {"properties": {"kind": {"const": kind}}, "required": ["kind"]},
        "then": {
            "properties": {
                "payload": {
                    "type": "object",
                    "properties": required,
                    "required": list(required),
                    "additionalProperties": True,
                }
            }
        },
    }


def _document() -> dict[str, Any]:
    result = _object(
        {
            "document_id": {"type": "string", "pattern": "^doc-[a-f0-9]{64}$"},
            "kind": {"enum": ["time_basis", "calculation_bundle", "western_timing"]},
            "source_sha256": {
                "type": "object",
                "minProperties": 1,
                "propertyNames": _text(),
                "additionalProperties": _sha256(),
            },
            "payload": {"type": "object", "additionalProperties": True},
        }
    )
    result["allOf"] = [
        _payload_condition(
            "time_basis", {"version": {"const": "p8-time-basis-readonly-v2-review23"}}
        ),
        _payload_condition(
            "western_timing", {"version": {"const": "p8-western-timing-readonly-v1"}}
        ),
        _payload_condition(
            "calculation_bundle",
            {
                **{
                    key: {"type": "object"}
                    for key in ("artifacts", "features", "profiles")
                },
                **{key: {"type": "array"} for key in ("branches", "errors")},
            },
        ),
    ]
    return result


def _alias_properties(prefix: str) -> dict[str, Any]:
    return {
        "alias": {"type": "string", "pattern": "^" + prefix + "[1-9][0-9]*$"},
        "claim_id": {"type": "string", "pattern": "^demo-claim-[a-f0-9]{64}$"},
        "scope": _ref("Scope"),
        "ref": _ref("Ref"),
        "value_sha256": _sha256(),
        "branch_id": _text(),
        "basis": {"enum": ["true_solar", "standard", "beijing_standard", "actual_UTC"]},
    }


def _rule_alias() -> dict[str, Any]:
    properties = _alias_properties("r")
    properties.update(
        {
            "rule_id": _text(),
            "rules_version": _text(),
            "evidence_aliases": _array(
                {"type": "string", "pattern": "^c[1-9][0-9]*$"}, 1
            ),
        }
    )
    return _object(properties)


def _definitions() -> dict[str, Any]:
    return {
        "Scope": _scope(),
        "Birth": _birth(),
        "Request": _request(),
        "Document": _document(),
        "Ref": _object(
            {
                "document_id": {"type": "string", "pattern": "^doc-[a-f0-9]{64}$"},
                "path": {
                    "type": "string",
                    "pattern": "^(?:/.*)?$",
                    "format": "json-pointer",
                },
            }
        ),
        "ChartAlias": _object(_alias_properties("c")),
        "RuleAlias": _rule_alias(),
    }


def schema() -> dict[str, Any]:
    """Return a fresh 2020-12 schema; semantic provenance checks are separate."""
    result = _object(
        {
            "contract_version": {"enum": [LEGACY_CONTRACT_VERSION, CONTRACT_VERSION]},
            "status": {"const": "draft_integration_contract"},
            "mode": {"const": "scripted_synthetic_preview"},
            "display_name": _text(),
            "scope": _ref("Scope"),
            "request": _ref("Request"),
            "documents": _array(_ref("Document"), 1),
            "view": _object({key: _array(_ref("Ref")) for key in VIEW_KEYS}),
            "aliases": _object(
                {"c": _array(_ref("ChartAlias")), "r": _array(_ref("RuleAlias"))}
            ),
            "effects": _object(
                {
                    "model_calls": {"const": 0},
                    "writes": {"const": 0},
                    "alias_registry": {"const": "ephemeral_demo_only"},
                }
            ),
            "warnings": _array(_text(), 1),
            "boundary_alerts": _array(_ref("Ref")),
        }
    )
    result["required"].remove("boundary_alerts")
    result["properties"]["view"]["required"].remove("boundary_alerts")
    result["allOf"] = [
        {
            "if": {"properties": {"contract_version": {"const": CONTRACT_VERSION}}},
            "then": {
                "required": ["boundary_alerts"],
                "properties": {"view": {"required": ["boundary_alerts"]}},
            },
        }
    ]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "P8 chart_compute synthetic preview integration contract",
        "description": (
            "Structure only. Ownership, content hashes, reference resolution, "
            "rule truth and finite JSON require the accompanying semantic validator."
        ),
        **result,
        "$defs": _definitions(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[4]
        / "docs"
        / "v4"
        / "contracts"
        / SCHEMA_FILENAME,
    )
    output = parser.parse_args().output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
