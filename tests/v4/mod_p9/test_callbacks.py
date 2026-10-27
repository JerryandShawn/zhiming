from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
import hashlib

import pytest

from mingjing_core.adapters.channels.action_token_contracts import ActionTokenClaim
from mingjing_core.adapters.channels.action_tokens import ActionTokenService
from mingjing_core.adapters.channels.callback_auth import (
    CallbackAuthenticator,
    CallbackError,
)
from mingjing_core.adapters.channels.callback_commands import (
    CallbackBinding,
    MemoryCallbackCommands,
)
from mingjing_core.adapters.channels.cards_contracts import CardAction
from mingjing_core.adapters.channels.cards_official_v3 import question_card
from mingjing_core.timekit.clock import FrozenClock

from .fake_feishu import FakeFeishu

NOW = datetime.fromisoformat("2026-10-27T16:45:00+08:00")


def setup(kind="ask_user"):
    clock = FrozenClock(NOW)
    queue = MemoryCallbackCommands(clock=clock)
    claim = ActionTokenClaim(
        "synthetic-owner",
        "synthetic-subject",
        "ou_synthetic",
        kind,
        "synthetic-entity",
        "a" * 64,
    )
    issuer = ActionTokenService(queue, clock=clock)
    token = issuer.issue(**claim.__dict__).token
    card = question_card(
        "合成选择？", why="合成确认", options=[CardAction("合成选项", token)]
    )
    fake = FakeFeishu()
    message = fake.send(card, claim.open_id)
    binding = CallbackBinding(claim, "synthetic_app", "synthetic_chat", message)
    auth = CallbackAuthenticator(
        "synthetic_app", "synthetic_verification", "synthetic_encrypt"
    )
    document = fake.callback(message_id=message, action_token=token)
    return clock, queue, claim, issuer, fake, binding, auth, document


def verify(auth, fake, clock, document):
    return auth.webhook(**fake.webhook(document, now=clock.now()), clock=clock)


@pytest.mark.parametrize(
    "kind", ["ask_user", "decision", "memory_undo", "tarot_select", "synastry_confirm"]
)
def test_signed_callback_queues_once_and_acknowledges_before_worker(kind):
    clock, queue, _, _, fake, binding, auth, document = setup(kind)
    event = verify(auth, fake, clock, document)
    receipt = queue.accept(event, binding, authorize=lambda _: True)
    assert receipt.response() == {"toast": {"type": "info", "content": "操作已收到"}}
    assert fake.effects == []
    assert queue.accept(event, binding, authorize=lambda _: True).duplicate
    assert (
        queue.execute_once(
            receipt.operation_id, authorize=lambda _: True, execute=fake.execute
        )
        == "succeeded"
    )
    assert (
        queue.execute_once(
            receipt.operation_id, authorize=lambda _: True, execute=fake.execute
        )
        == "succeeded"
    )
    assert len(fake.effects) == 1
    assert document["event"]["action"]["value"]["t"] not in repr(event)


@pytest.mark.parametrize(
    "field,value",
    [
        ("timestamp", "0"),
        ("timestamp", "not-a-time"),
        ("nonce", ""),
        ("signature", "0" * 64),
        ("raw", b"tampered"),
    ],
)
def test_raw_signature_or_replay_window_rejects_before_parsing(field, value):
    clock, _, _, _, fake, _, auth, document = setup()
    request = fake.webhook(document, now=clock.now())
    request[field] = value
    with pytest.raises(CallbackError, match="^card_callback_invalid$"):
        auth.webhook(**request, clock=clock)


def test_signature_binds_original_bytes_and_encrypted_envelope_is_mandatory():
    clock, _, _, _, fake, _, auth, document = setup()
    request = fake.webhook(document, now=clock.now())
    request["raw"] += b" "
    with pytest.raises(CallbackError):
        auth.webhook(**request, clock=clock)
    request["raw"] = fake.plaintext(document)
    request["signature"] = hashlib.sha256(
        (request["timestamp"] + request["nonce"] + "synthetic_encrypt").encode()
        + request["raw"]
    ).hexdigest()
    with pytest.raises(CallbackError):
        auth.webhook(**request, clock=clock)


@pytest.mark.parametrize(
    "field,value",
    [
        ("app_id", "other"),
        ("token", "other"),
        ("event_type", "other"),
        ("event_id", ""),
    ],
)
def test_even_signed_wrong_application_or_event_is_rejected(field, value):
    clock, _, _, _, fake, _, auth, document = setup()
    document["header"][field] = value
    with pytest.raises(CallbackError):
        verify(auth, fake, clock, document)


