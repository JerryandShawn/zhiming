"""Independent K3 duration, exact expiry and non-disclosing capability binding tests."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random

import pytest

from mingjing_core.adapters.channels.action_token_contracts import ActionTokenError
from mingjing_core.adapters.channels.action_token_policy_v2 import K3TokenService, ttl_for_kind
from mingjing_core.adapters.channels.action_token_refresh_v2 import MemoryTokenMetadataLookup
from mingjing_core.adapters.channels.action_token_store import MemoryActionTokenStore
from mingjing_core.adapters.channels.action_tokens import ActionTokenService
from mingjing_core.timekit.clock import FrozenClock

TRUTH = json.loads((Path(__file__).parent / "fixtures/acceptance_expected_mod.json").read_bytes())
AT = datetime(2026, 10, 21, tzinfo=UTC)


def setup(kind):
    clock, store = FrozenClock(AT), MemoryActionTokenStore()
    lookup = MemoryTokenMetadataLookup(store)
    service = K3TokenService(store, clock=clock, lookup=lookup)
    claim = dict(
        owner_id="owner",
        subject_id="self",
        open_id="ou_synthetic",
        kind=kind,
        entity_id="synthetic-entity",
        payload_fingerprint="a" * 64,
    )
    issued = service.issue(**claim)
    return clock, store, lookup, service, claim, issued


@pytest.mark.parametrize("case", TRUTH["token_semantics"], ids=lambda case: case["semantic"])
@pytest.mark.parametrize("boundary", TRUTH["token_boundaries"])
def test_k3_exact_ttl_and_half_open_expiry_are_frozen(case, boundary):
    clock, _, _, service, claim, issued = setup(case["semantic"])
    assert issued.expires_at - AT == timedelta(seconds=case["ttl_seconds"])
    offset = timedelta(microseconds=boundary["offset_from_expiry_microseconds"])
    clock.advance(issued.expires_at + offset - clock.now())
    click = service.consume(issued.token, **claim)
    assert click.should_execute == boundary["may_execute"]
    assert click.refresh_needed == boundary["refresh_needed"]
    if click.refresh_needed:
        assert click.message == TRUTH["token_expired_message"] and click.consumption is None
    else:
        replay = service.consume(issued.token, **claim)
        assert not replay.should_execute and replay.consumption.replayed
        assert replay.operation_id == click.operation_id == issued.operation_id


@pytest.mark.parametrize("field", TRUTH["forbidden_token_mismatches"])
def test_expired_wrong_actor_or_payload_cannot_reveal_that_a_card_existed(field):
    clock, _, _, service, claim, issued = setup("question")
    clock.advance(timedelta(days=2))
    replacement = (
        "ou_other"
        if field == "open_id"
        else "delete_memory"
        if field == "kind"
        else "b" * 64
        if field == "payload_fingerprint"
        else "other"
    )
    wrong = dict(claim, **{field: replacement})
    with pytest.raises(ActionTokenError) as expired:
        service.consume(issued.token, **wrong)
    with pytest.raises(ActionTokenError) as unknown:
        service.consume("A" * 43, **claim)
    assert str(expired.value) == str(unknown.value)
    assert "过期" not in str(expired.value)


def test_revocation_and_metadata_lookup_failure_do_not_turn_into_expiry_refresh():
    clock, store, lookup, service, claim, issued = setup("brief")
    lookup.revoke(store.snapshot()[0].digest)
    clock.advance(timedelta(days=2))
    with pytest.raises(ActionTokenError):
        service.consume(issued.token, **claim)

    class FailingLookup:
        def lookup(self, digest):
            raise RuntimeError("SYNTHETIC_PRIVATE_ERROR_MARKER")

    failed = K3TokenService(store, clock=clock, lookup=FailingLookup())
    with pytest.raises(ActionTokenError) as caught:
        failed.consume(issued.token, **claim)
    assert "SYNTHETIC_PRIVATE_ERROR_MARKER" not in str(caught.value)


@pytest.mark.parametrize("dangerous", ["delete_memory", "delete_source", "apply_organize", "apply_organization"])
def test_visual_card_or_second_kind_cannot_extend_a_dangerous_action_to_24_hours(dangerous):
    assert ttl_for_kind(dangerous) == timedelta(minutes=15)
    with pytest.raises(ActionTokenError):
        ttl_for_kind("question", asserted_action=dangerous)
    _, _, _, service, claim, _ = setup("question")
    with pytest.raises(ActionTokenError):
        service.issue(**claim, asserted_action=dangerous)
    with pytest.raises(TypeError):
        service.issue(**claim, ttl=timedelta(days=1))


def test_legacy_short_question_token_cannot_be_reinterpreted_as_a_new_k3_capability():
    clock, store = FrozenClock(AT), MemoryActionTokenStore()
    claim = dict(
        owner_id="owner",
        subject_id="self",
        open_id="ou_synthetic",
        kind="question",
        entity_id="synthetic-entity",
        payload_fingerprint="a" * 64,
    )
    old = ActionTokenService(store, clock=clock).issue(**claim)
    service = K3TokenService(store, clock=clock, lookup=MemoryTokenMetadataLookup(store))
    with pytest.raises(ActionTokenError):
        service.consume(old.token, **claim)


@pytest.mark.parametrize("seed", range(40))
def test_1000_clocked_random_capability_cases_keep_ttl_scope_and_at_most_once_effect(seed):
    rng = Random(729100 + seed)
    for _ in range(25):
        case = rng.choice(TRUTH["token_semantics"])
        clock, store, lookup, service, claim, issued = setup(case["semantic"])
        seconds = rng.randrange(0, case["ttl_seconds"] + 60)
        clock.advance(timedelta(seconds=seconds))
        if rng.randrange(6) == 0:
            lookup.revoke(store.snapshot()[0].digest)
            with pytest.raises(ActionTokenError):
                service.consume(issued.token, **claim)
            continue
        click = service.consume(issued.token, **claim)
        assert click.should_execute == (seconds < case["ttl_seconds"])
        assert click.refresh_needed == (seconds >= case["ttl_seconds"])
        if click.should_execute:
            assert not service.consume(issued.token, **claim).should_execute
        assert issued.expires_at == AT + timedelta(seconds=case["ttl_seconds"])
        assert issued.token not in repr(store.snapshot())
