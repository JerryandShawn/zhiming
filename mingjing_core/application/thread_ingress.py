"""Authenticated message intake is independent from model execution and delivery."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mingjing_core.application.privacy_mode import PrivacyModeService
from mingjing_core.application.privacy_run_barrier import inherit_source_barrier
from mingjing_core.application.thread_queue import queue_thread
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.timekit.clock import Clock


class ThreadIngress:
    def __init__(self, service: Any, *, clock: Clock | None = None) -> None:
        self.service, self.repo = service, service.repo
        self.threads = ThreadService(self.repo, clock=clock)
        self.privacy = PrivacyModeService(self.repo, clock=clock)

    def receive(
        self,
        *,
        owner: str,
        thread_id: str,
        message: str,
        request_id: str,
        subject: str = "self",
        conversation_id: str = "shared",
        channel: str = "web",
        external_id: str | None = None,
        source_id: str | None = None,
        at: datetime | None = None,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 16000:
            raise EvidenceError("消息需要一至16000字")
        return self.privacy.receive(
            owner=owner,
            thread_id=thread_id,
            message=message,
            request_id=request_id,
            subject=subject,
            channel=channel,
            external_id=external_id,
            conversation_id=conversation_id,
            source_id=source_id,
            at=at,
            case_ids=case_ids,
        )

    def submit(
        self,
        *,
        owner: str,
        thread_id: str,
        message: str,
        request_id: str,
        subject: str = "self",
        conversation_id: str = "shared",
        channel: str = "web",
        external_id: str | None = None,
        source_id: str | None = None,
        at: datetime | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        with self.repo.transaction(owner):
            source = self.receive(
                owner=owner,
                thread_id=thread_id,
                message=message,
                request_id=request_id,
                subject=subject,
                conversation_id=conversation_id,
                channel=channel,
                external_id=external_id,
                source_id=source_id,
                at=at,
                case_ids=options.get("case_ids"),
            )
            return self.queue(
                owner=owner,
                thread_id=source["thread_id"],
                source_ids=[source["id"]],
                request_id=request_id,
                subject=subject,
                conversation_id=conversation_id,
                **options,
            )

    def queue(
        self,
        *,
        owner: str,
        thread_id: str,
        source_ids: list[str],
        request_id: str,
        subject: str = "self",
        conversation_id: str = "shared",
        **options: Any,
    ) -> dict[str, Any]:
        if thread_id.startswith("incognito:") and options.get("case_ids"):
            raise EvidenceError("无痕线程不能绑定长期事项")
        with self.repo.transaction(owner):
            run = queue_thread(
                self.service,
                owner=owner,
                subject=subject,
                thread=thread_id,
                sources=source_ids,
                request_id=request_id,
                conversation_id=conversation_id,
                options=options,
            )
            return inherit_source_barrier(self.repo, run, source_ids)

    def history(self, owner: str, thread_id: str, *, subject: str = "self", limit: int = 80) -> list[dict[str, Any]]:
        return self.threads.history(owner, thread_id, subject=subject, limit=limit)
