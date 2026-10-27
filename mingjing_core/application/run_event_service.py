"""Trusted app leases share exactly one process listener and bounded hint hub."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict

from mingjing_core.domain.contracts import EvidenceError

from .run_event_hub import RunEventHub, Subscription
from .run_event_listener import EventListener


@dataclass
class _Broker:
    fingerprint: str
    hub: RunEventHub
    listener: EventListener
    clients: set[object] = field(default_factory=set)
    closing: bool = False


_guard = threading.RLock()
_broker: _Broker | None = None


def _database_key(dsn: str) -> str:
    try:
        fields = conninfo_to_dict(dsn)
        if not fields:
            raise ValueError("empty connection")
        return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
    except (psycopg.Error, ValueError, TypeError):
        raise EvidenceError("事件监听数据库配置无效") from None


class EventHints:
    def __init__(
        self, repo: Any, broker: _Broker, scope: object, loop: asyncio.AbstractEventLoop
    ) -> None:
        self.repo, self._broker, self.scope, self.loop = repo, broker, scope, loop
        self.closed = False

    def subscribe(self, repo: Any, owner: str, ident: str) -> Subscription:
        if (
            self.closed
            or repo is not self.repo
            or asyncio.get_running_loop() is not self.loop
        ):
            raise EvidenceError("事件提示服务与当前请求范围不符")
        return self._broker.hub.subscribe(self.scope, owner, ident)

    def statistics(self) -> dict[str, Any]:
        return dict(
            self._broker.hub.statistics(),
            listener_ready=self._broker.listener.ready.is_set(),
            notifications=self._broker.listener.notifications,
            failures=self._broker.listener.failures,
            code=self._broker.listener.last_code,
        )

    def close(self) -> None:
        global _broker
        with _guard:
            if self.closed:
                return
            self.closed = True
            broker = self._broker
            broker.hub.close_scope(self.scope)
            broker.clients.discard(self.scope)
            final = not broker.clients
            if final:
                broker.closing = True
        if final:
            # Leave the closing broker installed until its old socket/thread are gone.
            broker.listener.close()
            with _guard:
                if _broker is broker:
                    _broker = None


def acquire_event_hints(repo: Any) -> EventHints:
    global _broker
    loop, key = asyncio.get_running_loop(), _database_key(repo.dsn)
    with _guard:
        broker = _broker
        if broker is not None and (broker.closing or broker.fingerprint != key):
            raise EvidenceError("同一进程的事件监听配置冲突，请使用独立进程")
        fresh = broker is None
        if broker is None:
            hub = RunEventHub()
            broker = _Broker(key, hub, EventListener(repo.dsn, hub))
        scope = broker.hub.open_scope(loop)
        broker.clients.add(scope)
        _broker = broker
        try:
            if fresh:
                broker.listener.start()
        except Exception:
            broker.clients.discard(scope)
            broker.hub.close_scope(scope)
            _broker = None
            raise EvidenceError("事件监听服务未能启动") from None
        return EventHints(repo, broker, scope, loop)
