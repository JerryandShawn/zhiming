"""Explicit revealed-draw intake shared by authenticated product entry points."""

from __future__ import annotations

from typing import Any

from mingjing_core.adapters.tarot import TarotService
from mingjing_core.application.thread_case_sources import normalize_case_ids, selected_cases
from mingjing_core.application.thread_ingress import ThreadIngress
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, ScopeError


def selected_draw(repo: Any, owner: str, subject: str, ident: str, thread: str, cases: list[str] | None) -> dict:
    if not isinstance(ident, str) or not 1 <= len(ident) <= 200:
        raise EvidenceError("需要明确选中的牌阵")
    if thread != "life:" + subject:
        raise ScopeError("固定牌阵只能在对应人物的人生线程解读")
    repo.assert_scope(owner, subject)
    try:
        draw = TarotService(repo).get(owner, ident)
    except KeyError:
        raise ScopeError("牌阵不存在或不属于当前身份") from None
    if draw["subject_id"] != subject or draw.get("context_revoked"):
        raise ScopeError("牌阵人物或来源已经失效")
    if draw["status"] != "ready":
        raise EvidenceError("请先在面板选牌并揭示固定牌阵")
    if cases and set(normalize_case_ids(cases)) != {draw["case_id"]}:
        raise ScopeError("牌阵与选中的事项不符")
    selected_cases(repo, owner, subject, [draw["case_id"]])
    return draw


class TarotRevealIngress:
    def __init__(self, service: Any) -> None:
        self.service, self.repo = service, service.repo

    def submit(
        self,
        *,
        owner: str,
        draw_id: str,
        request_id: str,
        subject: str = "self",
        thread_id: str | None = None,
        message: str | None = None,
        conversation_id: str = "shared",
        case_ids: list[str] | None = None,
        depth: str = "standard",
        source_ids: list[str] | None = None,
        reading_id: str | None = None,
    ) -> dict:
        if depth not in {"standard", "deep"}:
            raise EvidenceError("v4 目前支持标准或深入模式")
        thread = thread_id or "life:" + subject
        with self.repo.transaction(owner):
            draw = selected_draw(self.repo, owner, subject, draw_id, thread, case_ids)
            ThreadService(self.repo).create(owner, subject=subject, request_id="tarot-life:" + subject)
            options = dict(
                owner=owner,
                subject=subject,
                thread_id=thread,
                request_id=request_id,
                conversation_id=conversation_id,
                case_ids=[draw["case_id"]],
                depth=depth,
                draw_id=draw_id,
            )
            if reading_id is not None:
                options["reading_id"] = reading_id
            ingress = ThreadIngress(self.service)
            if source_ids is not None:
                return ingress.queue(source_ids=source_ids, **options)
            text = "我揭开了牌，帮我看看" if message in (None, "") else message
            return ingress.submit(message=text, **options)
