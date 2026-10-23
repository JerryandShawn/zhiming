"""Offline K3 capability boundaries; no callback, effect, refresh delivery or network is executed."""

import hashlib
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from random import Random
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.adapters.channels.action_token_contracts import ActionTokenError
from mingjing_core.adapters.channels.action_token_policy_v2 import (
    EXPIRED_CARD_MESSAGE,
    TTL_BY_KIND,
    K3TokenService,
    ttl_for_kind,
)
from mingjing_core.adapters.channels.action_token_refresh_v2 import MemoryTokenMetadataLookup, TokenMetadata
from mingjing_core.adapters.channels.action_token_store import MemoryActionTokenStore
from mingjing_core.adapters.channels.action_tokens import ActionTokenService
from mingjing_core.timekit.clock import FrozenClock

START = datetime(2026, 10, 21, 0, tzinfo=UTC)
CLAIM = dict(
    owner_id="synthetic-owner",
    subject_id="self",
    open_id="ou_syntheticActor",
    kind="question",
    entity_id="synthetic-entity",
    payload_fingerprint=hashlib.sha256(b"synthetic-payload").hexdigest(),
)


def setup(kind="question", *, at=START):
    store = MemoryActionTokenStore()
    clock = FrozenClock(at)
    lookup = MemoryTokenMetadataLookup(store)
    service = K3TokenService(store, clock=clock, lookup=lookup)
    return service, store, lookup, clock, {**CLAIM, "kind": kind}


@pytest.mark.parametrize(
    "kind,hours",
    [
        ("question", 24),
        ("decision", 24),
        ("memory_receipt", 24),
        ("brief", 24),
        ("delete_memory", 0.25),
        ("delete_source", 0.25),
        ("apply_organize", 0.25),
        ("apply_organization", 0.25),
    ],
)
def test_positive_allowlist_has_exact_k3_ttl(kind, hours):
    service, store, _, _, claim = setup(kind)
    issued = service.issue(**claim)
    assert issued.expires_at == START + timedelta(hours=hours)
    assert store.snapshot()[0].expires_at - store.snapshot()[0].created_at == timedelta(hours=hours)
    assert issued.token not in repr(issued) and issued.token not in repr(store.snapshot())


@pytest.mark.parametrize("kind", tuple(TTL_BY_KIND))
def test_expiry_is_half_open_and_refresh_never_consumes_or_executes(kind):
    service, store, _, clock, claim = setup(kind)
    issued = service.issue(**claim)
    clock.at = issued.expires_at
    expired = service.consume(issued.token, **claim)
    assert expired.refresh_needed and not expired.should_execute and expired.consumption is None
    assert expired.message == EXPIRED_CARD_MESSAGE == "这张卡已过期，我重新发一张"
    assert expired.operation_id == issued.operation_id and store.snapshot()[0].used_at is None
    clock.at = issued.expires_at - timedelta(microseconds=1)
    allowed = service.consume(issued.token, **claim)
    assert allowed.should_execute and not allowed.refresh_needed
    clock.at = issued.expires_at + timedelta(microseconds=1)
    assert service.consume(issued.token, **claim).refresh_needed


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", "another"),
        ("subject_id", "another"),
        ("open_id", "ou_anotherActor"),
        ("kind", "delete_memory"),
        ("entity_id", "another"),
        ("payload_fingerprint", "0" * 64),
    ],
)
def test_wrong_binding_never_discovers_expiry(field, value):
    service, _, _, clock, claim = setup()
    issued = service.issue(**claim)
    clock.at = issued.expires_at
    with pytest.raises(ActionTokenError) as caught:
        service.consume(issued.token, **{**claim, field: value})
    assert str(caught.value) != EXPIRED_CARD_MESSAGE


@pytest.mark.parametrize("kind", ["unknown", "memory_undo", "Question", "", True, None])
def test_unknown_kinds_have_no_long_ttl_fallback(kind):
    with pytest.raises(ActionTokenError):
        ttl_for_kind(kind)


