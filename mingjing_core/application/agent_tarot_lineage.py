"""Bind fixed tarot viewers to actual source ranges and completed tool steps."""

from __future__ import annotations

from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.adapters.tarot import TarotService
from mingjing_core.application.agent_commit_versions import reconcile_versions
from mingjing_core.application.agent_tools_contracts import (
    ToolContext,
    ToolResult,
    tool_input_fingerprint,
)
from mingjing_core.application.agent_tools_memory import source_ref
from mingjing_core.application.agent_tools_policy import source_policy
from mingjing_core.application.agent_tools_tarot_guard import INSIST, NOT_INSIST, validate_draw_source
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.memory.policy import clause, mask_quoted
from mingjing_core.repositories.postgres import fingerprint


def cache_id(ctx: ToolContext) -> str:
    return "agent_tarot_cache_" + fingerprint([ctx.owner, ctx.operation_id])[:32]


def operation_source_refs(
    service: Any, ctx: ToolContext, args: dict[str, Any], source: dict[str, Any], start: int, end: int
) -> list[dict[str, Any]]:
    ranges = {(start, end)}
    for option in args["options"].values():
        position = source["content"].find(option)
        if position < 0:
            raise EvidenceError("塔罗选项没有真实原话")
        ranges.add((position, position + len(option)))
    if args["explicit_new"]:
        visible = mask_quoted(source["content"])
        ranges.update(
            (match.start(), match.end())
            for match in INSIST.finditer(visible)
            if NOT_INSIST.search(clause(visible, match.start(), match.end())) is None
        )
    refs = []
    for left, right in sorted(ranges):
        service.check_span(ctx, source["id"], left, right)
        refs.append(source_ref(source, left, right))
    return refs


def question_sources(service: Any, ctx: ToolContext, draw: dict[str, Any]) -> dict[str, Any] | None:
    snapshot = draw.get("context_snapshot", {})
    ident, refs = snapshot.get("question_message_id"), snapshot.get("source_refs")
    if not ident or not isinstance(refs, list) or not refs:
        return None
    # Legacy snapshots with background/facts need their own complete adapter;
    # a question hash alone cannot authorize those additional dependencies.
    if set(snapshot) != {"question_message_id", "source_ids", "source_refs", "thread_id"}:
        return None
    if snapshot["source_ids"] != [ident] or snapshot["thread_id"] != "life:" + ctx.subject:
        raise ScopeError("牌阵问题来源不属于主线程")
    source = service.repo.get(ctx.owner, "message", ident)
    source_policy(source, ctx.subject, "life:" + ctx.subject)
    if source.get("role") != "user" or service.repo.is_revoked(ctx.owner, "message", ident):
        raise EvidenceError("牌阵缺少有效用户原话")
    for ref in refs:
        start, end = ref.get("start"), ref.get("end")
        if (
            ref.get("message_id") != ident
            or type(ref.get("version")) is not int
            or ref["version"] != source["revision"]
            or type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(source["content"])
            or ref.get("quote") != source["content"][start:end]
        ):
            raise EvidenceError("牌阵原话区间或版本不符")
        service.check_span(ctx, ident, start, end)
    if not any(ref["quote"].strip() == draw["question"] for ref in refs):
        raise EvidenceError("牌阵问题与实际原话不符")
    return {"source_ids": [ident], "source_refs": refs, "versions": {"message:" + ident: source["revision"]}}


def reading_identity(service: Any, run: dict[str, Any], draw: dict[str, Any]) -> dict[str, Any] | None:
    ident = run["request"].get("reading_id")
    if ident is None:
        return None
    try:
        row = TarotService(service.repo).get_reading(run["owner"], ident)
    except (KeyError, ValueError):
        raise EvidenceError("实际塔罗解读记录不存在") from None
    if row["draw_id"] != draw["id"]:
        raise ScopeError("塔罗解读未绑定当前牌阵")
    return {key: row[key] for key in ("id", "draw_id", "version", "model", "prompt_version", "created_at")}


