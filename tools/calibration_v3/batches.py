"""Deterministic private blind mapping; public payloads exclude answer keys and original IDs."""

import re
from dataclasses import dataclass, field
from random import Random

from .blind_payload_contract import BLIND_PAYLOAD_SCHEMA, blind_payload_digest
from .models import ITEMS, CalibrationError, PrivateDataset, digest, fingerprint, identity


@dataclass(frozen=True)
class ReviewScope:
    owner_id: str
    reviewer_id: str

    def __post_init__(self) -> None:
        identity(self.owner_id)
        identity(self.reviewer_id)


@dataclass(frozen=True)
class BlindRef:
    blind_id: str
    sample_id: str = field(repr=False)
    item: str

    def __post_init__(self) -> None:
        if type(self.blind_id) is not str or re.fullmatch(r"b_[a-f0-9]{32}", self.blind_id) is None:
            raise CalibrationError("blind_id_invalid")
        identity(self.sample_id)
        if self.item not in ITEMS:
            raise CalibrationError("blind_item_invalid")


@dataclass(frozen=True)
class BlindBatch:
    id: str
    ordinal: int
    refs: tuple[BlindRef, ...] = field(repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.id) is not str
            or re.fullmatch(r"batch_[a-f0-9]{32}", self.id) is None
            or (type(self.ordinal) is not int or not 1 <= self.ordinal <= 5)
            or not isinstance(self.refs, tuple)
            or any(not isinstance(ref, BlindRef) for ref in self.refs)
        ):
            raise CalibrationError("blind_batch_invalid")


@dataclass(frozen=True)
class BlindPlan:
    scope: ReviewScope
    dataset_sha256: str
    rubric_sha256: str
    seed: int = field(repr=False)
    batches: tuple[BlindBatch, ...] = field(repr=False)

    def __post_init__(self) -> None:
        digest(self.dataset_sha256)
        digest(self.rubric_sha256)
        if (
            type(self.seed) is not int
            or not isinstance(self.scope, ReviewScope)
            or not isinstance(self.batches, tuple)
            or (len(self.batches) != 5 or any(not isinstance(batch, BlindBatch) for batch in self.batches))
        ):
            raise CalibrationError("blind_plan_shape_invalid")
        refs = [ref for batch in self.batches for ref in batch.refs]
        if len(refs) != 75 or len({ref.sample_id for ref in refs}) != 75 or len({ref.blind_id for ref in refs}) != 75:
            raise CalibrationError("blind_plan_coverage_invalid")
        for index, batch in enumerate(self.batches, 1):
            if batch.ordinal != index or len(batch.refs) != 15 or {ref.item for ref in batch.refs} != set(ITEMS):
                raise CalibrationError("blind_batch_shape_invalid")

    @property
    def sha256(self) -> str:
        return fingerprint(
            {
                "schema": "blind-plan-v3.1-no-target-hint",
                "owner": self.scope.owner_id,
                "reviewer": self.scope.reviewer_id,
                "dataset": self.dataset_sha256,
                "rubric": self.rubric_sha256,
                "seed": self.seed,
                "batches": [[(ref.blind_id, ref.sample_id, ref.item) for ref in batch.refs] for batch in self.batches],
            }
        )


def make_blind_plan(
    dataset: PrivateDataset, *, scope: ReviewScope, rubric_sha256: str, seed: int = 20261021
) -> BlindPlan:
    if not isinstance(dataset, PrivateDataset) or type(seed) is not int:
        raise CalibrationError("brain_dataset_and_integer_seed_required")
    rng = Random(seed)
    pools = {item: [sample for sample in dataset.samples if sample.item == item] for item in ITEMS}
    first = {}
    for item, samples in pools.items():
        if len(samples) != 5:
            raise CalibrationError("five_samples_per_item_required")
        rng.shuffle(samples)
        priority = [sample for sample in samples if sample.uncertain]
        if len(priority) > 1:
            raise CalibrationError("uncertain_stratification_invalid")
        selected = priority[0] if priority else samples[0]
        first[item] = selected
        samples.remove(selected)
    batches, previous = [], None
    for ordinal in range(1, 6):
        order = list(ITEMS)
        rng.shuffle(order)
        if order[0] == previous:
            order = order[1:] + order[:1]
        refs = []
        for item in order:
            sample = first[item] if ordinal == 1 else pools[item].pop()
            blind = (
                "b_"
                + fingerprint(
                    [BLIND_PAYLOAD_SCHEMA, scope.owner_id, scope.reviewer_id, dataset.sha256, seed, sample.source_id]
                )[:32]
            )
            refs.append(BlindRef(blind, sample.source_id, item))
        batch_id = (
            "batch_"
            + fingerprint([BLIND_PAYLOAD_SCHEMA, dataset.sha256, rubric_sha256, ordinal, [r.blind_id for r in refs]])[
                :32
            ]
        )
        batches.append(BlindBatch(batch_id, ordinal, tuple(refs)))
        previous = order[-1]
    return BlindPlan(scope, dataset.sha256, rubric_sha256, seed, tuple(batches))


def blind_payload(dataset: PrivateDataset, plan: BlindPlan, batch: BlindBatch) -> dict:
    if dataset.sha256 != plan.dataset_sha256 or batch not in plan.batches:
        raise CalibrationError("blind_payload_binding_mismatch")
    samples = {sample.source_id: sample for sample in dataset.samples}
    payload = {
        "schema": BLIND_PAYLOAD_SCHEMA,
        "batch_id": batch.id,
        "ordinal": batch.ordinal,
        "plan_sha256": plan.sha256,
        "rubric_sha256": plan.rubric_sha256,
        "owner_id": plan.scope.owner_id,
        "reviewer_id": plan.scope.reviewer_id,
        "common_material": dataset.common_context,
        "candidates": [
            {
                "id": ref.blind_id,
                "material": samples[ref.sample_id].material,
                "user": samples[ref.sample_id].user,
                "draft": samples[ref.sample_id].draft,
            }
            for ref in batch.refs
        ],
    }
    blind_payload_digest(payload)
    return payload
