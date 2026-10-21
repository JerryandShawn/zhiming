"""Private synthetic samples and metadata with explicit brain provenance, never human labels."""

import hashlib
import json
import re
from dataclasses import dataclass, field

ITEMS = tuple([f"E{i}" for i in range(1, 7)] + [f"J{i}" for i in range(1, 10)])
SECTION_ITEMS = ("J5", "E1", "E5", "E2", "E3", "J1", "J2", "E6", "J8", "J7", "J9", "J6", "J3", "J4", "E4")


class CalibrationError(ValueError):
    """A fixed reason code; private samples and labels must never enter errors."""


def identity(value: object) -> None:
    if type(value) is not str or not value.strip() or len(value) > 160 or any(ord(c) < 32 for c in value):
        raise CalibrationError("identity_invalid")


def digest(value: object) -> None:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise CalibrationError("digest_invalid")


def fingerprint(value: object) -> str:
    try:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise CalibrationError("canonical_value_invalid") from None


def label_vector(values: object) -> tuple[tuple[str, bool], ...]:
    if not isinstance(values, dict) or set(values) != set(ITEMS) or any(type(v) is not bool for v in values.values()):
        raise CalibrationError("complete_boolean_labels_required")
    return tuple((item, values[item]) for item in ITEMS)


@dataclass(frozen=True)
class PrivateSample:
    source_id: str = field(repr=False)
    item: str
    material: str = field(repr=False)
    user: str = field(repr=False)
    draft: str = field(repr=False)
    labels: tuple[tuple[str, bool], ...] = field(repr=False)
    severity: int = field(repr=False)
    uncertain: bool = field(repr=False)
    j02: bool = field(repr=False)
    group: str = field(repr=False)
    rationale: str = field(repr=False)

    def __post_init__(self) -> None:
        if re.fullmatch(r"(?:[1-9]|1[0-5])-(?:R[12]|P[12]|T)", self.source_id) is None or self.item not in ITEMS:
            raise CalibrationError("sample_identity_invalid")
        for name in ("material", "user", "draft", "rationale"):
            if type(getattr(self, name)) is not str or not getattr(self, name).strip():
                raise CalibrationError("sample_content_missing")
        if type(self.severity) is not int or not 1 <= self.severity <= 5:
            raise CalibrationError("severity_invalid")
        if type(self.uncertain) is not bool or type(self.j02) is not bool or self.group not in {"R", "P", "T"}:
            raise CalibrationError("sample_annotation_invalid")
        if (
            not isinstance(self.labels, tuple)
            or any(not isinstance(pair, tuple) or len(pair) != 2 for pair in self.labels)
            or label_vector(dict(self.labels)) != self.labels
        ):
            raise CalibrationError("sample_labels_invalid")


@dataclass(frozen=True)
class PrivateDataset:
    source_sha256: str
    common_context: str = field(repr=False)
    samples: tuple[PrivateSample, ...] = field(repr=False)
    provenance: str = "brain_ai"

    def __post_init__(self) -> None:
        digest(self.source_sha256)
        if (
            self.provenance != "brain_ai"
            or type(self.common_context) is not str
            or not self.common_context.strip()
            or (
                not isinstance(self.samples, tuple)
                or len(self.samples) != 75
                or any(not isinstance(sample, PrivateSample) for sample in self.samples)
            )
        ):
            raise CalibrationError("brain_dataset_shape_invalid")
        if len({sample.source_id for sample in self.samples}) != 75:
            raise CalibrationError("sample_id_duplicate")

    @property
    def sha256(self) -> str:
        return fingerprint(
            {
                "source": self.source_sha256,
                "common": self.common_context,
                "samples": [private_record(sample) for sample in self.samples],
            }
        )


def private_record(sample: PrivateSample) -> dict:
    return {
        name: dict(sample.labels) if name == "labels" else getattr(sample, name) for name in sample.__dataclass_fields__
    }