def save_tarot_snapshot(service: Any, ctx: ToolContext, args: dict[str, Any], result: ToolResult) -> None:
    if not result.ok or ctx.private:
        return
    run = service.repo.fetch_run(ctx.owner, ctx.run_id)
    draw = result.data["draw"]
    sources = question_sources(service, ctx, draw)
    if sources is None:
        return
    primary = service.source(ctx, run["request"]["source_message_id"])
    sources["source_ids"] = list(dict.fromkeys([*sources["source_ids"], primary["id"]]))
    sources["versions"]["message:" + primary["id"]] = primary["revision"]
    snapshot = {
        "run_id": ctx.run_id,
        "epoch": ctx.epoch,
        "seq": ctx.seq,
        "name": ctx.name,
        "input_fp": ctx.input_fp,
        "arguments": args,
        "input_source_versions": ctx.source_versions,
        "native_draw_id": draw["id"],
        "native_reading_id": run["request"].get("reading_id"),
        "native_sha256": fingerprint(draw),
        "output_sha256": fingerprint(result.model_dump()),
        "reading": reading_identity(service, run, draw),
        **sources,
    }
    versions = reconcile_versions(service.repo, run, run["state_version"])
    for key, value in sources["versions"].items():
        if key in versions and versions[key] != value:
            raise RevisionConflict("牌阵来源与本轮已采用版本不一致")
        versions[key] = value
    service.repo.set_run_dependencies(ctx.owner, ctx.run_id, versions, ctx.lease_token)
    service.repo.put(
        ctx.owner,
        "runtime_step",
        cache_id(ctx),
        snapshot,
        subject=ctx.subject,
        expected_revision=0,
        operation_id=ctx.operation_id + ":tarot_cache",
    )


def completed_context(service: Any, run: dict[str, Any], name: str, result: ToolResult) -> ToolContext:
    if name not in {"tarot_start", "tarot_read"}:
        raise EvidenceError("不是塔罗工具步骤")
    with service.repo.transaction(run["owner"]) as connection:
        step = connection.execute(
            sql.SQL(
                "SELECT seq,input_fp FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND kind='tool' "
                "AND name=%s AND status='completed' AND error_code IS NULL AND finished_at IS NOT NULL "
                "AND output=%s ORDER BY seq DESC LIMIT 1"
            ).format(service.repo.table("core_run_steps")),
            (run["owner"], run["id"], run["retry_epoch"], name, Jsonb(result.model_dump())),
        ).fetchone()
    if step is None:
        raise EvidenceError("塔罗结果缺少当前批次已完成工具步骤")
    return ToolContext(
        run["owner"],
        run["id"],
        run["subject"],
        run["retry_epoch"],
        step["seq"],
        run["lease_token"],
        name,
        step["input_fp"],
        run.get("thread_id") or run["request"].get("thread_id") or "life:" + run["subject"],
        case_ids=tuple(run["request"].get("case_ids", [])),
    )


def attest_tarot_snapshot(service: Any, run: dict[str, Any], name: str, result: ToolResult) -> dict[str, Any] | None:
    """No aliases here: this first slice proves only the native tool snapshot."""
    if not result.ok:
        return None
    with service.repo.transaction(run["owner"]) as connection:
        ctx = completed_context(service, run, name, result)
        current = service.authority(connection, ctx)
        if ctx.private or current["request"].get("incognito") is True:
            raise ScopeError("无痕线程不能注册长期塔罗依据")
        cached = service.repo.get(ctx.owner, "runtime_step", cache_id(ctx), include_deleted=True)
        if (
            cached["status"] != "active"
            or cached.get("run_id") != ctx.run_id
            or cached.get("epoch") != ctx.epoch
            or cached.get("name") != name
            or cached.get("seq") != ctx.seq
            or cached.get("input_fp") != ctx.input_fp
            or tool_input_fingerprint(name, cached["arguments"], cached["input_source_versions"]) != ctx.input_fp
            or cached.get("output_sha256") != fingerprint(result.model_dump())
        ):
            raise EvidenceError("塔罗缓存与实际工具步骤不符")
        draw = TarotService(service.repo).get(ctx.owner, cached["native_draw_id"])
        if name == "tarot_read":
            if current["request"].get("draw_id") != draw["id"]:
                raise ScopeError("塔罗读取未绑定本轮牌阵")
            draw = TarotService(service.repo).get_for_reading(ctx.owner, draw["id"])
        if fingerprint(draw) != cached["native_sha256"] or fingerprint(draw) != fingerprint(result.data["draw"]):
            raise EvidenceError("塔罗牌面或输入已改变")
        if cached["native_reading_id"] != current["request"].get("reading_id") or cached["reading"] != reading_identity(
            service, current, draw
        ):
            raise EvidenceError("塔罗解读身份已改变")
        sources = question_sources(service, ctx, draw)
        if sources is None or fingerprint(sources["source_refs"]) != fingerprint(cached["source_refs"]):
            raise EvidenceError("塔罗缺少完整问题来源")
        if not service.repo.verify_versions(ctx.owner, cached["versions"]):
            raise RevisionConflict("塔罗来源版本已经改变")
        return cached


