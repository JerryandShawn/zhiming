"""Verify trusted-host attestations; this module cannot establish who physically used a UI."""

import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from mingjing_core.timekit.clock import Clock

from .batches import BlindPlan, blind_payload
from .blind_payload_contract import blind_payload_digest
from .daily import OpeningLedger, aware
from .models import ITEMS, CalibrationError, PrivateDataset, digest, identity, label_vector


@dataclass(frozen=True)
class HumanLabelRecord:
    record_id: str
    owner_id: str
    reviewer_id: str
    plan_sha256: str
    dataset_sha256: str
    rubric_sha256: str
    payload_sha256: str
    batch_id: str
    blind_id: str
    labels: tuple[tuple[str, bool], ...] = field(repr=False)
    reviewed_at: datetime
    origin: str
    stage: str
    signature: str = field(repr=False)
    uncertain_items: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("record_id", "owner_id", "reviewer_id", "batch_id", "blind_id"):
            identity(getattr(self, name))
        for name in ("plan_sha256", "dataset_sha256", "rubric_sha256", "payload_sha256", "signature"):
            digest(getattr(self, name))
        if (
            not isinstance(self.labels, tuple)
            or any(not isinstance(pair, tuple) or len(pair) != 2 for pair in self.labels)
            or label_vector(dict(self.labels)) != self.labels
        ):
            raise CalibrationError("human_complete_labels_required")
        if self.origin != "human_ui" or self.stage not in {"review", "adjudication"}:
            raise CalibrationError("human_ui_origin_required")
        if (
            not isinstance(self.uncertain_items, tuple)
            or len(set(self.uncertain_items)) != len(self.uncertain_items)
            or (any(item not in ITEMS for item in self.uncertain_items))
        ):
            raise CalibrationError("human_uncertain_items_invalid")
        object.__setattr__(self, "reviewed_at", aware(self.reviewed_at))


def attestation_bytes(record: HumanLabelRecord) -> bytes:
    values = {
        name: dict(record.labels)
        if name == "labels"
        else record.reviewed_at.isoformat()
        if name == "reviewed_at"
        else getattr(record, name)
        for name in record.__dataclass_fields__
        if name != "signature"
    }
    return json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class HmacHostVerifier:
    """Key is injected by an authenticated host; no key loading or signature issuance is provided."""

    key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.key) is not bytes or len(self.key) < 32:
            raise CalibrationError("host_verifier_key_required")

    def __call__(self, payload: bytes, signature: str) -> bool:
        expected = hmac.new(self.key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


@dataclass(frozen=True)
class VerifiedHumanRecord:
    record: HumanLabelRecord = field(repr=False)
    source_id: str = field(repr=False)


def verify_human_record(
    record: HumanLabelRecord,
    *,
    plan: BlindPlan,
    dataset: PrivateDataset,
    ledger: OpeningLedger,
    verifier: Callable[[bytes, str], bool] | None,
    clock: Clock,
) -> VerifiedHumanRecord:
    now = aware(clock.now())
    if (
        not isinstance(record, HumanLabelRecord)
        or not isinstance(plan, BlindPlan)
        or (not isinstance(ledger, OpeningLedger) or ledger.plan_sha256 != plan.sha256)
    ):
        raise CalibrationError("human_binding_required")
    expected = (plan.scope.owner_id, plan.scope.reviewer_id, plan.sha256, plan.dataset_sha256, plan.rubric_sha256)
    actual = (record.owner_id, record.reviewer_id, record.plan_sha256, record.dataset_sha256, record.rubric_sha256)
    if actual != expected:
        raise CalibrationError("human_scope_or_version_mismatch")
    batch = next((batch for batch in plan.batches if batch.id == record.batch_id), None)
    ref = next((ref for ref in batch.refs if ref.blind_id == record.blind_id), None) if batch else None
    opening = next((entry for entry in ledger.entries if entry.batch_id == record.batch_id), None)
    if ref is None or opening is None or record.reviewed_at < opening.opened_at or record.reviewed_at > now:
        raise CalibrationError("human_batch_not_opened_or_bound")
    if record.payload_sha256 != blind_payload_digest(blind_payload(dataset, plan, batch)):
        raise CalibrationError("human_displayed_payload_mismatch")
    if verifier is None:
        raise CalibrationError("trusted_human_attestation_unavailable")
    try:
        accepted = verifier(attestation_bytes(record), record.signature)
    except Exception:
        raise CalibrationError("human_attestation_failed") from None
    if accepted is not True:
        raise CalibrationError("human_attestation_failed")
    return VerifiedHumanRecord(record, ref.sample_id)
