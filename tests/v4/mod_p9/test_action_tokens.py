"""Offline capability lifecycle, cross-scope, atomicity, and privacy contracts."""

import hashlib
import json
import re
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.adapters.channels.action_token_contracts import (
    ActionTokenClaim,
    ActionTokenRecord,
)
from mingjing_core.adapters.channels.action_tokens import (
    ActionTokenError,
    ActionTokenService,
    MemoryActionTokenStore,
)
from mingjing_core.timekit.clock import FrozenClock

START = datetime(2026, 10, 19, 0, tzinfo=UTC)
CLAIM = {
    "owner_id": "synthetic-owner",
    "subject_id": "self",
    "open_id": "ou_SyntheticUser",
    "kind": "memory_undo",
    "entity_id": "synthetic-receipt",
    "payload_fingerprint": "a" * 64,
}


def setup(*, at: datetime = START, **kwargs):
    clock = FrozenClock(at)
    store = MemoryActionTokenStore()
    return ActionTokenService(store, clock=clock, **kwargs), store, clock


def test_first_consumption_is_one_shot_and_valid_replay_has_same_operation_and_time() -> (
    None
):
    service, store, clock = setup()
    issued = service.issue(**CLAIM)
    first = service.consume(issued.token, **CLAIM)
    clock.advance(timedelta(seconds=1))
    replay = service.consume(issued.token, **CLAIM)
    assert first.should_execute and not first.replayed
    assert replay.replayed and not replay.should_execute
    assert replay.operation_id == first.operation_id == issued.operation_id
    assert replay.used_at == first.used_at == START
    assert store.snapshot()[0].used_at == START


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", "another-owner"),
        ("subject_id", "another-subject"),
        ("open_id", "ou_Attacker"),
        ("kind", "proposal_accept"),
        ("entity_id", "another-receipt"),
        ("payload_fingerprint", "b" * 64),
    ],
)
def test_bad_actor_or_wrong_action_binding_cannot_burn_a_valid_token(
    field: str, value: str
) -> None:
    service, store, _ = setup()
    issued = service.issue(**CLAIM)
    bad = {**CLAIM, field: value}
    with pytest.raises(ActionTokenError):
        service.consume(issued.token, **bad)
    assert store.snapshot()[0].used_at is None
    assert service.consume(issued.token, **CLAIM).should_execute


def test_replay_still_validates_the_actor_and_does_not_reveal_operation_to_wrong_owner() -> (
    None
):
    service, _, _ = setup()
    issued = service.issue(**CLAIM)
    service.consume(issued.token, **CLAIM)
    with pytest.raises(ActionTokenError):
        service.consume(issued.token, **{**CLAIM, "owner_id": "another-owner"})


def test_expiry_is_half_open_and_expired_attempt_does_not_mark_used() -> None:
    service, store, clock = setup()
    issued = service.issue(**CLAIM, ttl=timedelta(seconds=2))
    clock.advance(timedelta(seconds=2))
    with pytest.raises(ActionTokenError):
        service.consume(issued.token, **CLAIM)
    assert store.snapshot()[0].used_at is None


def test_one_microsecond_before_expiry_is_still_valid() -> None:
    service, _, clock = setup()
    issued = service.issue(**CLAIM, ttl=timedelta(seconds=2))
    clock.advance(timedelta(seconds=2, microseconds=-1))
    assert service.consume(issued.token, **CLAIM).should_execute


def test_expired_replay_never_reopens_used_token() -> None:
    service, store, clock = setup()
    issued = service.issue(**CLAIM, ttl=timedelta(seconds=2))
    service.consume(issued.token, **CLAIM)
    clock.advance(timedelta(seconds=2))
    with pytest.raises(ActionTokenError):
        service.consume(issued.token, **CLAIM)
    assert store.snapshot()[0].used_at == START


def test_clock_rollback_before_issuance_is_rejected_without_burning() -> None:
    service, store, clock = setup()
    issued = service.issue(**CLAIM)
    clock.advance(timedelta(seconds=-1))
    with pytest.raises(ActionTokenError):
        service.consume(issued.token, **CLAIM)
    assert store.snapshot()[0].used_at is None


