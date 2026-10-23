"""Only private full-text exports; public summaries carry no sample or answer-key fields."""

import json
from pathlib import Path

from .batches import BlindPlan, blind_payload
from .models import CalibrationError, PrivateDataset

REPO = Path(__file__).resolve().parents[2]
PRIVATE = REPO / "private/calibration/v2"


def _write(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def _candidates(dataset: PrivateDataset) -> dict:
    return {
        "schema": "brain25-candidates-private-v3",
        "synthetic_only": True,
        "source_sha256": dataset.source_sha256,
        "dataset_sha256": dataset.sha256,
        "common_material": dataset.common_context,
        "candidates": [
            {
                "source_id": sample.source_id,
                "item": sample.item,
                "material": sample.material,
                "user": sample.user,
                "draft": sample.draft,
            }
            for sample in dataset.samples
        ],
    }


def _labels(dataset: PrivateDataset) -> dict:
    return {
        "schema": "brain25-labels-private-v3",
        "origin": "brain_ai",
        "human_verified": False,
        "dataset_sha256": dataset.sha256,
        "labels": [
            {
                "source_id": sample.source_id,
                "labels": dict(sample.labels),
                "severity": sample.severity,
                "uncertain": sample.uncertain,
                "j02": sample.j02,
                "rationale": sample.rationale,
            }
            for sample in dataset.samples
        ],
    }


def _mapping(dataset: PrivateDataset, plan: BlindPlan) -> dict:
    return {
        "schema": "blind-mapping-private-v3",
        "plan_sha256": plan.sha256,
        "seed": plan.seed,
        "dataset_sha256": dataset.sha256,
        "rubric_sha256": plan.rubric_sha256,
        "owner_id": plan.scope.owner_id,
        "reviewer_id": plan.scope.reviewer_id,
        "batches": [
            {
                "id": batch.id,
                "ordinal": batch.ordinal,
                "refs": [
                    {"blind_id": ref.blind_id, "source_id": ref.sample_id, "item": ref.item} for ref in batch.refs
                ],
            }
            for batch in plan.batches
        ],
    }


def export_private(dataset: PrivateDataset, plan: BlindPlan, *, output: Path) -> dict:
    resolved = output.resolve()
    if not resolved.is_relative_to(REPO.resolve()) or not resolved.is_relative_to(PRIVATE.resolve()) or output.exists():
        raise CalibrationError("new_private_calibration_directory_required")
    if dataset.sha256 != plan.dataset_sha256:
        raise CalibrationError("export_plan_dataset_mismatch")
    resolved.mkdir(parents=True, exist_ok=False)
    _write(resolved / "candidates.private.json", _candidates(dataset))
    _write(resolved / "brain-labels.private.json", _labels(dataset))
    _write(resolved / "blind-mapping.private.json", _mapping(dataset, plan))
    for batch in plan.batches:
        _write(resolved / f"batch-{batch.ordinal}.private.json", blind_payload(dataset, plan, batch))
    return {
        "schema": "calibration-import-summary-v3",
        "source_sha256": dataset.source_sha256,
        "dataset_sha256": dataset.sha256,
        "plan_sha256": plan.sha256,
        "sample_count": 75,
        "batch_count": 5,
        "batch_size": 15,
        "labels_origin": "brain_ai",
        "human_verified_count": 0,
        "critic_observation_count": 0,
        "mode": "record_only",
        "runtime_revision_enabled": False,
        "limitations": [
            "No human review or critic call occurred",
            "Full text, labels and mapping stay private",
            "Daily plan is pure and not yet persisted under an authenticated host lock",
            "The 75 hard cases alone cannot enable critic revision",
        ],
    }
