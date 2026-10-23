"""Z1 estimates from an application-injected, locally pinned public K3 counter.

This module does not download a vocabulary, implement a substitute tokenizer or
claim server framing equivalence. An unconfigured runtime remains unavailable.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol

from mingjing_core.models.port import ChatMessage, ToolSpec

from .context_tokens import TokenReading
from .context_types import ContextInputError, InputMeterUnverified, MeterResult

DEFAULT_FACTOR = Decimal("1.15")
FRAMING_ALLOWANCE = 4_000


class PublicK3Counter(Protocol):
    """Trusted wiring must bind the verified artifact to its actual local encoder."""

    version: str
    artifact_sha256: str
    encoder_version: str
    encoder_sha256: str
    live_admissible: bool

    def count(self, text: str) -> int: ...


@dataclass(frozen=True)
class PinnedK3Counter:
    artifact: Path
    version: str
    artifact_sha256: str
    encoder_artifact: Path
    encoder_version: str
    encoder_sha256: str
    encode: Callable[[str], Sequence[int]]
    live_admissible: bool = False

    def __post_init__(self) -> None:
        for path, version, expected in (
            (self.artifact, self.version, self.artifact_sha256),
            (self.encoder_artifact, self.encoder_version, self.encoder_sha256),
        ):
            valid = (
                path.is_absolute()
                and path.is_file()
                and not path.is_symlink()
                and isinstance(version, str)
                and bool(version.strip())
                and isinstance(expected, str)
                and re.fullmatch(r"[0-9a-f]{64}", expected)
            )
            if not valid or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise InputMeterUnverified()

    def count(self, text: str) -> int:
        # Encoding IDs, rather than characters or bytes, define the count.
        identifiers = self.encode(text)
        if not isinstance(identifiers, Sequence) or any(type(value) is not int or value < 0 for value in identifiers):
            raise ContextInputError("context_tokenizer_output_invalid")
        return len(identifiers)


def factor_value(value: str | Decimal) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ContextInputError("context_token_factor_invalid") from None
    if not result.is_finite() or result < DEFAULT_FACTOR:
        raise ContextInputError("context_token_factor_invalid")
    return result


class K3EstimatedMeter:
    version = "public_k3_estimate_v1"
    model = "k3-256k"

    def __init__(self, counter: PublicK3Counter | None, *, factor: str = "1.15", model: str = "k3-256k") -> None:
        if counter is None:
            raise InputMeterUnverified()
        if not isinstance(model, str) or not model.strip():
            raise InputMeterUnverified()
        identities = (counter.version, counter.encoder_version)
        hashes = (counter.artifact_sha256, counter.encoder_sha256)
        if any(not isinstance(value, str) or not value.strip() for value in identities) or any(
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes
        ):
            raise InputMeterUnverified()
        self.counter, self.factor = counter, factor_value(factor)
        self.model = model
        self.live_admissible = counter.live_admissible is True
        self.provider = "kimi" if self.live_admissible else "scripted"
        self.tokenizer_version, self.tokenizer_sha256 = identities[0], hashes[0]
        self.encoder_version, self.encoder_sha256 = identities[1], hashes[1]
        self.estimate_multiplier = str(self.factor)
        self.framing_allowance = FRAMING_ALLOWANCE

    def measure(
        self, messages: tuple[ChatMessage, ...], tools: tuple[ToolSpec, ...], *, tool_choice: str
    ) -> TokenReading:
        payload = json.dumps(
            {
                "messages": [asdict(row) for row in messages],
                "tools": [asdict(row) for row in tools],
                "tool_choice": tool_choice,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        estimated = self.counter.count(payload)
        if type(estimated) is not int or estimated < 0:
            raise ContextInputError("context_tokenizer_output_invalid")
        upper = int((Decimal(estimated) * self.factor).to_integral_value(rounding=ROUND_CEILING)) + FRAMING_ALLOWANCE
        return TokenReading(estimated, upper)


def calibration(previous: dict, meter: MeterResult, actual: int | None) -> dict:
    """Record an estimate breach as evidence; never relabel usage as a prediction."""
    current = factor_value(meter.estimate_multiplier or str(DEFAULT_FACTOR))
    identity = ":".join(
        str(value or "")
        for value in (
            meter.token_meter_version,
            meter.tokenizer_version,
            meter.tokenizer_sha256,
            meter.encoder_version,
            meter.encoder_sha256,
            meter.provider,
            meter.model,
        )
    )
    if previous.get("identity") == identity:
        current = max(current, factor_value(previous.get("factor", str(DEFAULT_FACTOR))))
    breached = (
        actual is not None and meter.input_token_upper_bound is not None and actual > meter.input_token_upper_bound
    )
    estimated = meter.estimated_input_tokens
    if breached and type(estimated) is int and estimated > 0:
        current = max(current, Decimal(actual) / Decimal(estimated) * Decimal("1.1"))
    return {
        "identity": identity,
        "factor": str(current),
        "upper_bound_breached": breached,
        "calibration_unavailable": breached and not estimated,
    }
