"""Choose privacy before original-message persistence; event routes never migrate."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mingjing_core.application.privacy_mode_policy import blocks_current_run, privacy_action
from mingjing_core.application.privacy_run_barrier import block_thread_runs
from mingjing_core.application.thread_case_sources import bind_case_selection, normalize_case_ids
from mingjing_core.application.thread_queue import owner_runtime
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.clock import Clock, get_clock


class PrivacyModeService:
    def __init__(self, repo: Any, *, clock: Clock | None = None) -> None:
        self.repo, self.clock = repo, clock or get_clock()
        self.threads = ThreadService(repo, clock=self.clock)

    def assert_legacy_safe(
        self, owner: str, subject: str, message: str, *, channel: str = "web", conversation_id: str = "shared"
    ) -> None:
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            ident = "privacy-mode:" + fingerprint([owner, subject, channel, conversation_id])[:32]
            state = self._get(owner, "session", ident)
            if privacy_action(message) is not None or self._state_thread(owner, subject, state) is not None:
                raise EvidenceError("无痕需要已配置的 v4 运行时，本条原话尚未保存")

    def receive(
        self,
        *,
        owner: str,
        thread_id: str,
        message: str,
        request_id: str,
        subject: str = "self",
        channel: str = "web",
        external_id: str | None = None,
        conversation_id: str = "shared",
        source_id: str | None = None,
        at: datetime | None = None,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        self._validate(message, request_id, at)
        cases = normalize_case_ids(case_ids)
        identity = self._identity(subject, channel, external_id, conversation_id, thread_id, message, at, cases)
        ident = "privacy-route:" + fingerprint([owner, channel, source_id or request_id])[:32]
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            old = self._get(owner, "request", ident)
            if old is not None:
                if old["subject_id"] != subject or old.get("origin_thread_id") != thread_id:
                    raise ScopeError("原始事件不能移动到其他人物或线程")
                if old.get("input_fp") != fingerprint(identity) or old["subject_id"] != subject:
                    raise EvidenceError("原始事件不能替换无痕路由、人物或正文")
                thread = old["thread_id"]
                return self._receive(
                    owner,
                    subject,
                    thread,
                    message,
                    request_id,
                    channel,
                    external_id,
                    conversation_id,
                    source_id,
                    at,
                    cases,
                )
            thread = self._choose(owner, subject, thread_id, message, request_id, channel, conversation_id)
            receipt = self._receipt(owner, subject, ident, thread_id, thread, message, identity)
            source = self._receive(
                owner, subject, thread, message, request_id, channel, external_id, conversation_id, source_id, at, cases
            )
            self.repo.update(
                owner, "request", ident, {"source_id": source["id"]}, expected_revision=receipt["revision"]
            )
            if receipt["blocks_current_run"]:
                block_thread_runs(self.repo, owner, subject, thread_id, ident)
            return source

    @staticmethod
    def _identity(subject, channel, external, conversation, thread, message, at, cases) -> list[Any]:
        return bind_case_selection(
            [
                subject,
                channel,
                external,
                conversation,
                thread,
                fingerprint(message),
                at.astimezone(UTC).isoformat() if at else None,
            ],
            cases,
        )

    @staticmethod
    def _validate(message: str, request_id: str, at: datetime | None) -> None:
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 16000:
            raise EvidenceError("消息需要一至16000字")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 200:
            raise EvidenceError("隐私路由需要稳定请求标识")
        if at is not None and (not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None):
            raise EvidenceError("原话时间必须是带时区的时刻")

    def _receive(
        self,
        owner: str,
        subject: str,
        thread: str,
        message: str,
        request: str,
        channel: str,
        external: str | None,
        conversation: str,
        source: str | None,
        at: datetime | None,
        case_ids: list[str],
    ) -> dict[str, Any]:
        return self.threads.receive(
            owner,
            thread,
            message,
            request_id=request,
            subject=subject,
            channel=channel,
            external_id=external,
            conversation_id=conversation,
            source_id=source,
            at=at,
            case_ids=case_ids,
        )

    def _choose(
        self, owner: str, subject: str, original: str, text: str, request: str, channel: str, conversation: str
    ) -> str:
        action = privacy_action(text)
        state_id = "privacy-mode:" + fingerprint([owner, subject, channel, conversation])[:32]
        state = self._get(owner, "session", state_id)
        current = self._active(owner, subject, original, state)
        runtime = owner_runtime(self.repo.assert_scope(owner, subject)["settings"])
        if runtime != "v4" and (action is not None or current is not None):
            raise EvidenceError("无痕需要已配置的 v4 运行时，本条原话尚未保存")
        if action == "exit":
            self._state(owner, subject, state_id, state, None)
            return self.threads.create(owner, subject=subject, request_id="privacy-life:" + subject)["id"]
        if action == "enter" and current is None:
            current = self.threads.create(
                owner,
                subject=subject,
                incognito=True,
                request_id="privacy:" + fingerprint([channel, conversation, request]),
            )["id"]
        if current is not None:
            if state is None or state.get("thread_id") != current:
                self._state(owner, subject, state_id, state, current)
            return current
        self.threads.get(owner, original, subject=subject)
        return original

    def _active(self, owner: str, subject: str, original: str, state: dict | None) -> str | None:
        if original.startswith("incognito:"):
            self.threads.get(owner, original, subject=subject)
            return original
        self.threads.get(owner, original, subject=subject)
        return self._state_thread(owner, subject, state)

    def _state_thread(self, owner: str, subject: str, state: dict[str, Any] | None) -> str | None:
        target = state.get("thread_id") if state else None
        if target is None:
            return None
        if not isinstance(target, str) or not target.startswith("incognito:") or state["subject_id"] != subject:
            raise EvidenceError("自动无痕模式元数据无效")
        try:
            self.threads.get(owner, target, subject=subject)
        except (ScopeError, EvidenceError):
            return None
        return target

    def _state(self, owner: str, subject: str, ident: str, old: dict[str, Any] | None, thread: str | None) -> None:
        self.repo.put(
            owner,
            "session",
            ident,
            {"ingress": "privacy_mode", "thread_id": thread},
            subject=subject,
            expected_revision=old["revision"] if old else 0,
        )

    def _receipt(
        self, owner: str, subject: str, ident: str, origin: str, thread: str, text: str, identity: list[Any]
    ) -> dict[str, Any]:
        return self.repo.put(
            owner,
            "request",
            ident,
            {
                "ingress": "privacy_route",
                "input_fp": fingerprint(identity),
                "thread_id": thread,
                "origin_thread_id": origin,
                "blocks_current_run": blocks_current_run(text),
                "source_id": None,
            },
            subject=subject,
            expected_revision=0,
            operation_id=ident,
        )

    def _get(self, owner: str, kind: str, ident: str) -> dict[str, Any] | None:
        try:
            return self.repo.get(owner, kind, ident)
        except ScopeError:
            return None
