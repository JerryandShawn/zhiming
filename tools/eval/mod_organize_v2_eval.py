"""Single final offline B evaluation; preparation never opens the sealed fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from mingjing_core.timekit.clock import Clock

ROOT = Path(__file__).resolve().parents[2]
if __name__ == "__main__" and str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BLIND_PATH = "tools/eval/fixtures/mod_20261021/organize_blind_B.json"
BLIND_SHA = "db998b7d960af7276c87d45d25ee024a0d3913e72d74e0bd938dfc6f60cd8682"
MAPPING_PATH = "tools/eval/fixtures/mod_20261021/BLIND_B_label_mapping.json"
MAPPING_SHA = "254ab6760a08bb3059533cf66f17283ab5c436ae8d3b8bc1c4c5312dd6c43639"
SELF_PATH = "tools/eval/mod_organize_v2_eval.py"
TOPICS_PATH = "tools/eval/mod_organize_v2_topics.py"
FEATURES_PATH = "tools/eval/mod_organize_v2_features.py"
EVALUATOR_PATHS = (SELF_PATH, TOPICS_PATH, FEATURES_PATH)
UNKNOWN_GOLD = "__unorganized__"
SCHEMA = "organize.v2.preblind.v1"


class BlindProtocolError(ValueError):
    """Fixed reason strings never contain sealed text or per-record gold."""


def timestamp(clock: Clock | None) -> str:
    from mingjing_core.timekit.clock import SystemClock

    instant = (clock or SystemClock()).now()
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise BlindProtocolError("evaluation_clock_must_be_aware")
    return instant.astimezone(ZoneInfo("Asia/Shanghai")).isoformat()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def file_in_repo(relative: str, *, root: Path = ROOT) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise BlindProtocolError("evaluation_path_invalid")
    return path


def source_snapshot(*, root: Path = ROOT) -> dict[str, str]:
    base = root / "mingjing_core/organize"
    paths = sorted(path for path in base.rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    return {path.relative_to(root).as_posix(): digest(path.read_bytes()) for path in paths if path.suffix != ".pyc"}


def prepare_manifest(
    settings: dict | None = None,
    *,
    topic_settings: dict | None = None,
    clock: Clock | None = None,
    root: Path = ROOT,
) -> dict:
    from mingjing_core.organize.v2.contracts import ClassifierSettings

    concrete = asdict(ClassifierSettings(**(settings or {})))
    topics = topic_settings or {"similarity_threshold": 0.4}
    value = topics.get("similarity_threshold")
    if set(topics) != {"similarity_threshold"} or type(value) not in (int, float) or not 0 <= value <= 1:
        raise BlindProtocolError("topic_parameters_invalid")
    sources = source_snapshot(root=root)
    evaluators = {path: digest(file_in_repo(path, root=root).read_bytes()) for path in EVALUATOR_PATHS}
    if not sources or digest(file_in_repo(MAPPING_PATH, root=root).read_bytes()) != MAPPING_SHA:
        raise BlindProtocolError("preblind_sources_or_mapping_invalid")
    # The B hash is the earlier independent freeze, never recomputed during preparation.
    return {
        "schema": SCHEMA,
        "status": "preblind_frozen",
        "frozen_at": timestamp(clock),
        "source_files": sources,
        "source_tree_sha256": digest(canonical(sources)),
        "settings": concrete,
        "settings_sha256": digest(canonical(concrete)),
        "topic_settings": topics,
        "topic_settings_sha256": digest(canonical(topics)),
        "parameters_sha256": digest(canonical({"classifier": concrete, "topics": topics})),
        "fixture_path": BLIND_PATH,
        "fixture_sha256": BLIND_SHA,
        "mapping_path": MAPPING_PATH,
        "mapping_sha256": MAPPING_SHA,
        "evaluator_sha256": digest(file_in_repo(SELF_PATH, root=root).read_bytes()),
        "evaluator_files": evaluators,
        "evaluator_tree_sha256": digest(canonical(evaluators)),
        "context_policy": "explicit_context_group_previous_predictions_only",
        "gold_unknown": UNKNOWN_GOLD,
        "topic_clustering": "character_ngram_without_gold",
        "retry_policy": "single_final_no_retuning_or_automatic_retry",
    }


def validate_manifest(manifest: dict, *, root: Path = ROOT) -> None:
    fixed = {
        "schema": SCHEMA,
        "status": "preblind_frozen",
        "fixture_path": BLIND_PATH,
        "fixture_sha256": BLIND_SHA,
        "mapping_path": MAPPING_PATH,
        "mapping_sha256": MAPPING_SHA,
        "context_policy": "explicit_context_group_previous_predictions_only",
        "gold_unknown": UNKNOWN_GOLD,
        "topic_clustering": "character_ngram_without_gold",
        "retry_policy": "single_final_no_retuning_or_automatic_retry",
    }
    if not isinstance(manifest, dict) or any(manifest.get(key) != value for key, value in fixed.items()):
        raise BlindProtocolError("preblind_manifest_not_frozen")
    sources = source_snapshot(root=root)
    if manifest.get("source_files") != sources or manifest.get("source_tree_sha256") != digest(canonical(sources)):
        raise BlindProtocolError("preblind_source_changed")
    if manifest.get("settings_sha256") != digest(canonical(manifest.get("settings"))):
        raise BlindProtocolError("preblind_settings_changed")
    if manifest.get("topic_settings_sha256") != digest(canonical(manifest.get("topic_settings"))):
        raise BlindProtocolError("preblind_topic_settings_changed")
    parameters = {
        "classifier": manifest.get("settings"),
        "topics": manifest.get("topic_settings"),
    }
    if manifest.get("parameters_sha256") != digest(canonical(parameters)):
        raise BlindProtocolError("preblind_parameters_changed")
    if digest(file_in_repo(MAPPING_PATH, root=root).read_bytes()) != MAPPING_SHA:
        raise BlindProtocolError("preblind_mapping_changed")
    if manifest.get("evaluator_sha256") != digest(file_in_repo(SELF_PATH, root=root).read_bytes()):
        raise BlindProtocolError("preblind_evaluator_changed")
    actual = {path: digest(file_in_repo(path, root=root).read_bytes()) for path in EVALUATOR_PATHS}
    if manifest.get("evaluator_files") != actual:
        raise BlindProtocolError("preblind_evaluator_helper_changed")
    if manifest.get("evaluator_tree_sha256") != digest(canonical(actual)):
        raise BlindProtocolError("preblind_evaluator_tree_changed")


def evaluate_records(
    records: list[dict],
    classifier: Any,
    normalization: dict[str, str],
    *,
    similarity_threshold: float = 0.4,
) -> dict:
    from tools.eval.mod_organize_v2_features import (
        evaluate_records as evaluate_features,
    )

    return evaluate_features(
        records,
        classifier,
        normalization,
        similarity_threshold=similarity_threshold,
        unknown_gold=UNKNOWN_GOLD,
        error_type=BlindProtocolError,
    )


def make_report(result: dict, manifest: dict, manifest_sha256: str, stamp: str) -> dict:
    area = result["area_assignment"]
    accuracy, abstention = area["assigned_accuracy"], area["abstention_rate"]
    return {
        "schema": "organize.v2.final_blind_report.v1",
        "evaluated_at": stamp,
        "fixture_sha256": BLIND_SHA,
        "mapping_sha256": MAPPING_SHA,
        "manifest_sha256": manifest_sha256,
        "source_tree_sha256": manifest["source_tree_sha256"],
        "settings_sha256": manifest["settings_sha256"],
        "topic_settings_sha256": manifest["topic_settings_sha256"],
        "parameters_sha256": manifest["parameters_sha256"],
        "evaluator_sha256": manifest["evaluator_sha256"],
        "evaluator_tree_sha256": manifest["evaluator_tree_sha256"],
        "synthetic_only": True,
        "real_history_applied": False,
        **result,
        "target": {
            "scope": "area_assignment_only",
            "assigned_accuracy_min": 0.85,
            "abstention_rate_max": 0.35,
            "passed": accuracy is not None and accuracy >= 0.85 and abstention <= 0.35,
        },
        "limits": [
            "Area-label ARI is not topic-clustering ARI.",
            "Single sealed B evaluation; no row examples, gold distributions or tuning feedback emitted.",
        ],
    }


def validate_destination(manifest_path: Path, output_path: Path, root: Path) -> None:
    if not manifest_path.resolve().is_relative_to(root.resolve()):
        raise BlindProtocolError("manifest_path_outside_repo")
    if not output_path.resolve().is_relative_to(root.resolve()) or not output_path.parent.is_dir():
        raise BlindProtocolError("blind_report_destination_invalid")
    if output_path.exists():
        raise BlindProtocolError("blind_report_already_exists")
    try:
        with tempfile.TemporaryFile(dir=output_path.parent) as probe:
            probe.write(b"synthetic_preblind_write_probe")
    except OSError:
        raise BlindProtocolError("blind_report_parent_not_writable") from None


def run_final(
    manifest_path: Path,
    output_path: Path,
    *,
    expected_manifest_sha256: str | None = None,
    clock: Clock | None = None,
    root: Path = ROOT,
) -> dict:
    from mingjing_core.organize.v2.classifier import LocalClassifier
    from mingjing_core.organize.v2.contracts import ClassifierSettings

    manifest_raw = manifest_path.read_bytes()
    if expected_manifest_sha256 is None or digest(manifest_raw) != expected_manifest_sha256:
        raise BlindProtocolError("root_frozen_manifest_hash_mismatch")
    manifest = json.loads(manifest_raw)
    validate_manifest(manifest, root=root)
    validate_destination(manifest_path, output_path, root)
    claim = manifest_path.with_name(manifest_path.name + ".blind_claim.json")
    stamp = timestamp(clock)
    try:
        with claim.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {
                    "manifest_sha256": digest(manifest_raw),
                    "claimed_at": stamp,
                    "status": "single_final_claimed",
                },
                handle,
            )
    except FileExistsError:
        raise BlindProtocolError("blind_final_already_claimed_no_retry") from None
    # The first access to B is after full source/config/evaluator checks and the one-shot claim.
    sealed_raw = file_in_repo(BLIND_PATH, root=root).read_bytes()
    if digest(sealed_raw) != BLIND_SHA:
        raise BlindProtocolError("blind_fixture_changed")
    records = json.loads(sealed_raw).get("records")
    if not isinstance(records, list) or len(records) != 231:
        raise BlindProtocolError("blind_record_count_invalid")
    mapping = json.loads(file_in_repo(MAPPING_PATH, root=root).read_bytes())
    result = evaluate_records(
        records,
        LocalClassifier(ClassifierSettings(**manifest["settings"])),
        mapping["normalization"],
        **manifest["topic_settings"],
    )
    report = make_report(result, manifest, digest(manifest_raw), stamp)
    with output_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--final-blind", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args()
    if args.prepare == args.final_blind:
        raise BlindProtocolError("choose_exactly_one_prepare_or_final")
    if args.prepare:
        with args.manifest.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(prepare_manifest(), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(
            json.dumps(
                {
                    "manifest": str(args.manifest),
                    "manifest_sha256": digest(args.manifest.read_bytes()),
                    "B_read": False,
                },
                ensure_ascii=False,
            )
        )
        return
    if args.output is None:
        raise BlindProtocolError("final_output_required")
    report = run_final(
        args.manifest,
        args.output,
        expected_manifest_sha256=args.expected_manifest_sha256,
    )
    print(
        json.dumps(
            {
                "report": str(args.output),
                "target_passed": report["target"]["passed"],
                "source_tree_sha256": report["source_tree_sha256"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
