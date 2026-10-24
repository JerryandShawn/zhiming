"""R16 connection approval cannot select a core model or consume old equivalence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .quota_delegated import DEADLINE
from .quota_r11 import validate_r11
from .quota_types import GuardRejected, instant

_SEAL = object()


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


def connection_approval(value: Any, candidate: str, now: datetime) -> K31ConnectionApproval:
    # The operator boundary must additionally bind HEAD/source and reread raw
    # reports; a scripted gate grants connection checks, never a core selection.
    validate_r11(value, candidate)
    source = value["source_sha256"]
    approval = K31ConnectionApproval(candidate, source, DEADLINE, (_SEAL, candidate, source, DEADLINE))
    approval.check(now)
    return approval
