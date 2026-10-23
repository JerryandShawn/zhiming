"""Public K3 ports with synthetic failures; generated tokens remain only in process memory."""

import json
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mingjing_core.adapters.channels.action_token_contracts import (
    ActionTokenClaim,
    ActionTokenError,
    ActionTokenRecord,
    IssuedActionToken,
    TokenConsumption,
)
from mingjing_core.adapters.channels.action_token_policy_v2 import K3TokenService
from mingjing_core.adapters.channels.action_token_refresh_v2 import MemoryTokenMetadataLookup, TokenMetadata
from mingjing_core.adapters.channels.action_token_store import MemoryActionTokenStore

ROOT = Path(__file__).resolve().parents[3]
AT = datetime(2026, 10, 21, 0, tzinfo=UTC)
FIXTURE = ROOT / "tools/eval/fixtures/mod_20261021/k3_public_boundaries_synthetic.json"
DIAGNOSTIC = json.loads(FIXTURE.read_text(encoding="utf-8"))["diagnostic"]
# The first-target harness redacts these exact secrets in memory before any log reaches disk.
SECRET_TOKENS: set[str] = set()


class SwitchClock:
    def __init__(self) -> None:
        self.at = AT
        self.mode = "aware"

    def now(self) -> datetime:
        if self.mode == "error":
            raise RuntimeError(DIAGNOSTIC)
        return self.at.replace(tzinfo=None) if self.mode == "naive" else self.at


class ObservedStore(MemoryActionTokenStore):
    def __init__(self) -> None:
        super().__init__()
        self.consume_calls = 0

    def consume(self, digest: str, claim: ActionTokenClaim, *, now: datetime) -> TokenConsumption:
        self.consume_calls += 1
        return super().consume(digest, claim, now=now)


class SnapshotPort:
    """A host may return a malformed container, while all actual records remain legally constructed."""

    def __init__(self, value: object, *, fail: bool = False) -> None:
        self.value, self.fail = value, fail

    def snapshot(self) -> object:
        if self.fail:
            raise RuntimeError(DIAGNOSTIC)
        return self.value


class GuardLookup:
    def __init__(self, lookup: MemoryTokenMetadataLookup, *, phase: str | None) -> None:
        self.lookup_port, self.phase = lookup, phase
        self.lookup_calls = 0

    @contextmanager
    def guard(self) -> Iterator[None]:
        if self.phase == "enter":
            raise RuntimeError(DIAGNOSTIC)
        yield
        if self.phase == "exit":
            raise RuntimeError(DIAGNOSTIC)

    def lookup(self, digest: str) -> TokenMetadata | None:
        self.lookup_calls += 1
        return self.lookup_port.lookup(digest)


@dataclass
class Capability:
    store: ObservedStore
    clock: SwitchClock
    lookup: MemoryTokenMetadataLookup
    service: K3TokenService
    claim: dict[str, str]
    issued: IssuedActionToken


def issue(service: K3TokenService, claim: dict[str, str]) -> IssuedActionToken:
    result = service.issue(**claim)
    SECRET_TOKENS.add(result.token)
    return result


def capability() -> Capability:
    store, clock = ObservedStore(), SwitchClock()
    lookup = MemoryTokenMetadataLookup(store)
    service = K3TokenService(store, clock=clock, lookup=lookup)
    claim = {
        "owner_id": "synthetic-owner-first",
        "subject_id": "self",
        "open_id": "ou_syntheticPublic",
        "kind": "question",
        "entity_id": "synthetic-entity-first",
        "payload_fingerprint": "a" * 64,
    }
    return Capability(store, clock, lookup, service, claim, issue(service, claim))


def assert_generic_error(error: ActionTokenError) -> None:
    rendered = "".join(traceback.format_exception(error))
    fixed_message = str(error) == str(ActionTokenError())
    leaked = DIAGNOSTIC in rendered or any(token in rendered for token in SECRET_TOKENS)
    assert fixed_message, "public_error_must_use_fixed_message"
    assert not leaked, "public_error_must_not_include_token_or_diagnostic"
    assert error.code == "ACTION_TOKEN_INVALID"


def assert_unconsumed(case: Capability) -> None:
    assert all(record.used_at is None for record in case.store.snapshot())


def sole_record(case: Capability) -> ActionTokenRecord:
    records = case.store.snapshot()
    assert len(records) == 1
    return records[0]


def assert_recovered_first_then_replay(case: Capability) -> None:
    case.clock.mode = "aware"
    first = case.service.consume(case.issued.token, **case.claim)
    assert first.should_execute and not first.refresh_needed
    assert first.operation_id == case.issued.operation_id
    replay = case.service.consume(case.issued.token, **case.claim)
    assert not replay.should_execute and not replay.refresh_needed
    assert replay.consumption is not None and replay.consumption.replayed
    assert replay.operation_id == first.operation_id
