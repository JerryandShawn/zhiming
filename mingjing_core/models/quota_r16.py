"""R16 connection approval cannot select a core model or consume old equivalence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .quota_delegated import DEADLINE
from .quota_r11 import validate_r11
from .quota_types import GuardRejected, instant

_SEAL = object()
_CORE_SEAL = object()


@dataclass(frozen=True)
class K31ConnectionApproval:
    candidate: str
    source_sha256: str
    expires_at: datetime
    _seal: object = field(repr=False)

    def check(self, now: datetime) -> None:
        if (
            self._seal != (_SEAL, self.candidate, self.source_sha256, self.expires_at)
            or instant(now) >= self.expires_at
            or self.expires_at > DEADLINE
        ):
            raise GuardRejected("authorization_expired")


def connection_approval(
    value: Any, candidate: str, now: datetime
) -> K31ConnectionApproval:
    # The operator boundary must additionally bind HEAD/source and reread raw
    # reports; a scripted gate grants connection checks, never a core selection.
    validate_r11(value, candidate)
    source = value["source_sha256"]
    approval = K31ConnectionApproval(
        candidate, source, DEADLINE, (_SEAL, candidate, source, DEADLINE)
    )
    approval.check(now)
    return approval


@dataclass(frozen=True)
class K31CoreApproval:
    candidate: str
    source_sha256: str
    expires_at: datetime
    proof_sha256: str
    factor: str
    _seal: object = field(repr=False)

    def check(self, now: datetime) -> None:
        if (
            self._seal
            != (
                _CORE_SEAL,
                self.candidate,
                self.source_sha256,
                self.expires_at,
                self.proof_sha256,
                self.factor,
            )
            or instant(now) >= self.expires_at
            or self.expires_at > DEADLINE
        ):
            raise GuardRejected("authorization_expired")


def _core_approval(
    scripted: K31ConnectionApproval, proof: str, factor: str
) -> K31CoreApproval:
    fields = (
        scripted.candidate,
        scripted.source_sha256,
        scripted.expires_at,
        proof,
        factor,
    )
    return K31CoreApproval(*fields, (_CORE_SEAL, *fields))


def approved_core_model(approval: Any, now: datetime) -> str:
    """Select only from a sealed core approval; a connection-only grant is insufficient."""
    from .quota_delegated import DelegatedApproval

    approval.check(now)
    if type(approval) is K31CoreApproval:
        return "k3.1-pro"
    if type(approval) is DelegatedApproval and type(approval.equivalent) is bool:
        return "k3-256k" if approval.equivalent else "k3"
    raise GuardRejected("manual_start_required")


def core_token_stage(model: str) -> str:
    """Match the central delegated token naming; K31 is not core-k3.1-pro."""
    if model not in {"k3", "k3-256k", "k3.1-pro"}:
        raise GuardRejected("manual_start_required")
    return "core-k31" if model == "k3.1-pro" else "core-" + model
