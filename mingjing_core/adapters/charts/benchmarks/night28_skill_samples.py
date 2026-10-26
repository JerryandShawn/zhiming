"""Generate native legacy-entry roots for the local skill binding audit only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ..p8_adapter import P8ChartAdapter
from ..profile_draft import profile_proposal

OWNER, SUBJECT = "synthetic-skills-owner", "synthetic-skills-subject"
TARGET_DATE = "2026-10-21"
ROOT = Path(__file__).resolve().parents[4]
OUTPUT = ROOT / "docs/v4/contracts/samples/skill-bindings"


def sample_archive() -> dict:
    """Reuse the existing public skill-field test's exact synthetic input."""
    return {
        "owner_user_id": OWNER,
        "subject_id": SUBJECT,
        "user": {
            "gender": "男",
            "birth": {
                "solar_datetime": "2000-06-15 10:30",
                "timezone_offset": 8,
                "time_precision": "exact",
                "location": {"lng": 120, "lat": 30},
            },
        },
    }


def _save(output: Path, name: str, value: dict) -> dict:
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    content = text.encode("utf8")
    (output / name).write_bytes(content)
    return {"file": name, "sha256": hashlib.sha256(content).hexdigest()}


def generate(chart_python: str, output: Path = OUTPUT) -> dict:
    calculation = P8ChartAdapter(OWNER, python=chart_python).calculate(
        sample_archive(), TARGET_DATE, ["bazi", "ziwei"], 1, SUBJECT
    )
    if calculation["errors"]:
        raise ValueError("skill_native_sample_calculation_failed")
    artifacts = list(calculation["artifacts"].values())
    if len(artifacts) != 2 or {row["system"] for row in artifacts} != {"bazi", "ziwei"}:
        raise ValueError("skill_native_sample_artifacts_ambiguous")
    proposed = profile_proposal(calculation, OWNER, SUBJECT, 1)
    output.mkdir(parents=True, exist_ok=True)
    rows = [_save(output, row["system"] + "-artifact.json", row) for row in artifacts]
    rows += [
        _save(output, "calculation-bundle.json", calculation),
        _save(output, "profile-proposal.json", proposed),
    ]
    manifest = {
        "version": "p8-native-skill-samples-v1",
        "synthetic": True,
        "input_archive": sample_archive(),
        "target_date": TARGET_DATE,
        "entry": "P8ChartAdapter.calculate",
        "method_policy": "legacy_explicit_entry_not_default_true_solar_reading",
        "method_notice": "保留实际平太阳/sect2等方法；不冒充time_basis真太阳主盘。",
        "actual_profiles": calculation["profiles"],
        "files": rows,
        "effects": {
            "model_calls": 0,
            "database_access": 0,
            "writes": "sample_files_only",
        },
        "limits": ["合成字段绑定证据，不是命理效度或外部owner授权证明。"],
    }
    _save(output, "manifest.json", manifest)
    return {"files": len(rows) + 1, "artifacts": len(artifacts), "errors": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chart-python", required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.chart_python), ensure_ascii=False))


if __name__ == "__main__":
    main()
