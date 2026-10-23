"""Replay synthetic learning cards and append a fresh Core-only timing record."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import timedelta, timezone
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

from ....skills.learning import learning_outline
from ....timekit.clock import get_clock
from ..tool_evidence import content_hash
from .handoff_offline import denied, offline_runtime

ROOT = Path(__file__).resolve().parents[4]
CONTRACTS = ROOT / "docs/v4/contracts"
EVIDENCE = ROOT / "docs/v4/evidence/P8"
SYSTEMS = ("bazi", "ziwei", "astro")
BEIJING = timezone(timedelta(hours=8))


def _local_refs(value: Any) -> None:
    if isinstance(value, dict):
        for name in ("$ref", "$dynamicRef"):
            ref = value.get(name)
            if ref is not None and (
                not isinstance(ref, str) or not ref.startswith("#")
            ):
                raise ValueError("learning_preview_external_schema_ref_forbidden")
        for child in value.values():
            _local_refs(child)
    elif isinstance(value, list):
        for child in value:
            _local_refs(child)


def _inputs(contracts: Path) -> tuple[dict, Draft202012Validator, dict]:
    schema_bytes = (contracts / "learning_outline.schema.json").read_bytes()
    schema = json.loads(schema_bytes)
    _local_refs(schema)
    Draft202012Validator.check_schema(schema)
    originals, fingerprints = {}, {}
    for system in SYSTEMS:
        source = contracts / "samples" / f"ayuan_{system}.json"
        raw = source.read_bytes()
        originals[system] = json.loads(raw)
        fingerprints[system] = {
            "file": source.name,
            "file_sha256": hashlib.sha256(raw).hexdigest(),
            "content_sha256": content_hash(originals[system]),
        }
    provenance = {
        "chart_inputs": fingerprints,
        "learning_schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
    }
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return originals, validator, provenance


def _measure(original: dict, validator: Draft202012Validator) -> tuple[dict, dict]:
    before = content_hash(original)
    result = learning_outline(original)
    validator.validate(result)
    observations = []
    for _ in range(10):
        begin = perf_counter()
        candidate = learning_outline(original)
        elapsed = (perf_counter() - begin) * 1000
        # Equality and schema checks stay outside the timed call.
        if candidate != result:
            raise ValueError("learning_preview_nondeterministic_result")
        validator.validate(candidate)
        observations.append(round(elapsed, 6))
    if content_hash(original) != before:
        raise ValueError("learning_preview_input_mutated")
    return result, {
        "warmups": 1,
        "observations": 10,
        "milliseconds": observations,
        "median_ms": median(observations),
        "min_ms": min(observations),
        "max_ms": max(observations),
        "points": len(result["points"]),
        "c_aliases": len(result["aliases"]["c"]),
        "r_aliases": len(result["aliases"]["r"]),
    }


def _code_hashes() -> dict[str, str]:
    paths = [Path(__file__)] + [
        ROOT / "mingjing_core/skills" / name
        for name in ("learning.py", "learning_input.py")
    ]
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for path in paths
    }


def generate_previews(
    contracts: Path, output: Path, performance_output: Path
) -> dict[str, Any]:
    if performance_output.suffix != ".json":
        raise ValueError("learning_preview_performance_json_required")
    if performance_output.exists():
        raise ValueError("learning_preview_performance_output_exists")
    sample_paths = [output / f"learning-ayuan-{system}.json" for system in SYSTEMS]
    if performance_output.resolve() in {path.resolve() for path in sample_paths}:
        raise ValueError("learning_preview_performance_sample_overlap")
    started = get_clock().now().astimezone(BEIJING)
    with (
        offline_runtime(),
        patch.object(subprocess, "run", denied),
        patch.object(subprocess, "Popen", denied),
    ):
        originals, validator, provenance = _inputs(contracts)
        results, measurements = {}, {}
        for system in SYSTEMS:
            results[system], measurements[system] = _measure(
                originals[system], validator
            )
        report = _report(started.isoformat(), measurements, provenance)
        output.mkdir(parents=True, exist_ok=True)
        performance_output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation preserves earlier measurements, including races.
        with performance_output.open("x", encoding="utf8", newline="\n") as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        for path, system in zip(sample_paths, SYSTEMS, strict=True):
            path.write_text(
                json.dumps(results[system], ensure_ascii=False, indent=2) + "\n",
                encoding="utf8",
                newline="\n",
            )
    return report


def _report(started: str, measurements: dict, provenance: dict) -> dict:
    return {
        "version": "p8-learning-preview-performance-v1",
        "mode": "scripted_synthetic_core_only",
        "started_at_beijing": started,
        "recorded_at_beijing": get_clock().now().astimezone(BEIJING).isoformat(),
        "measurements": measurements,
        "provenance": {**provenance, "code_sha256": _code_hashes()},
        "python_version": list(sys.version_info[:3]),
        "method": "Core in-process learning_outline content validation/hash "
        "and rule-card generation only",
        "excluded_from_timing": [
            "input_and_output_file_IO",
            "JSON_serialization",
            "JSON_Schema_validation",
            "output_equality_check",
            "outer_input_immutability_hash_check",
        ],
        "model_calls": 0,
        "chart_processes": 0,
        "profile_writes": 0,
        "effects_scope": "sample_and_new_measurement_files_only",
        "limits": [
            "本机Core单进程1次预热+10次观测；不代表HTTP/Agent/模型/排盘延迟或生产SLA。",
            "纯读取本分支原三份合成样例；别名复用，不创建或注册新的证据账本。",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay synthetic learning previews")
    parser.add_argument("--mode", choices=("scripted",), required=True)
    parser.add_argument("--output-dir", type=Path, default=CONTRACTS / "samples")
    parser.add_argument("--performance-output", type=Path)
    args = parser.parse_args(argv)
    stamp = get_clock().now().astimezone(BEIJING).strftime("%Y%m%dT%H%M%S%f")
    performance = args.performance_output or EVIDENCE / f"learning-preview-{stamp}.json"
    try:
        report = generate_previews(CONTRACTS, args.output_dir, performance)
    except (OSError, ValueError, SchemaError, ValidationError):
        parser.exit(2, "learning_preview_replay_failed_without_external_calls\n")
    print(
        json.dumps(
            {
                "systems": list(report["measurements"]),
                "model_calls": 0,
                "chart_processes": 0,
                "performance_output": str(performance),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