@pytest.mark.parametrize("danger", ["delete_memory", "delete_source", "apply_organize"])
def test_dangerous_action_cannot_borrow_visual_question_category(danger):
    service, store, _, _, claim = setup()
    with pytest.raises(ActionTokenError):
        service.issue(**claim, asserted_action=danger)
    issued = service.issue(**{**claim, "kind": danger}, asserted_action=danger)
    assert issued.expires_at == START + timedelta(minutes=15)
    with pytest.raises(ActionTokenError):
        service.consume(issued.token, **claim)
    assert store.snapshot()[0].used_at is None


def test_arbitrary_ttl_override_is_not_part_of_policy_api():
    service, _, _, _, claim = setup("delete_source")
    with pytest.raises(TypeError):
        service.issue(**claim, ttl=timedelta(hours=24))


def test_replay_is_atomic_and_keeps_old_operation_and_first_use_time():
    service, _, _, clock, claim = setup()
    issued = service.issue(**claim)
    first = service.consume(issued.token, **claim)
    clock.advance(timedelta(minutes=1))
    again = service.consume(issued.token, **claim)
    assert first.should_execute and not again.should_execute and again.consumption.replayed
    assert first.operation_id == again.operation_id == issued.operation_id
    assert first.consumption.used_at == again.consumption.used_at == START


def test_duplicate_issue_and_refresh_keep_legacy_business_operation_identity():
    service, store, _, clock, claim = setup()
    first = service.issue(**claim)
    legacy = ActionTokenService(store, clock=clock).issue(**claim, ttl=timedelta(hours=24))
    assert first.operation_id == legacy.operation_id and first.token != legacy.token
    clock.advance(timedelta(days=2))
    expired = service.consume(first.token, **claim)
    refreshed = service.issue(**claim)
    assert expired.refresh_needed and refreshed.operation_id == first.operation_id
    # The host still checks source/entity and its business operation ledger before any effect.
    assert refreshed.expires_at == clock.now() + timedelta(hours=24)


def test_revocation_wins_even_for_a_correctly_bound_expired_capability():
    service, store, lookup, clock, claim = setup()
    issued = service.issue(**claim)
    lookup.revoke(store.snapshot()[0].digest)
    clock.at = issued.expires_at
    with pytest.raises(ActionTokenError):
        service.consume(issued.token, **claim)
    assert store.snapshot()[0].used_at is None


def test_delayed_metadata_read_rechecks_clock_before_claim():
    service, store, lookup, clock, claim = setup()
    issued = service.issue(**claim)

    class DelayedLookup:
        def lookup(self, digest):
            clock.at = issued.expires_at
            return lookup.lookup(digest)

    guarded = K3TokenService(store, clock=clock, lookup=DelayedLookup())
    result = guarded.consume(issued.token, **claim)
    assert result.refresh_needed and not result.should_execute and store.snapshot()[0].used_at is None


def test_unknown_well_formed_raw_token_is_invalid_even_after_another_card_expires():
    service, _, _, clock, claim = setup()
    issued = service.issue(**claim)
    clock.at = issued.expires_at
    with pytest.raises(ActionTokenError) as caught:
        service.consume("Z" * 43, **claim)
    assert str(caught.value) != EXPIRED_CARD_MESSAGE


@pytest.mark.parametrize("status", ["unknown", "inactive", "revoked", "wrong_digest", "wrong_duration"])
def test_invalid_metadata_cannot_be_misreported_as_expired(status):
    service, store, _, clock, claim = setup()
    issued = service.issue(**claim)
    record = store.snapshot()[0]

    class Lookup:
        def lookup(self, digest):
            if status == "unknown":
                return None
            current = record
            if status == "wrong_digest":
                current = replace(current, digest="0" * 64)
            if status == "wrong_duration":
                current = replace(current, expires_at=current.expires_at - timedelta(minutes=1))
            return TokenMetadata(current, active=status != "inactive", revoked=status == "revoked")

    clock.at = issued.expires_at
    guarded = K3TokenService(store, clock=clock, lookup=Lookup())
    with pytest.raises(ActionTokenError):
        guarded.consume(issued.token, **claim)


