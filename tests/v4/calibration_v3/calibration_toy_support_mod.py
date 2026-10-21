"""Protocol-only toy inputs; these are not design 25's hard-case texts or labels."""

import hashlib

from tools.calibration_v3.batches import BlindPlan, ReviewScope, make_blind_plan
from tools.calibration_v3.models import ITEMS, SECTION_ITEMS, PrivateDataset, PrivateSample, label_vector

TOY_BODY = "TOY_PRIVATE_BODY_NOT_FROM_BRAIN25"


def toy_dataset() -> PrivateDataset:
    samples = []
    for number, item in enumerate(SECTION_ITEMS, 1):
        for suffix in ("R1", "R2", "P1", "P2", "T"):
            labels = {name: name == item and suffix.startswith("R") for name in ITEMS}
            samples.append(
                PrivateSample(
                    f"{number}-{suffix}",
                    item,
                    "toy-context",
                    "toy-user",
                    TOY_BODY,
                    label_vector(labels),
                    2,
                    number <= 6 and suffix == "T",
                    number <= 4,
                    suffix[0],
                    "toy-rationale",
                )
            )
    return PrivateDataset(hashlib.sha256(b"independent-toy-data").hexdigest(), "toy-common", tuple(samples))


def toy_plan() -> tuple[PrivateDataset, BlindPlan]:
    dataset = toy_dataset()
    return dataset, make_blind_plan(dataset, scope=ReviewScope("toy-owner", "toy-reviewer"), rubric_sha256="b" * 64)
