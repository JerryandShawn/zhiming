"""U7 is an application guard over real fixed draws, separate from shuffling."""

from __future__ import annotations

import re
import unicodedata
from datetime import timedelta
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

from psycopg import sql

from mingjing_core.adapters.tarot import TarotService
from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.memory.policy import clause, mask_quoted
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService

INSIST = re.compile(
    r"我(?:还是|仍然)?坚持(?:要)?(?:再抽|重抽|重新抽)|请(?:再抽一次|重新抽牌?|重抽)|我要重新抽|还是想再抽一次"
)
NOT_INSIST = re.compile(r"不要|不想|不用|别|假如|假设|如果")


def normalize_question(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKC", text).casefold() if unicodedata.category(char)[0] in {"L", "N"}
    )


def similar_question(left: str, right: str) -> bool:
    a, b = normalize_question(left), normalize_question(right)
    if not a or not b:
        return False
    return a == b or min(len(a), len(b)) >= 8 and SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.88


def explicit_redraw(text: str) -> bool:
    visible = mask_quoted(text)
    return any(
        NOT_INSIST.search(clause(visible, match.start(), match.end())) is None for match in INSIST.finditer(visible)
    )


def validate_draw_source(service: AgentToolsService, ctx: ToolContext, draw: dict[str, Any]) -> None:
    if draw["subject_id"] != ctx.subject or draw.get("context_revoked"):
        raise ScopeError("牌阵人物或来源已经失效")
    snapshot = draw.get("context_snapshot", {})
    ident = snapshot.get("question_message_id")
    if not ident:
        return
    source = service.memory.get_source(ctx.owner, ident)
    if (
        source["subject_id"] != ctx.subject
        or source["status"] != "active"
        or service.repo.is_revoked(ctx.owner, "message", ident)
        or source.get("role") != "user"
        or source.get("thread_id") != "life:" + ctx.subject
    ):
        raise EvidenceError("牌阵问题来源已失效")
    for ref in snapshot.get("source_refs", []):
        if ref.get("message_id") == ident and ref.get("version") != source["revision"]:
            raise EvidenceError("牌阵问题来源版本已改变")
    quote = draw["question"]
    start = source["content"].find(quote)
    if start < 0:
        raise EvidenceError("牌阵问题不能回溯到原话")
    service.check_span(ctx, ident, start, start + len(quote))


def recent_draw(
    service: AgentToolsService,
    ctx: ToolContext,
    question: str,
) -> tuple[dict[str, Any] | None, bool]:
    now = service.clock.now()
    cutoff = now - timedelta(hours=24)
    service.repo.assert_scope(ctx.owner, ctx.subject)
    with service.repo.transaction(ctx.owner) as connection:
        ids = connection.execute(
            sql.SQL(
                "SELECT id FROM {} WHERE owner=%s AND subject=%s "
                "AND (payload->>'created_at')::timestamptz>%s "
                "AND (payload->>'created_at')::timestamptz<=%s ORDER BY created_at DESC,id DESC LIMIT 201"
            ).format(service.repo.table("tarot_draws")),
            (ctx.owner, ctx.subject, cutoff, now),
        ).fetchall()
    for item in ids[:200]:
        row = TarotService(service.repo).get(ctx.owner, item["id"])
        at = history_instant(row.get("created_at"))
        if at is None or not cutoff < at <= now:
            continue
        try:
            validate_draw_source(service, ctx, row)
        except (EvidenceError, ScopeError):
            continue
        if similar_question(question, row["question"]):
            return row, False
    return None, len(ids) > 200


def tarot_mode(service: AgentToolsService, ctx: ToolContext) -> str:
    """Visibility derives from the leased run and selected real draw, never model flags."""
    with service.repo.transaction(ctx.owner) as connection:
        run = service.repo._leased(connection, ctx.owner, ctx.run_id, ctx.lease_token)
        if run["runtime"] != "v4" or run["retry_epoch"] != ctx.epoch or run["cancel_requested_at"] is not None:
            raise LeaseConflict("塔罗运行已失效")
        if run["deadline_at"] is not None and run["deadline_at"] <= service.clock.now():
            raise LeaseConflict("塔罗运行时间已结束")
        thread = run["thread_id"] or run["request"].get("thread_id") or "life:" + run["subject"]
        if run["subject"] != ctx.subject or thread != ctx.thread_id:
            raise ScopeError("塔罗运行范围不符")
        service._case_scope(run, ctx)
        ident = run["request"].get("draw_id")
        if not ident:
            return "tarot_start"
        try:
            draw = TarotService(service.repo).get(ctx.owner, ident)
        except KeyError:
            raise ScopeError("选中的牌阵不存在或不属于当前身份") from None
        validate_draw_source(service, ctx, draw)
        if ctx.case_ids and draw["case_id"] not in ctx.case_ids:
            raise ScopeError("牌阵不在当前选中事项")
        return "tarot_read" if draw["status"] == "ready" else "tarot_start"
