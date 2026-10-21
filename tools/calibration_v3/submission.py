"""Validate an unsigned 15-answer UI submission without turning it into human evidence."""

import re
from dataclasses import dataclass
from datetime import datetime

from mingjing_core.timekit.clock import Clock

from .batches import BlindPlan, blind_payload
from .blind_payload_contract import blind_payload_digest
from .daily import OpeningLedger, aware
from .models import ITEMS, CalibrationError, PrivateDataset, fingerprint, identity

HEADER = {
    "schema",
    "submission_id",
    "owner_id",
    "reviewer_id",
    "plan_sha256",
    "dataset_sha256",
    "rubric_sha256",
    "payload_sha256",
    "batch_id",
    "submitted_at",
    "answers",
}


@dataclass(frozen=True)
class SubmissionReceipt:
    submission_id: str
    submission_sha256: str
    payload_sha256: str
    answer_count: int = 15
    status: str = "unverified_submission"
    verified_human_count: int = 0
    runtime_revision_enabled: bool = False


def _answers(value: object, expected: set[str]) -> None:
    if type(value) is not list or len(value) != 15:
        raise CalibrationError("submission_fifteen_answers_required")
    seen = set()
    for answer in value:
        if type(answer) is not dict or set(answer) != {"blind_id", "items"}:
            raise CalibrationError("submission_answer_shape_invalid")
        blind_id, items = answer["blind_id"], answer["items"]
        if type(blind_id) is not str or blind_id not in expected or blind_id in seen:
            raise CalibrationError("submission_blind_id_invalid")
        seen.add(blind_id)
        if type(items) is not dict or set(items) != set(ITEMS):
            raise CalibrationError("submission_all_items_required")
        for annotation in items.values():
            if type(annotation) is not dict or set(annotation) != {"violation", "severity", "uncertain"}:
                raise CalibrationError("submission_annotation_shape_invalid")
            violation, severity = annotation["violation"], annotation["severity"]
            if type(violation) is not bool or type(annotation["uncertain"]) is not bool:
                raise CalibrationError("submission_boolean_required")
            if (violation and (type(severity) is not int or not 1 <= severity <= 5)) or (
                not violation and severity is not None
            ):
                raise CalibrationError("submission_severity_invalid")


def validate_submission(
    value: object, *, dataset: PrivateDataset, plan: BlindPlan, ledger: OpeningLedger, clock: Clock
) -> SubmissionReceipt:
    now = aware(clock.now())
    if type(value) is not dict or set(value) != HEADER or value["schema"] != "human-review-submission-v3.1":
        raise CalibrationError("submission_shape_invalid")
    if (
        not isinstance(dataset, PrivateDataset)
        or not isinstance(plan, BlindPlan)
        or not isinstance(ledger, OpeningLedger)
    ):
        raise CalibrationError("submission_typed_binding_required")
    identity(value["submission_id"])
    expected = (plan.scope.owner_id, plan.scope.reviewer_id, plan.sha256, dataset.sha256, plan.rubric_sha256)
    actual = tuple(value[key] for key in ("owner_id", "reviewer_id", "plan_sha256", "dataset_sha256", "rubric_sha256"))
    if actual != expected or plan.dataset_sha256 != dataset.sha256 or ledger.plan_sha256 != plan.sha256:
        raise CalibrationError("submission_scope_or_version_mismatch")
    batch = next((batch for batch in plan.batches if batch.id == value["batch_id"]), None)
    opening = next((entry for entry in ledger.entries if entry.batch_id == value["batch_id"]), None)
    if batch is None or opening is None:
        raise CalibrationError("submission_opened_batch_required")
    if value["payload_sha256"] != blind_payload_digest(blind_payload(dataset, plan, batch)):
        raise CalibrationError("submission_displayed_payload_mismatch")
    if (
        type(value["submitted_at"]) is not str
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value["submitted_at"])
        is None
    ):
        raise CalibrationError("submission_aware_time_required")
    try:
        submitted = aware(datetime.fromisoformat(value["submitted_at"]))
    except (TypeError, ValueError):
        raise CalibrationError("submission_aware_time_required") from None
    if submitted < opening.opened_at or submitted > now:
        raise CalibrationError("submission_time_outside_opening")
    _answers(value["answers"], {ref.blind_id for ref in batch.refs})
    return SubmissionReceipt(value["submission_id"], fingerprint(value), value["payload_sha256"])
