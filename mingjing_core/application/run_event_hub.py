"""Bounded integer hints; the database reader retains all authorization and payloads."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field

from mingjing_core.domain.contracts import EvidenceError


@dataclass
class _Scope:
    loop: asyncio.AbstractEventLoop
    subscribers: set[object] = field(default_factory=set)
    pending: bool = False
    handle: asyncio.Handle | None = None


class Subscription:
    def __init__(self, hub: RunEventHub, scope: object, owner: str, ident: str) -> None:
        self.hub, self.scope, self.owner, self.ident = hub, scope, owner, ident
        self.token = object()
        self.queue: asyncio.Queue[int] = asyncio.Queue(maxsize=1)
        self.pending_high = 0
        self.closed = False

    async def wait(self, timeout: float) -> int | None:
        if self.closed:
            return None
        try:
            value = await asyncio.wait_for(self.queue.get(), timeout)
        except TimeoutError:
            return None
        return None if self.closed else value

    def close(self) -> None:
        self.hub.unsubscribe(self)


class RunEventHub:
    def __init__(
        self,
        *,
        capacity: int = 256,
        per_run: int = 32,
        per_scope: int = 128,
        max_scopes: int = 16,
    ) -> None:
        for value, maximum in (
            (capacity, 256),
            (per_run, 32),
            (per_scope, 128),
            (max_scopes, 16),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("事件提示容量无效")
        self.capacity, self.per_run, self.per_scope, self.max_scopes = (
            capacity,
            per_run,
            per_scope,
            max_scopes,
        )
        self._guard = threading.RLock()
        self._scopes: dict[object, _Scope] = {}
        self._subscriptions: dict[object, Subscription] = {}
        self._by_run: dict[str, set[object]] = {}

    def open_scope(self, loop: asyncio.AbstractEventLoop) -> object:
        with self._guard:
            if len(self._scopes) >= self.max_scopes or loop.is_closed():
                raise EvidenceError("事件订阅服务容量已满或已关闭")
            token = object()
            self._scopes[token] = _Scope(loop)
            return token

    def subscribe(self, scope: object, owner: str, ident: str) -> Subscription:
        if any(
            not isinstance(value, str) or not value.strip() or len(value) > 200
            for value in (owner, ident)
        ):
            raise EvidenceError("事件订阅身份无效")
        with self._guard:
            if scope not in self._scopes:
                raise EvidenceError("事件订阅服务已关闭")
            if (
                len(self._subscriptions) >= self.capacity
                or len(self._by_run.get(ident, ())) >= self.per_run
                or len(self._scopes[scope].subscribers) >= self.per_scope
            ):
                raise EvidenceError("事件订阅容量已满，请稍后重新连接")
            value = Subscription(self, scope, owner, ident)
            self._subscriptions[value.token] = value
            self._scopes[scope].subscribers.add(value.token)
            self._by_run.setdefault(ident, set()).add(value.token)
            return value

    def publish(self, ident: str, seq: int) -> None:
        if not isinstance(ident, str) or type(seq) is not int or not 0 < seq < 2**63:
            return
        with self._guard:
            scopes = set()
            for token in self._by_run.get(ident, ()):
                value = self._subscriptions[token]
                value.pending_high = max(value.pending_high, seq)
                scopes.add(value.scope)
            for token in scopes:
                scope = self._scopes[token]
                if scope.pending:
                    continue
                scope.pending = True
                try:
                    # One app pump, rather than one callback per event or departed subscriber.
                    scope.handle = scope.loop.call_soon_threadsafe(self._drain, token)
                except RuntimeError:
                    self.close_scope(token)

    def _drain(self, token: object) -> None:
        with self._guard:
            scope = self._scopes.get(token)
            if scope is None:
                return
            scope.pending, scope.handle = False, None
            for key in scope.subscribers:
                value = self._subscriptions[key]
                high, value.pending_high = value.pending_high, 0
                if not high:
                    continue
                if not value.queue.empty():
                    high = max(high, value.queue.get_nowait())
                value.queue.put_nowait(high)

    def unsubscribe(self, value: Subscription) -> None:
        with self._guard:
            if value.closed:
                return
            value.closed, value.pending_high = True, 0
            self._subscriptions.pop(value.token, None)
            keys = self._by_run.get(value.ident)
            if keys is not None:
                keys.discard(value.token)
                if not keys:
                    del self._by_run[value.ident]
            scope = self._scopes.get(value.scope)
            if scope is not None:
                scope.subscribers.discard(value.token)

    def close_scope(self, token: object) -> None:
        with self._guard:
            scope = self._scopes.get(token)
            if scope is None:
                return
            for key in tuple(scope.subscribers):
                self.unsubscribe(self._subscriptions[key])
            if scope.handle is not None:
                scope.handle.cancel()
            del self._scopes[token]

    def statistics(self) -> dict[str, int]:
        with self._guard:
            return {
                "scopes": len(self._scopes),
                "subscriptions": len(self._subscriptions),
                "runs": len(self._by_run),
                "pending_callbacks": sum(
                    scope.pending for scope in self._scopes.values()
                ),
                "queued_hints": sum(
                    value.queue.qsize() for value in self._subscriptions.values()
                ),
            }
