"""Aggregate only: dual kappas, raw/effective critic views and failclosed candidate gates."""

from collections.abc import Callable, Sequence
from dataclasses import asdict

from mingjing_core.timekit.clock import Clock

from .batches import BlindPlan
from .critic_records import CalibrationProtocol, CriticObservation, input_digest
from .daily import ZONE, OpeningLedger, aware
from .human_provenance import HumanLabelRecord, VerifiedHumanRecord, verify_human_record
from .models import ITEMS, CalibrationError, PrivateDataset
from .statistics import BinaryMetrics, binary_metrics, bootstrap_kappa


def _human_records(
    records: Sequence[HumanLabelRecord],
    dataset: PrivateDataset,
    plan: BlindPlan,
    ledger: OpeningLedger,
    verifier: Callable | None,
    clock: Clock,
) -> dict:
    seen, result = {}, {}
    for record in records:
        if not isinstance(record, HumanLabelRecord):
            raise CalibrationError("typed_human_record_required")
        if record.record_id in seen:
            if seen[record.record_id] != record:
                raise CalibrationError("human_record_operation_changed")
            continue
        verified = verify_human_record(
            record, plan=plan, dataset=dataset, ledger=ledger, verifier=verifier, clock=clock
        )
        seen[record.record_id] = record
        key = (verified.source_id, record.stage)
        if key in result:
            raise CalibrationError("human_review_stage_duplicate")
        result[key] = verified
    for (sample_id, stage), entry in result.items():
        prior = result.get((sample_id, "review"))
        if stage == "adjudication" and (prior is None or entry.record.reviewed_at < prior.record.reviewed_at):
            raise CalibrationError("human_adjudication_prior_review_required")
    return result


def _critics(
    records: Sequence[CriticObservation], dataset: PrivateDataset, protocol: CalibrationProtocol
) -> dict[str, CriticObservation]:
    samples = {sample.source_id: sample for sample in dataset.samples}
    result = {}
    for record in records:
        if not isinstance(record, CriticObservation) or record.sample_id not in samples:
            raise CalibrationError("critic_sample_unknown")
        if record.protocol != protocol or record.input_sha256 != input_digest(dataset, samples[record.sample_id]):
            raise CalibrationError("critic_protocol_or_input_changed")
        if record.sample_id in result:
            if result[record.sample_id] != record:
                raise CalibrationError("critic_observation_conflict")
            continue
        result[record.sample_id] = record
    return result


def _gold(
    item: str, brain: bool, review: VerifiedHumanRecord | None, adjudication: VerifiedHumanRecord | None
) -> tuple[bool | None, bool]:
    if adjudication is not None:
        if item in adjudication.record.uncertain_items:
            return None, True
        return dict(adjudication.record.labels)[item], False
    if review is None:
        return brain, False
    human = dict(review.record.labels)[item]
    if item in review.record.uncertain_items or human != brain:
        return None, True
    return human, False


def _summarize(reference: list[bool], predicted: list[bool], seed: int) -> tuple[dict, BinaryMetrics]:
    metrics = binary_metrics(reference, predicted)
    return {
        "metrics": asdict(metrics),
        "kappa_bootstrap95": asdict(bootstrap_kappa(reference, predicted, seed=seed)),
    }, metrics


def _reasons(
    item: str,
    dataset: PrivateDataset,
    humans: dict,
    critics: dict,
    protocol: CalibrationProtocol,
    unresolved: int,
    hm: BinaryMetrics,
    cm: BinaryMetrics,
) -> list[str]:
    reasons = ["brain25_alone_requires_merged_baseline_and_seeded_set"]
    if not humans:
        reasons.append("no_verified_human_labels")
    if len(critics) != len(dataset.samples):
        reasons.append("critic_observations_incomplete")
    if any(record.origin != "critic_trace" for record in critics.values()):
        reasons.append("synthetic_critic_not_runtime_evidence")
    if unresolved:
        reasons.append("unadjudicated_or_uncertain_human_labels")
    if not protocol.current:
        reasons.append("protocol_requires_recalibration")
    if hm.kappa is None or hm.positives < 5 or hm.negatives < 5 or hm.kappa < 0.6:
        reasons.append("human_rubric_evidence_insufficient")
    if cm.kappa is None or cm.positives < 5 or cm.negatives < 5 or cm.kappa < 0.6:
        reasons.append("critic_evidence_insufficient")
    if item.startswith("E") and (cm.kappa is None or cm.kappa < 0.7 or cm.sensitivity is None or cm.sensitivity < 0.9):
        reasons.append("evidence_item_threshold_not_met")
    if item in {"J8", "J9"}:
        reasons.append("always_record_only")
    return reasons


