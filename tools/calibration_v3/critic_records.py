"""Observation metadata only; no model request, implicit label or runtime permission."""

from dataclasses import dataclass, field

from .models import ITEMS, CalibrationError, PrivateDataset, PrivateSample, digest, fingerprint, identity, label_vector

SEVERITY = {
    "E1": 5,
    "E2": 5,
    "E3": 4,
    "E4": 3,
    "E5": 4,
    "E6": 5,
    "J1": 4,
    "J2": 5,
    "J3": 3,
    "J4": 3,
    "J5": 4,
    "J6": 5,
    "J7": 3,
    "J8": 2,
    "J9": 2,
}


@dataclass(frozen=True)
class CalibrationProtocol:
    prompt_sha256: str | None
    rubric_sha256: str
    model: str = "k3-256k"
    effort: str = "high"
    prompt_version: str = "2.0.0"

    def __post_init__(self) -> None:
        if self.prompt_sha256 is not None:
            digest(self.prompt_sha256)
        digest(self.rubric_sha256)
        for value in (self.model, self.effort, self.prompt_version):
            identity(value)

    @property
    def current(self) -> bool:
        return self.prompt_sha256 is not None and (self.model, self.effort, self.prompt_version) == (
            "k3-256k",
            "high",
            "2.0.0",
        )


@dataclass(frozen=True)
class CriticObservation:
    sample_id: str = field(repr=False)
    input_sha256: str
    protocol: CalibrationProtocol
    artifact_sha256: str
    labels: tuple[tuple[str, bool], ...] = field(repr=False)
    confidence: tuple[tuple[str, int], ...] = field(repr=False)
    origin: str

    def __post_init__(self) -> None:
        identity(self.sample_id)
        digest(self.input_sha256)
        digest(self.artifact_sha256)
        if (
            not isinstance(self.protocol, CalibrationProtocol)
            or self.protocol.prompt_sha256 is None
            or self.origin not in {"critic_trace", "synthetic_test"}
        ):
            raise CalibrationError("critic_provenance_invalid")
        if (
            not isinstance(self.labels, tuple)
            or any(not isinstance(pair, tuple) or len(pair) != 2 for pair in self.labels)
            or label_vector(dict(self.labels)) != self.labels
        ):
            raise CalibrationError("critic_complete_labels_required")
        if (
            not isinstance(self.confidence, tuple)
            or len(self.confidence) != 15
            or set(dict(self.confidence)) != set(ITEMS)
        ):
            raise CalibrationError("critic_confidence_required")
        if any(type(value) is not int or not 1 <= value <= 3 for _, value in self.confidence):
            raise CalibrationError("critic_confidence_invalid")

    def effective(self, item: str) -> bool:
        return dict(self.labels)[item] and dict(self.confidence)[item] >= 2 and SEVERITY[item] >= 3


def input_digest(dataset: PrivateDataset, sample: PrivateSample) -> str:
    if sample not in dataset.samples:
        raise CalibrationError("critic_sample_dataset_mismatch")
    return fingerprint(
        {"common": dataset.common_context, "material": sample.material, "user": sample.user, "draft": sample.draft}
    )