@pytest.mark.parametrize("field", ["open_id", "chat_id", "message_id"])
def test_current_host_bindings_are_checked_before_token_consumption(field):
    clock, queue, _, _, fake, binding, auth, document = setup()
    event = verify(auth, fake, clock, document)
    with pytest.raises(CallbackError):
        queue.accept(
            replace(event, **{field: "foreign"}), binding, authorize=lambda _: True
        )
    assert not queue.accept(event, binding, authorize=lambda _: True).duplicate


def test_authenticated_connection_is_separate_and_needs_host_app_and_payload_verification():
    clock, _, _, _, fake, _, auth, document = setup()
    result = auth.authenticated_connection(
        fake.plaintext(document), authenticated_app_id="synthetic_app"
    )
    assert result == verify(auth, fake, clock, document)
    with pytest.raises(CallbackError):
        auth.authenticated_connection(
            fake.plaintext(document), authenticated_app_id="foreign"
        )
    with pytest.raises(CallbackError):
        auth.authenticated_connection(
            b'{"schema": "2.0", "schema": "1.0"}', authenticated_app_id="synthetic_app"
        )


def test_event_id_conflict_and_distinct_tokens_for_same_logical_action_do_not_double_execute():
    clock, queue, claim, issuer, fake, binding, auth, document = setup()
    first = queue.accept(
        verify(auth, fake, clock, document), binding, authorize=lambda _: True
    )
    token = issuer.issue(**claim.__dict__).token
    document["event"]["action"]["value"]["t"] = token
    with pytest.raises(CallbackError):
        queue.accept(
            verify(auth, fake, clock, document), binding, authorize=lambda _: True
        )
    document["header"]["event_id"] = "new_event"
    duplicate = queue.accept(
        verify(auth, fake, clock, document), binding, authorize=lambda _: True
    )
    assert duplicate.duplicate and duplicate.operation_id == first.operation_id


def test_expiry_revocation_and_worker_authority_recheck_fail_closed():
    clock, queue, _, _, fake, binding, auth, document = setup()
    event = verify(auth, fake, clock, document)
    with pytest.raises(CallbackError):
        queue.accept(event, binding, authorize=lambda _: False)
    receipt = queue.accept(event, binding, authorize=lambda _: True)
    assert (
        queue.execute_once(
            receipt.operation_id, authorize=lambda _: False, execute=fake.execute
        )
        == "rejected"
    )
    assert fake.effects == []
    clock.advance(timedelta(minutes=16))
    document["header"]["event_id"] = "expired_event"
    with pytest.raises(CallbackError):
        queue.accept(
            verify(auth, fake, clock, document), binding, authorize=lambda _: True
        )


def test_unknown_after_side_effect_is_never_automatically_replayed():
    clock, queue, _, _, fake, binding, auth, document = setup()
    receipt = queue.accept(
        verify(auth, fake, clock, document), binding, authorize=lambda _: True
    )

    def execute(command):
        fake.execute(command, uncertain=True)

    assert (
        queue.execute_once(
            receipt.operation_id, authorize=lambda _: True, execute=execute
        )
        == "unknown"
    )
    assert (
        queue.execute_once(
            receipt.operation_id, authorize=lambda _: True, execute=execute
        )
        == "unknown"
    )
    assert len(fake.effects) == 1


def test_two_concurrent_callback_workers_commit_one_command_and_one_effect():
    clock, queue, _, _, fake, binding, auth, document = setup()
    event = verify(auth, fake, clock, document)
    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = list(
            executor.map(
                lambda _: queue.accept(event, binding, authorize=lambda _: True),
                range(2),
            )
        )
    assert sum(not row.duplicate for row in receipts) == 1
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(
            executor.map(
                lambda _: queue.execute_once(
                    receipts[0].operation_id,
                    authorize=lambda _: True,
                    execute=fake.execute,
                ),
                range(2),
            )
        )
    assert len(fake.effects) == 1


@pytest.mark.parametrize("encrypted", ["invalid base64!", "AA==", "A" * 44])
def test_bad_ciphertexts_fail_safely_even_with_valid_request_signature(encrypted):
    clock, _, _, _, fake, _, auth, document = setup()
    request = fake.webhook(document, now=clock.now())
    request["raw"] = fake.plaintext({"encrypt": encrypted})
    request["signature"] = hashlib.sha256(
        (request["timestamp"] + request["nonce"] + "synthetic_encrypt").encode()
        + request["raw"]
    ).hexdigest()
    with pytest.raises(CallbackError, match="^card_callback_invalid$"):
        auth.webhook(**request, clock=clock)


def test_token_consumed_outside_command_transaction_cannot_be_used_to_invent_command():
    clock, queue, claim, issuer, fake, binding, auth, document = setup()
    issuer.consume(document["event"]["action"]["value"]["t"], **claim.__dict__)
    with pytest.raises(CallbackError):
        queue.accept(
            verify(auth, fake, clock, document), binding, authorize=lambda _: True
        )
    assert fake.effects == []
