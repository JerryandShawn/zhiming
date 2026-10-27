"""Binary calibration statistics with explicit provenance gates, without inventing human labels."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from .critic_contracts import (
    CRITIC_PROMPT_VERSION,
    ITEM_TYPES,
    RUBRIC_VERSION,
    CalibrationState,
)


@dataclass(frozen=True)
class CalibrationIdentity:
    version: str
    model: str
    effort: str = "high"
    critic_prompt_version: str = CRITIC_PROMPT_VERSION
    rubric_version: str = RUBRIC_VERSION

    def __post_init__(self) -> None:
        if any(
            not isinstance(getattr(self, name), str) or not getattr(self, name).strip()
            for name in self.__dataclass_fields__
        ):
            raise ValueError(
                "calibration identity and versions must be nonempty strings"
            )

    def is_current_protocol(self, primary_model: str | None = None) -> bool:
        return (
            self.model,
            self.effort,
            self.critic_prompt_version,
            self.rubric_version,
        ) == (
            primary_model,
            "high",
            CRITIC_PROMPT_VERSION,
            RUBRIC_VERSION,
        )


@dataclass(frozen=True)
class CalibrationSample:
    id: str
    human_labels: Mapping[str, bool | None]
    critic_labels: Mapping[str, bool | None]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("calibration observation requires an id")
        for name in ("human_labels", "critic_labels"):
            values = dict(getattr(self, name))
            if set(values) - set(ITEM_TYPES):
                raise ValueError("unknown calibration item")
            if any(
                value is not None and type(value) is not bool
                for value in values.values()
            ):
                raise ValueError("binary labels must be actual booleans or missing")
            object.__setattr__(self, name, MappingProxyType(values))


@dataclass(frozen=True)
class CalibrationProvenance:
    labels_version: str
    brain_labeled_ids: frozenset[str]
    user_reviewed_ids: frozenset[str]
    user_random_ids: frozenset[str]
    known_disagreements: frozenset[str] = frozenset()
    adjudicated_ids: frozenset[str] = frozenset()

    def permits_revision(self, ids: set[str]) -> bool:
        return (
            bool(self.labels_version.strip())
            and len(ids) >= 60
            and self.brain_labeled_ids == ids
            and self.user_reviewed_ids <= ids
            and len(self.user_reviewed_ids) >= 15
            and self.user_random_ids <= self.user_reviewed_ids
            and len(self.user_random_ids) >= 10
            and self.known_disagreements <= self.user_reviewed_ids
            and self.adjudicated_ids <= ids
            and self.known_disagreements <= self.adjudicated_ids
        )


@dataclass(frozen=True)
class BinaryMetrics:
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    positives: int
    negatives: int
    paired_count: int
    sensitivity: float | None
    specificity: float | None
    agreement: float | None
    kappa: float | None
    agreement_wilson95: tuple[float, float] | None
    f1: float | None

    def as_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def wilson_interval(successes: int, total: int) -> tuple[float, float] | None:
    if (
        type(successes) is not int
        or type(total) is not int
        or not 0 <= successes <= total
    ):
        raise ValueError("Wilson interval requires integer 0 <= successes <= total")
    if total == 0:
        return None
    z = 1.959963984540054
    point = successes / total
    denominator = 1 + z * z / total
    centre = (point + z * z / (2 * total)) / denominator
    half = (
        z
        * math.sqrt(point * (1 - point) / total + z * z / (4 * total * total))
        / denominator
    )
    return max(0.0, centre - half), min(1.0, centre + half)


def binary_metrics(human: Sequence[bool], critic: Sequence[bool]) -> BinaryMetrics:
    if len(human) != len(critic):
        raise ValueError("calibration labels must be paired")
    if any(type(value) is not bool for value in (*human, *critic)):
        raise ValueError("calibration labels must be actual booleans")
    tp = sum(
        actual and predicted for actual, predicted in zip(human, critic, strict=True)
    )
    tn = sum(
        not actual and not predicted
        for actual, predicted in zip(human, critic, strict=True)
    )
    fp = sum(
        not actual and predicted
        for actual, predicted in zip(human, critic, strict=True)
    )
    fn = sum(
        actual and not predicted
        for actual, predicted in zip(human, critic, strict=True)
    )
    count, positives, negatives = len(human), tp + fn, tn + fp
    agreement = (tp + tn) / count if count else None
    chance_numerator = positives * (tp + fp) + negatives * (tn + fn)
    denominator = count * count - chance_numerator
    kappa = (
        (count * (tp + tn) - chance_numerator) / denominator if denominator else None
    )
    return BinaryMetrics(
        tp,
        tn,
        fp,
        fn,
        positives,
        negatives,
        count,
        tp / positives if positives else None,
        tn / negatives if negatives else None,
        agreement,
        kappa,
        wilson_interval(tp + tn, count),
        2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
    )


@dataclass(frozen=True)
class ItemCalibration:
    item: str
    metrics: BinaryMetrics
    missing_labels: int
    state: CalibrationState
    reason: str


@dataclass(frozen=True)
class CalibrationReport:
    identity: CalibrationIdentity
    items: tuple[ItemCalibration, ...]
    sample_count: int
    complete: bool
    provenance_verified: bool
    macro_f1: float | None
    macro_defined_items: int
    user_reviewed_count: int

    def state_for(
        self, item: str, *, primary_model: str | None = None
    ) -> CalibrationState:
        found = next((entry for entry in self.items if entry.item == item), None)
        if (
            not self.complete
            or not self.provenance_verified
            or not self.identity.is_current_protocol(primary_model)
        ):
            return "record_only"
        return found.state if found is not None else "record_only"

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": {
                name: getattr(self.identity, name)
                for name in self.identity.__dataclass_fields__
            },
            "sample_count": self.sample_count,
            "complete": self.complete,
            "provenance_verified": self.provenance_verified,
            "user_reviewed_count": self.user_reviewed_count,
            "macro_f1": self.macro_f1,
            "macro_defined_items": self.macro_defined_items,
            "items": [
                {
                    "item": row.item,
                    "metrics": row.metrics.as_dict(),
                    "missing_labels": row.missing_labels,
                    "state": self.state_for(
                        row.item, primary_model=self.identity.model
                    ),
                    "reason": row.reason,
                }
                for row in self.items
            ],
        }


def _threshold_state(item: str, metrics: BinaryMetrics) -> CalibrationState:
    if item in {"J8", "J9"} or metrics.kappa is None:
        return "record_only"
    if item.startswith("E"):
        passed = (
            metrics.kappa >= 0.7
            and metrics.sensitivity is not None
            and metrics.sensitivity >= 0.9
        )
    else:
        passed = (
            metrics.positives >= 5 and metrics.negatives >= 5 and metrics.kappa >= 0.5
        )
    return "revision_enabled" if passed else "record_only"


def _item_report(
    item: str,
    samples: Sequence[CalibrationSample],
    eligible: bool,
    defects: Mapping[str, bool],
) -> ItemCalibration:
    pairs = [
        (row.human_labels.get(item), row.critic_labels.get(item)) for row in samples
    ]
    valid = [
        (actual, predicted)
        for actual, predicted in pairs
        if type(actual) is bool and type(predicted) is bool
    ]
    metrics = binary_metrics([pair[0] for pair in valid], [pair[1] for pair in valid])
    state = (
        _threshold_state(item, metrics)
        if eligible and defects.get(item, True)
        else "record_only"
    )
    reason = (
        "threshold_passed"
        if state == "revision_enabled"
        else "insufficient_or_unverified_calibration"
    )
    if defects.get(item) is False:
        reason = "seeded_or_laxity_test_failed"
    elif eligible and state == "record_only":
        reason = "always_record_only" if item in {"J8", "J9"} else "threshold_not_met"
    return ItemCalibration(item, metrics, len(samples) - len(valid), state, reason)


def calculate_calibration(
    samples: Sequence[CalibrationSample],
    *,
    identity: CalibrationIdentity,
    provenance: CalibrationProvenance | None = None,
    defect_status: Mapping[str, bool] | None = None,
) -> CalibrationReport:
    ids = {row.id for row in samples}
    if len(ids) != len(samples):
        raise ValueError("calibration observation ids must be unique")
    defects = dict(defect_status or {})
    if set(defects) - set(ITEM_TYPES) or any(
        type(value) is not bool for value in defects.values()
    ):
        raise ValueError("defect results require known items and boolean outcomes")
    complete = len(samples) >= 60 and all(
        set(row.human_labels) == set(ITEM_TYPES)
        and set(row.critic_labels) == set(ITEM_TYPES)
        and all(
            type(value) is bool
            for value in (*row.human_labels.values(), *row.critic_labels.values())
        )
        for row in samples
    )
    verified = provenance is not None and provenance.permits_revision(ids)
    eligible = complete and verified and identity.is_current_protocol(identity.model)
    items = tuple(_item_report(item, samples, eligible, defects) for item in ITEM_TYPES)
    defined = sum(row.metrics.f1 is not None for row in items)
    fully_paired = bool(samples) and all(
        row.metrics.paired_count == len(samples) for row in items
    )
    macro = (
        sum(row.metrics.f1 for row in items) / len(items)
        if fully_paired and defined == len(items)
        else None
    )
    return CalibrationReport(
        identity,
        items,
        len(samples),
        complete,
        verified,
        macro,
        defined,
        len(provenance.user_reviewed_ids) if provenance else 0,
    )