def test_32_concurrent_consumers_have_exactly_one_execute_winner() -> None:
    service, store, _ = setup()
    issued = service.issue(**CLAIM)
    barrier = threading.Barrier(32)

    def consume_once():
        barrier.wait(timeout=10)
        return service.consume(issued.token, **CLAIM)

    with ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(lambda _: consume_once(), range(32)))
    assert sum(result.should_execute for result in results) == 1
    assert len({result.operation_id for result in results}) == 1
    assert len(store.snapshot()) == 1


def test_failure_after_atomic_consume_never_mints_a_retry_capability() -> None:
    class FailAfterConsume(MemoryActionTokenStore):
        fail_once = True

        def consume(self, digest, claim, *, now):
            result = super().consume(digest, claim, now=now)
            if self.fail_once:
                self.fail_once = False
                raise RuntimeError("synthetic-private-backend-body")
            return result

    store = FailAfterConsume()
    service = ActionTokenService(store, clock=FrozenClock(START))
    issued = service.issue(**CLAIM)
    with pytest.raises(ActionTokenError) as failure:
        service.consume(issued.token, **CLAIM)
    assert "synthetic-private-backend-body" not in str(failure.value)
    assert not service.consume(issued.token, **CLAIM).should_execute
    assert store.snapshot()[0].used_at == START


def test_business_failure_does_not_undo_the_capability_consumption() -> None:
    service, _, _ = setup()
    issued = service.issue(**CLAIM)
    first = service.consume(issued.token, **CLAIM)
    assert first.should_execute
    # The business transaction may fail; only its stable operation is reconciled, never this token reopened.
    assert not service.consume(issued.token, **CLAIM).should_execute


def test_duplicate_card_issuance_preserves_business_operation_across_distinct_secrets() -> (
    None
):
    service, _, _ = setup()
    first, second = service.issue(**CLAIM), service.issue(**CLAIM)
    assert first.token != second.token
    assert first.operation_id == second.operation_id
    executed_operations = set()
    for issued in (first, second):
        result = service.consume(issued.token, **CLAIM)
        if result.should_execute:
            executed_operations.add(result.operation_id)
    assert len(executed_operations) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", "another-owner"),
        ("subject_id", "another-subject"),
        ("kind", "proposal_accept"),
        ("entity_id", "another-entity"),
        ("payload_fingerprint", "b" * 64),
    ],
)
def test_operation_is_bound_to_every_business_scope_field(
    field: str, value: str
) -> None:
    service, _, _ = setup()
    assert (
        service.issue(**CLAIM).operation_id
        != service.issue(**{**CLAIM, field: value}).operation_id
    )


def test_store_and_reprs_never_retain_raw_secret_or_private_payload() -> None:
    service, store, _ = setup()
    private = "synthetic-private-choice-body-XYZ"
    fingerprint = hashlib.sha256(private.encode()).hexdigest()
    issued = service.issue(**{**CLAIM, "payload_fingerprint": fingerprint})
    record = store.snapshot()[0]
    serialised = json.dumps(asdict(record), default=str)
    assert record.digest != issued.token and re.fullmatch(
        r"[a-f0-9]{64}", record.digest
    )
    assert issued.token not in serialised and private not in serialised
    assert issued.token not in repr(issued) and issued.token not in repr(record)
    assert set(asdict(record)) == {
        "digest",
        "claim",
        "created_at",
        "expires_at",
        "operation_id",
        "used_at",
    }


def test_cryptographic_source_requests_32_bytes_per_capability(monkeypatch) -> None:
    original = secrets.token_urlsafe
    requested = []

    def record_entropy(size):
        requested.append(size)
        return original(size)

    monkeypatch.setattr(
        "mingjing_core.adapters.channels.action_tokens.secrets.token_urlsafe",
        record_entropy,
    )
    service, _, _ = setup()
    tokens = {service.issue(**CLAIM).token for _ in range(100)}
    assert len(tokens) == 100 and requested == [32] * 100
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{43}", token) for token in tokens)


def test_digest_collision_is_bounded_and_does_not_replace_existing_capability(
    monkeypatch,
) -> None:
    service, store, _ = setup()
    first = service.issue(**CLAIM)
    monkeypatch.setattr(
        "mingjing_core.adapters.channels.action_tokens.secrets.token_urlsafe",
        lambda _: first.token,
    )
    with pytest.raises(ActionTokenError):
        service.issue(**{**CLAIM, "entity_id": "another-entity"})
    assert len(store.snapshot()) == 1
    assert service.consume(first.token, **CLAIM).should_execute