class SyntheticStoreFailure(Exception):
    """Provider-defined class, without a real SDK or transport."""


@pytest.mark.parametrize("boundary", ["put", "consume", "lookup"])
def test_storage_errors_never_echo_tokens_paths_or_private_diagnostics(boundary):
    service, store, lookup, clock, claim = setup()
    issued = service.issue(**claim)

    class BrokenStore:
        def put_if_absent(self, record):
            if boundary == "put":
                raise SyntheticStoreFailure("synthetic private diagnostics/path")
            return store.put_if_absent(record)

        def consume(self, *args, **kwargs):
            raise SyntheticStoreFailure("synthetic private diagnostics/path")

    class BrokenLookup:
        def lookup(self, digest):
            raise SyntheticStoreFailure("synthetic private diagnostics/path")

    guarded = K3TokenService(BrokenStore(), clock=clock, lookup=BrokenLookup() if boundary == "lookup" else lookup)
    with pytest.raises(ActionTokenError) as caught:
        if boundary == "put":
            guarded.issue(**claim)
        else:
            guarded.consume(issued.token, **claim)
    rendered = "".join(traceback.format_exception(caught.value))
    assert "SyntheticStoreFailure" not in rendered and "synthetic private diagnostics/path" not in rendered
    assert issued.token not in rendered


def test_concurrent_valid_clicks_execute_at_most_once():
    service, store, _, _, claim = setup()
    issued = service.issue(**claim)
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda _: service.consume(issued.token, **claim), range(80)))
    assert sum(item.should_execute for item in results) == 1
    assert {item.operation_id for item in results} == {issued.operation_id}
    assert store.snapshot()[0].used_at == START


@pytest.mark.parametrize("zone", ["UTC", "Asia/Tokyo", "Asia/Shanghai", "America/New_York", "Pacific/Chatham"])
def test_ttl_is_elapsed_utc_time_independent_of_endpoint_or_host_timezone(monkeypatch, zone):
    monkeypatch.setenv("TZ", zone)
    monkeypatch.setenv("KIMI_BASE_URL", "https://synthetic.invalid/not-used")
    local = datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo(zone))
    service, _, _, _, claim = setup(at=local)
    issued = service.issue(**claim)
    assert issued.expires_at - local.astimezone(UTC) == timedelta(hours=24)


@pytest.mark.parametrize("seed", range(1000))
def test_random_replay_out_of_order_expiry_and_revocation_properties(seed):
    rng = Random(91261021 + seed)
    kind = rng.choice(tuple(TTL_BY_KIND))
    service, store, lookup, clock, claim = setup(kind)
    issued = service.issue(**claim)
    used_at, revoked = None, False
    duration = int((issued.expires_at - START).total_seconds())
    offsets = (-1, 0, 1, duration * 1_000_000 - 1, duration * 1_000_000, duration * 1_000_000 + 1)
    for _ in range(12):
        clock.at = START + timedelta(microseconds=rng.choice(offsets))
        if rng.randrange(12) == 0:
            lookup.revoke(store.snapshot()[0].digest)
            revoked = True
        malformed = rng.randrange(5) == 0
        supplied = {**claim, "owner_id": "another"} if malformed else claim
        if revoked or malformed or clock.now() < START:
            with pytest.raises(ActionTokenError):
                service.consume(issued.token, **supplied)
        else:
            result = service.consume(issued.token, **supplied)
            if clock.now() >= issued.expires_at:
                assert result.refresh_needed and not result.should_execute and result.consumption is None
            else:
                assert result.should_execute is (used_at is None)
                used_at = clock.now() if used_at is None else used_at
                assert result.consumption.used_at == used_at
                assert result.operation_id == issued.operation_id
        assert store.snapshot()[0].used_at == used_at
