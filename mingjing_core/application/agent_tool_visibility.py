"""Read disclosure state from the leased run and completed current-epoch steps."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from psycopg import sql

from mingjing_core.agent.tool_visibility import VisibilityState
from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.application.agent_tools_followups import reminder_intent
from mingjing_core.application.metaphysics_intent import metaphysics_intent
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.memory.policy import mask_quoted
from mingjing_core.timeparse import parse_time_range

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService

TAROT = re.compile(r"塔罗|抽(?:一张|几张|张|牌)|占卜牌")
NO_TAROT = re.compile(r"(?:不要|不想|不用|别|不需要|不许|禁止).{0,8}(?:塔罗|抽.{0,3}牌)")
CORRECTION = re.compile(r"记错|记得不对|纠正|更正|改成|不是.{0,12}而是")
PROFILE = re.compile(
    r"(?:修改|更正|纠正|更新|改一下).{0,12}(?:资料|生日|出生|姓名|名字|时区)"
    r"|(?:资料|生日|出生|姓名|名字|时区).{0,12}(?:改为|改成|不对|有误|记错)"
)
PROGRESS = re.compile(r"那件事.{0,8}(?:进展|后续|怎么样)|事情.{0,8}进展")
DATE_CALC = re.compile(
    r"日期|几天|多少天|相隔|天数|间隔|年龄|周岁|虚岁|多大|农历|公历|阴历|阳历|星期|日历|历法|假日|调休"
)


def reminder_requested(text: str) -> bool:
    return reminder_intent(text) == "confirmed"


def step_state(rows: list[dict[str, Any]]) -> tuple[bool, bool]:
    searched = computed = False
    for row in rows:
        output = row["output"] or {}
        if output.get("ok") is not True:
            continue
        if row["name"] == "memory_search" and output.get("data", {}).get("items"):
            searched = True
        if row["name"] == "chart_compute":
            computed = True
    return searched, computed


def visibility_state(service: AgentToolsService, ctx: ToolContext) -> VisibilityState:
    with service.repo.transaction(ctx.owner) as connection:
        run = service.repo._leased(connection, ctx.owner, ctx.run_id, ctx.lease_token)
        if run["runtime"] != "v4" or run["retry_epoch"] != ctx.epoch or run["cancel_requested_at"] is not None:
            raise LeaseConflict("工具可见性运行已失效")
        if run["deadline_at"] is not None and run["deadline_at"] <= service.clock.now():
            raise LeaseConflict("工具可见性运行时间已结束")
        thread = run["thread_id"] or run["request"].get("thread_id") or "life:" + run["subject"]
        if run["subject"] != ctx.subject or thread != ctx.thread_id:
            raise ScopeError("工具可见性线程或人物不符")
        service._case_scope(run, ctx)
        source = service.source(ctx, run["request"]["source_message_id"])
        if source.get("content") != run["request"].get("message"):
            raise EvidenceError("工具可见性来源已改变")
        rows = connection.execute(
            sql.SQL(
                "SELECT name,output FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s "
                "AND kind='tool' AND status='completed' AND error_code IS NULL "
                "AND name IN ('memory_search','chart_compute')"
            ).format(service.repo.table("core_run_steps")),
            (ctx.owner, ctx.run_id, ctx.epoch),
        ).fetchall()
        prior = connection.execute(
            sql.SQL(
                "SELECT EXISTS(SELECT 1 FROM {} WHERE owner=%s AND subject=%s AND kind='message' "
                "AND id<>%s AND status='active' AND data->>'role'='user' AND data->>'thread_id'=%s)"
            ).format(service.repo.table("core_entities")),
            (ctx.owner, ctx.subject, source["id"], thread),
        ).fetchone()
    searched, computed = step_state(rows)
    text = mask_quoted(source["content"])
    parsed = parse_time_range(text, ctx.at or service.clock.now(), service.timezone(ctx))
    tarot_pending = False if ctx.crisis or ctx.private else service.tarot_visibility(ctx) == "tarot_read"
    return VisibilityState(
        date_context=bool(DATE_CALC.search(text)) or parsed.start is not None or parsed.needs_clarification,
        memory_search_has_results=searched,
        memory_correcting=CORRECTION.search(text) is not None,
        first_meeting=not prior["exists"],
        profile_editing=PROFILE.search(text) is not None,
        tarot_topic=TAROT.search(text) is not None and NO_TAROT.search(text) is None,
        tarot_pending=tarot_pending,
        case_bound=bool(ctx.case_ids),
        case_progress=PROGRESS.search(text) is not None,
        chart_computed=computed,
        metaphysics_intent=metaphysics_intent(source["content"]),
        reminder_requested=reminder_requested(source["content"]),
    )
