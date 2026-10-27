"""Authenticate raw Feishu callbacks locally. No HTTP listener or SDK connection is created."""

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from mingjing_core.timekit.clock import Clock

from .action_token_contracts import utc, validate_identity


class CallbackError(ValueError):
    def __init__(self) -> None:
        super().__init__("card_callback_invalid")


def _pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CallbackError()
        result[key] = value
    return result


def _json(raw: bytes) -> dict:
    try:
        result = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(CallbackError()),
        )
        if not isinstance(result, dict):
            raise CallbackError()
        return result
    except (ValueError, UnicodeError, RecursionError, TypeError):
        raise CallbackError() from None


@dataclass(frozen=True)
class VerifiedCallback:
    event_id: str
    app_id: str
    open_id: str = field(repr=False)
    chat_id: str = field(repr=False)
    message_id: str = field(repr=False)
    action_token: str = field(repr=False)
    fingerprint: str


@dataclass(frozen=True)
class CallbackAuthenticator:
    app_id: str
    verification_token: str = field(repr=False)
    encrypt_key: str = field(repr=False)
    window_seconds: int = 300

    def __post_init__(self) -> None:
        for value in (self.app_id, self.verification_token, self.encrypt_key):
            validate_identity(value)
        if type(self.window_seconds) is not int or not 1 <= self.window_seconds <= 600:
            raise CallbackError()

    def webhook(
        self, raw: bytes, *, timestamp: str, nonce: str, signature: str, clock: Clock
    ) -> VerifiedCallback:
        """26 §3.2: sha256(timestamp + nonce + Encrypt Key + original body), before decoding/decryption."""
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= 65_536:
            raise CallbackError()
        if (
            not isinstance(timestamp, str)
            or re.fullmatch(r"[0-9]{1,12}", timestamp) is None
        ):
            raise CallbackError()
        if (
            not isinstance(nonce, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{1,256}", nonce) is None
        ):
            raise CallbackError()
        if (
            not isinstance(signature, str)
            or re.fullmatch(r"[a-f0-9]{64}", signature) is None
        ):
            raise CallbackError()
        if abs(utc(clock.now()).timestamp() - int(timestamp)) > self.window_seconds:
            raise CallbackError()
        expected = hashlib.sha256(
            (timestamp + nonce + self.encrypt_key).encode() + raw
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise CallbackError()
        envelope = _json(raw)
        if set(envelope) != {"encrypt"} or not isinstance(envelope["encrypt"], str):
            raise CallbackError()
        try:
            encrypted = base64.b64decode(envelope["encrypt"], validate=True)
            if len(encrypted) < 32 or len(encrypted) % 16:
                raise CallbackError()
            key = hashlib.sha256(self.encrypt_key.encode()).digest()
            plaintext = unpad(
                AES.new(key, AES.MODE_CBC, encrypted[:16]).decrypt(encrypted[16:]), 16
            )
        except (ValueError, TypeError):
            raise CallbackError() from None
        return self._event(_json(plaintext))

    def authenticated_connection(
        self, raw: bytes, *, authenticated_app_id: str
    ) -> VerifiedCallback:
        """Only for the host's already-authenticated SDK connection; never expose as an untrusted HTTP mode."""
        if (
            authenticated_app_id != self.app_id
            or not isinstance(raw, bytes)
            or not 1 <= len(raw) <= 65_536
        ):
            raise CallbackError()
        return self._event(_json(raw))

    def _event(self, document: dict) -> VerifiedCallback:
        try:
            header, event = document["header"], document["event"]
            if (
                document["schema"] != "2.0"
                or header["event_type"] != "card.action.trigger"
            ):
                raise CallbackError()
            if header["app_id"] != self.app_id or not hmac.compare_digest(
                header["token"].encode(), self.verification_token.encode()
            ):
                raise CallbackError()
            action, context = event["action"], event["context"]
            if action["tag"] != "button" or set(action["value"]) != {"t"}:
                raise CallbackError()
            values = (
                header["event_id"],
                header["app_id"],
                event["operator"]["open_id"],
                context["open_chat_id"],
                context["open_message_id"],
                action["value"]["t"],
            )
            for value in values:
                validate_identity(value)
            if re.fullmatch(r"[A-Za-z0-9_-]{43}", values[-1]) is None:
                raise CallbackError()
            digest = hashlib.sha256(
                json.dumps(values, separators=(",", ":")).encode()
            ).hexdigest()
            return VerifiedCallback(*values, digest)
        except (KeyError, TypeError, AttributeError, ValueError, UnicodeError):
            raise CallbackError() from None