def _item_report(
    item: str, dataset: PrivateDataset, humans: dict, critics: dict, protocol: CalibrationProtocol, seed: int
) -> dict:
    human_ref, human_guess, critic_ref, critic_raw, critic_effective = [], [], [], [], []
    unresolved = 0
    for sample in dataset.samples:
        brain = dict(sample.labels)[item]
        review, adjudication = humans.get((sample.source_id, "review")), humans.get((sample.source_id, "adjudication"))
        if review is not None and item not in review.record.uncertain_items:
            human_ref.append(brain)
            human_guess.append(dict(review.record.labels)[item])
        gold, pending = _gold(item, brain, review, adjudication)
        unresolved += int(pending)
        observation = critics.get(sample.source_id)
        if gold is not None and observation is not None:
            critic_ref.append(gold)
            critic_raw.append(dict(observation.labels)[item])
            critic_effective.append(observation.effective(item))
    human_report, hm = _summarize(human_ref, human_guess, seed)
    critic_report, cm = _summarize(critic_ref, critic_effective, seed + 1)
    raw_report, _ = _summarize(critic_ref, critic_raw, seed + 2)
    reasons = _reasons(item, dataset, humans, critics, protocol, unresolved, hm, cm)
    return {
        "item": item,
        "kappa_human": human_report,
        "kappa_critic_effective": critic_report,
        "kappa_critic_raw": raw_report,
        "unresolved_count": unresolved,
        "state": "record_only",
        "reasons": reasons,
    }


def build_calibration_report(
    dataset: PrivateDataset,
    plan: BlindPlan,
    *,
    protocol: CalibrationProtocol,
    clock: Clock,
    ledger: OpeningLedger | None = None,
    human_records: Sequence[HumanLabelRecord] = (),
    critic_records: Sequence[CriticObservation] = (),
    verifier: Callable | None = None,
    seed: int = 2026102104,
) -> dict:
    instant = aware(clock.now())
    if (
        not isinstance(dataset, PrivateDataset)
        or not isinstance(plan, BlindPlan)
        or not isinstance(protocol, CalibrationProtocol)
    ):
        raise CalibrationError("typed_calibration_binding_required")
    if plan.dataset_sha256 != dataset.sha256 or protocol.rubric_sha256 != plan.rubric_sha256 or type(seed) is not int:
        raise CalibrationError("report_dataset_protocol_binding_mismatch")
    ledger = OpeningLedger(plan.sha256) if ledger is None else ledger
    if not isinstance(ledger, OpeningLedger) or ledger.plan_sha256 != plan.sha256:
        raise CalibrationError("report_opening_ledger_mismatch")
    humans = _human_records(human_records, dataset, plan, ledger, verifier, clock)
    critics = _critics(critic_records, dataset, protocol)
    items = [
        _item_report(item, dataset, humans, critics, protocol, seed + index * 17) for index, item in enumerate(ITEMS)
    ]
    f1 = [item["kappa_critic_effective"]["metrics"]["f1"] for item in items]
    return {
        "schema": "calibration-aggregate-v3",
        "generated_at": instant.astimezone(ZONE).isoformat(),
        "dataset_sha256": dataset.sha256,
        "plan_sha256": plan.sha256,
        "protocol": asdict(protocol),
        "sample_count": 75,
        "dataset_sources": {"brain25": 75},
        "verified_human_reviewed_count": sum(stage == "review" for _, stage in humans),
        "critic_observation_count": len(critics),
        "items": items,
        "macro_f1": sum(f1) / 15 if all(value is not None for value in f1) else None,
        "metric_reference": "brain labels remain provisional except authenticated final adjudications",
        "macro_defined_items": sum(value is not None for value in f1),
        "mode": "record_only",
        "runtime_revision_enabled": False,
        "runtime_configuration_writes": 0,
        "limits": [
            "brain25 alone cannot enable revision; merged calibration adapter remains pending",
            "Host attestation authenticates a host statement, not physical observation of a human",
            "Critic observations are bound metadata; artifact contents and origin need independent host verification",
            "No human or critic observations are synthesized from brain labels",
            "Bootstrap resamples paired answers 2000 times; undefined draws are counted explicitly",
            "Crisis program routing is unchanged; no runtime configuration or model call is performed",
        ],
    }