def tarot_lineage(
    service: Any, run: dict[str, Any], name: str, result: ToolResult
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    from mingjing_core.application.agent_tarot_records import persist_records
    from mingjing_core.application.privacy_run_barrier import run_persistence_blocked

    if not result.ok:
        return [], {}
    with service.repo.transaction(run["owner"]):
        current = service.repo.fetch_run(run["owner"], run["id"])
        if run_persistence_blocked(service.repo, current):
            raise ScopeError("塔罗长期依据在本轮已停止保存")
        if unregistered_legacy_read(service, run, name, result):
            return [], {}
        cached = attest_tarot_snapshot(service, run, name, result)
        if cached is None:
            raise EvidenceError("塔罗依据缺少已完成步骤")
        draw = result.data["draw"]
        records = persist_records(service, current, cached, draw)
        versions = dict(cached["versions"])
        if records:
            versions["case:" + draw["case_id"]] = service.repo.versions(
                run["owner"], run["subject"], [draw["case_id"]]
            )["case:" + draw["case_id"]]
        return records, versions


def unregistered_legacy_read(service: Any, run: dict[str, Any], name: str, result: ToolResult) -> bool:
    """A proven legacy read stays readable; insufficient ranges never create c/r."""
    if name != "tarot_read":
        return False
    with service.repo.transaction(run["owner"]) as connection:
        ctx = completed_context(service, run, name, result)
        current = service.authority(connection, ctx)
        if ctx.private or current["request"].get("incognito") is True:
            raise ScopeError("无痕线程不能采用长期塔罗结果")
        cached = connection.execute(
            sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND kind='runtime_step' AND id=%s").format(
                service.repo.table("core_entities")
            ),
            (ctx.owner, cache_id(ctx)),
        ).fetchone()
        operation = connection.execute(
            sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND operation_id=%s").format(
                service.repo.table("core_operations")
            ),
            (ctx.owner, ctx.operation_id + ":tarot_cache"),
        ).fetchone()
        # Deleted or tampered new caches must not silently become legacy reads.
        if cached is not None or operation is not None:
            return False
        actual = current["request"].get("draw_id")
        try:
            draw = TarotService(service.repo).get_for_reading(ctx.owner, actual)
        except (KeyError, ValueError):
            raise EvidenceError("旧牌读取不属于本轮有效固定牌阵") from None
        if draw["subject_id"] != ctx.subject or not draw.get("context_snapshot", {}).get("question_message_id"):
            raise ScopeError("旧牌缺少可核对的同人物用户问题来源")
        expected = ToolResult(ok=True, data={"draw": draw}, summary="固定牌面与牌义已读取")
        if fingerprint(expected.model_dump()) != fingerprint(result.model_dump()):
            raise EvidenceError("旧牌结果与当前真实固定牌面不符")
        validate_draw_source(service, ctx, draw)
        reading_identity(service, current, draw)
        return question_sources(service, ctx, draw) is None