@pytest.mark.parametrize(
    "ttl", [timedelta(0), timedelta(seconds=-1), timedelta(hours=25), 1, True, "15m"]
)
def test_invalid_or_excessive_ttl_is_rejected_before_storage(ttl) -> None:
    service, store, _ = setup()
    with pytest.raises(ActionTokenError):
        service.issue(**CLAIM, ttl=ttl)
    assert store.snapshot() == ()


@pytest.mark.parametrize(
    "value", ["", "a" * 42, "a" * 44, "private-body-marker", None, True, []]
)
def test_malformed_token_uses_only_generic_public_error(value) -> None:
    service, _, _ = setup()
    with pytest.raises(ActionTokenError) as failure:
        service.consume(value, **CLAIM)
    assert failure.value.code == "ACTION_TOKEN_INVALID"
    assert "private-body-marker" not in str(failure.value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", ""),
        ("owner_id", " bad"),
        ("owner_id", "bad\nowner"),
        ("subject_id", ""),
        ("entity_id", ""),
        ("open_id", "oc_Chat"),
        ("open_id", "ou_bad-id"),
        ("kind", "bad action"),
        ("kind", "Upper"),
        ("payload_fingerprint", "x" * 64),
        ("payload_fingerprint", "A" * 64),
        ("payload_fingerprint", "private-payload-body"),
    ],
)
def test_action_binding_inputs_are_strict_without_echoing_private_values(
    field, value
) -> None:
    service, store, _ = setup()
    with pytest.raises(ActionTokenError) as failure:
        service.issue(**{**CLAIM, field: value})
    assert "private-payload-body" not in str(failure.value)
    assert store.snapshot() == ()


def test_configurable_default_ttl_and_dst_use_utc_elapsed_time() -> None:
    local = datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo("America/New_York"), fold=0)
    service, store, clock = setup(at=local, default_ttl=timedelta(hours=2))
    issued = service.issue(**CLAIM)
    assert issued.expires_at == clock.now() + timedelta(hours=2)
    assert store.snapshot()[0].created_at.tzinfo == UTC
    assert issued.expires_at.tzinfo == UTC


def test_memory_capacity_failure_does_not_invalidate_existing_tokens() -> None:
    store = MemoryActionTokenStore(capacity=1)
    service = ActionTokenService(store, clock=FrozenClock(START))
    first = service.issue(**CLAIM)
    with pytest.raises(ActionTokenError):
        service.issue(**{**CLAIM, "entity_id": "second"})
    assert service.consume(first.token, **CLAIM).should_execute


def test_store_rejects_invalid_record_metadata_without_mutating_existing_snapshot() -> (
    None
):
    service, store, _ = setup()
    service.issue(**CLAIM)
    record = store.snapshot()[0]
    with pytest.raises(ActionTokenError):
        replace(record, used_at=record.expires_at)
    with pytest.raises(ActionTokenError):
        ActionTokenRecord(
            record.digest, ActionTokenClaim(**CLAIM), START, START, record.operation_id
        )
    assert store.snapshot() == (record,)


def test_candidate_default_ttl_is_15_minutes_and_can_be_overridden() -> None:
    service, _, _ = setup()
    assert service.issue(**CLAIM).expires_at == START + timedelta(minutes=15)
    assert service.issue(
        **CLAIM, ttl=timedelta(minutes=2)
    ).expires_at == START + timedelta(minutes=2)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"default_ttl": timedelta(0)},
        {"default_ttl": True},
        {"max_ttl": timedelta(minutes=1)},
        {"max_ttl": "24h"},
    ],
)
def test_constructor_rejects_invalid_ttl_policy(kwargs) -> None:
    with pytest.raises(ActionTokenError):
        setup(**kwargs)


def test_naive_clock_and_failing_storage_use_only_generic_errors() -> None:
    class NaiveClock:
        def now(self):
            return START.replace(tzinfo=None)

    class FailingStore(MemoryActionTokenStore):
        def put_if_absent(self, record):
            raise RuntimeError("synthetic-private-provider-body")

    for store, clock in (
        (MemoryActionTokenStore(), NaiveClock()),
        (FailingStore(), FrozenClock(START)),
    ):
        service = ActionTokenService(store, clock=clock)
        with pytest.raises(ActionTokenError) as failure:
            service.issue(**CLAIM)
        assert "synthetic-private-provider-body" not in str(failure.value)
        assert store.snapshot() == ()
