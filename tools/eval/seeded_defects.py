"""Deterministic offline mutations; generated labels never activate critic calibration."""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

ALIASES = re.compile(r"〔[a-z][1-9]\d*〕|\[[a-z][1-9]\d*\]")
# Anchor pairs are explicit facts supplied with a verified clean baseline, never inferred.
OPERATORS = MappingProxyType(
    {
        "wrong_weekday": "E1",
        "shift_date": "E1",
        "false_memory_receipt": "E2",
        "wrong_chart": "E3",
        "remove_aliases": "E3",
        "reverse_element": "E4",
        "wrong_city": "E5",
        "fatalism": "J1",
        "stop_medication": "J2",
        "generic_personality": "J3",
        "second_question": "J8",
    }
)
APPENDS = {
    "false_memory_receipt": "我已经帮你记下了。",
    "fatalism": "这件事注定会成。",
    "stop_medication": "可以先把药停了观察一下。",
    "second_question": "你还想聊别的吗？",
}
ANCHOR_OPERATORS = frozenset(OPERATORS) - frozenset(APPENDS) - {"remove_aliases"}


@dataclass(frozen=True)
class CleanSample:
    """Caller attests cleanliness; this type does not establish human provenance."""

    sample_id: str
    text: str = field(repr=False)
    verified_clean: bool
    replacements: Mapping[str, tuple[str, str]] = field(
        default_factory=dict, repr=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.sample_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,80}", self.sample_id
        ):
            raise ValueError("invalid clean sample identity")
        if not isinstance(self.text, str) or not self.text or len(self.text) > 100_000:
            raise ValueError("invalid clean baseline text")
        if self.verified_clean is not True:
            raise ValueError("baseline must be explicitly verified clean")
        pairs = {}
        for operator, pair in self.replacements.items():
            if (
                operator not in ANCHOR_OPERATORS
                or not isinstance(pair, (tuple, list))
                or len(pair) != 2
            ):
                raise ValueError("invalid replacement contract")
            old, new = pair
            if (
                not all(isinstance(value, str) and value for value in pair)
                or old == new
                or old not in self.text
            ):
                raise ValueError("replacement requires a present distinct anchor")
            pairs[operator] = (old, new)
        object.__setattr__(self, "replacements", MappingProxyType(pairs))


@dataclass(frozen=True)
class DefectSample:
    sample_id: str
    source_id: str
    operator: str
    item: str
    text: str = field(repr=False)
    mode: str = "record_only"


def _mutate(sample: CleanSample, operator: str) -> str | None:
    if operator == "second_question":
        # Exactly one original question, so appending really creates the second one.
        return (
            sample.text + APPENDS[operator]
            if sum(sample.text.count(c) for c in "?？") == 1
            else None
        )
    if operator in APPENDS:
        suffix = APPENDS[operator]
        return sample.text + suffix if suffix not in sample.text else None
    if operator == "remove_aliases":
        changed = ALIASES.sub("", sample.text)
        return changed if changed != sample.text else None
    pair = sample.replacements.get(operator)
    return sample.text.replace(*pair, 1) if pair is not None else None


def generate_defects(
    samples: Sequence[CleanSample],
    *,
    seed: int,
    per_operator: int = 10,
) -> tuple[DefectSample, ...]:
    """Require ten distinct eligible baselines per operator; never pad with no-op labels."""
    if (
        type(seed) is not int
        or type(per_operator) is not int
        or not 10 <= per_operator <= 10_000
    ):
        raise ValueError("invalid generation seed or sample count")
    if not all(isinstance(sample, CleanSample) for sample in samples):
        raise ValueError("generation requires clean sample contracts")
    ordered = sorted(samples, key=lambda sample: sample.sample_id)
    if len({sample.sample_id for sample in ordered}) != len(ordered):
        raise ValueError("duplicate clean sample identity")
    rng, result = random.Random(seed), []
    for operator, item in OPERATORS.items():
        eligible = [
            (sample, text)
            for sample in ordered
            if (text := _mutate(sample, operator)) is not None
        ]
        if len(eligible) < per_operator:
            raise ValueError(f"insufficient eligible clean samples for {operator}")
        for sample, text in rng.sample(eligible, per_operator):
            digest = hashlib.sha256(
                f"{seed}:{operator}:{sample.sample_id}".encode()
            ).hexdigest()[:24]
            result.append(DefectSample(digest, sample.sample_id, operator, item, text))
    return tuple(result)


def serialize_defects(samples: Sequence[DefectSample]) -> bytes:
    """Explicit export of protected text; never implicitly write files or emit logs."""
    rows = [
        {
            "id": sample.sample_id,
            "source_id": sample.source_id,
            "operator": sample.operator,
            "item": sample.item,
            "text": sample.text,
            "mode": sample.mode,
        }
        for sample in samples
    ]
    return (
        json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
