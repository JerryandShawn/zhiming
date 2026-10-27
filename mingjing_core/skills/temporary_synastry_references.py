"""Opt-in run-private citations; no Agent registration or durable storage."""

from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timedelta
from secrets import token_urlsafe
from threading import RLock

from ..adapters.charts.tool_evidence import content_hash, evidence_result, pointer
from ..timekit.clock import Clock
from .temporary_synastry_scope import ConsumedGrant, SynastryBinding, utc

NOTICE = "本次合盘是临时计算，没有存档。"


def seal_generated_text(text: str, *, generated_for_temporary_synastry: bool) -> str:
    """Only for system-generated transient output, never for user source text."""
    if generated_for_temporary_synastry is not True or not isinstance(text, str):
        raise ValueError("TEMPORARY_GENERATED_TEXT_REQUIRED")
    # A tag-free explanation can still reveal another person's chart or birth.
    return NOTICE


class TemporarySynastryReferences:
    """One run, one consumed operation, one in-memory result; disabled by default."""

    def __init__(
        self,
        binding: SynastryBinding,
        *,
        clock: Clock,
        run_deadline: datetime,
        revalidate: Callable[[SynastryBinding], ConsumedGrant],
        enabled: bool = False,
    ) -> None:
        if not isinstance(binding, SynastryBinding) or not callable(revalidate):
            raise ValueError("TEMPORARY_SCOPE_INVALID")
        self._binding = binding
        self._clock = clock
        self._deadline = utc(run_deadline)
        self._revalidate = revalidate
        self._enabled = enabled is True
        self._closed = False
        self._root: dict | None = None
        self._document_id: str | None = None
        self._lock = RLock()

    def __repr__(self) -> str:
        return "<TemporarySynastryReferences private>"

    def __getstate__(self) -> dict:
        raise TypeError("TEMPORARY_RESULT_NOT_PERSISTABLE")

    def _live(self, binding: SynastryBinding) -> None:
        if binding != self._binding or self._closed:
            raise ValueError("CITATION_UNAVAILABLE")
        if not self._enabled:
            raise ValueError("TEMPORARY_PROTOCOL_DISABLED")
        try:
            grant = self._revalidate(binding)
            now = utc(self._clock.now())
            if self._closed:
                raise ValueError
            if not isinstance(grant, ConsumedGrant) or grant.binding != binding:
                raise ValueError
            if (
                grant.revoked is not False
                or grant.consumed_operation_id != binding.compute_operation_id
            ):
                raise ValueError
            start, end = utc(grant.confirmed_at), utc(grant.expires_at)
            if end <= start or end - start > timedelta(hours=24) or now < start:
                raise ValueError
            expired = now >= min(end, self._deadline)
        except Exception:
            self.close()
            raise ValueError("CITATION_UNAVAILABLE") from None
        if expired:
            self.close()
            raise ValueError("CITATION_EXPIRED")

    def _verified(self, result: dict) -> dict:
        try:
            if result["version"] != "p8-synastry-v1":
                raise ValueError
            if content_hash(result["scope"]) != content_hash(
                self._binding.native_scope()
            ):
                raise ValueError
            if result["data"]["kind"] != self._binding.kind:
                raise ValueError
            if result["data"]["consent"] != "user_confirmed":
                raise ValueError
            root = evidence_result(
                result["version"],
                result["data"],
                result["rule_hits"],
                result["sources"],
                result["scope"],
            )
            if any(root[key] != result[key] for key in ("document_id", "aliases")):
                raise ValueError
            return root
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            raise ValueError("TEMPORARY_RESULT_INVALID") from None

    def _projection(self) -> dict:
        aliases = deepcopy(self._root["aliases"])
        for rows in aliases.values():
            for row in rows:
                row["document_id"] = self._document_id
                row["claim_id"] = "claim-" + content_hash(
                    [self._document_id, row["path"], row["value_sha256"]]
                )
        return {
            "document_id": self._document_id,
            "aliases": aliases,
            "notice": NOTICE,
            "retention": "current_run_only",
        }

    def register(self, result: dict, *, binding: SynastryBinding) -> dict:
        with self._lock:
            self._live(binding)
            root = self._verified(result)
            if (
                self._root is not None
                and self._root["document_id"] != root["document_id"]
            ):
                raise ValueError("TEMPORARY_OPERATION_CONFLICT")
            self._live(binding)
            if self._root is None:
                self._root = root
                self._document_id = "run-doc-" + token_urlsafe(24)
            return self._projection()

    def resolve(
        self, alias: str, *, binding: SynastryBinding, document_id: str
    ) -> object:
        with self._lock:
            self._live(binding)
            if (
                self._root is None
                or document_id != self._document_id
                or not isinstance(alias, str)
                or not re.fullmatch(r"[cr][1-9][0-9]*", alias)
            ):
                raise ValueError("CITATION_UNAVAILABLE")
            row = next(
                (
                    row
                    for row in self._root["aliases"][alias[0]]
                    if row["alias"] == alias
                ),
                None,
            )
            if row is None:
                raise ValueError("CITATION_UNAVAILABLE")
            value = deepcopy(pointer(self._root, row["path"]))
            self._live(binding)
            return value

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._root = None
            self._document_id = None

    def __enter__(self) -> TemporarySynastryReferences:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
