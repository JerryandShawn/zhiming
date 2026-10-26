"""One native consent consumption and local calculation; no chart/fact persistence."""

from copy import deepcopy
from subprocess import TimeoutExpired

from mingjing_core.adapters.charts.p8_adapter import P8ChartAdapter
from mingjing_core.agent.tools.p8_parameters import Synastry
from mingjing_core.application.agent_tool_persistence import privacy_refusal
from mingjing_core.application.agent_tools_contracts import ToolResult, tool_input_fingerprint
from mingjing_core.application.charts_natal import natal_request
from mingjing_core.application.p8_chart_service import P8CalculationUnavailable
from mingjing_core.application.synastry_consent import SynastryConsentService
from mingjing_core.application.synastry_result import verify_synastry
from mingjing_core.domain.contracts import CoreError, EvidenceError, ScopeError
from mingjing_core.repositories.postgres import fingerprint


def cache_id(ctx):
    return "synastry_step_" + fingerprint([ctx.owner, ctx.operation_id])[:32]


def cached(service, ctx):
    try:
        row = service.repo.get(ctx.owner, "runtime_step", cache_id(ctx), include_deleted=True)
    except ScopeError:
        return None
    if (
        row["status"] != "active"
        or (row.get("run_id"), row.get("epoch"), row.get("input_fp")) != (ctx.run_id, ctx.epoch, ctx.input_fp)
        or not service.repo.verify_versions(ctx.owner, row["source_versions"])
    ):
        raise EvidenceError("原合盘步骤或出生资料已失效")
    for ident in row["source_ids"]:
        if service.repo.is_revoked(ctx.owner, "message", ident):
            raise EvidenceError("合盘来源已经撤销")
    if row.get("consent_id"):
        consent = SynastryConsentService(service.repo, clock=service.clock)._current(ctx.owner, row["consent_id"])
        if consent.get("consumed_by") != ctx.operation_id:
            raise EvidenceError("合盘授权消费与原步骤不符")
    if row["state"] != "completed":
        raise P8CalculationUnavailable("原合盘计算未取得完整结果，不能重复消费旧授权")
    return ToolResult.model_validate(row["tool_output"])


def store(service, ctx, data, *, previous=None):
    return service.repo.put(
        ctx.owner,
        "runtime_step",
        cache_id(ctx),
        dict(data, run_id=ctx.run_id, epoch=ctx.epoch, input_fp=ctx.input_fp, ephemeral_synastry=True),
        subject=ctx.subject,
        expected_revision=previous["revision"] if previous else 0,
        operation_id=ctx.operation_id + (":synastry-result" if previous else ":synastry-start"),
    )


def prepare(service, ctx, args):
    consent_service = SynastryConsentService(service.repo, clock=service.clock)
    with service.repo.transaction(ctx.owner) as connection:
        run = service.authority(connection, ctx)
        source = service.source(ctx, run["request"]["source_message_id"])
        if source.get("channel") != "web":
            return ToolResult(ok=False, data={"code": "CONSENT_REQUIRED"}, summary="请去网页确认本次合盘"), None
        if stopped := privacy_refusal(service, "synastry", args, ctx):
            return stopped, None
        if replay := cached(service, ctx):
            return replay, None
        grant = consent_service.find_granted(
            ctx.owner, ctx.subject, args["other_subject_id"], args["kind"], source["conversation_id"]
        )
        base = {"source_versions": {"message:" + source["id"]: source["revision"]}, "source_ids": [source["id"]]}
        if grant is None:
            card = consent_service.request(
                ctx.owner, ctx.subject, args["other_subject_id"], args["kind"], source["id"], ctx.operation_id
            )
            result = ToolResult(
                ok=False,
                data={"code": "CONSENT_REQUIRED", "confirmation_id": card["id"]},
                summary="请在网页确认本次合盘；尚未使用对方出生资料计算",
            )
            store(service, ctx, dict(base, state="completed", tool_output=result.model_dump()))
            return result, None
        consumed = consent_service.consume(
            ctx.owner,
            grant,
            subject_a=ctx.subject,
            subject_b=args["other_subject_id"],
            kind=args["kind"],
            operation_id=ctx.operation_id,
        )
        snapshots = consumed["snapshots"]
        facts = [fact for snapshot in snapshots for fact in snapshot["facts"]]
        base["source_versions"].update(
            {key: value for snapshot in snapshots for key, value in snapshot["versions"].items()}
        )
        grant_row = consent_service._current(ctx.owner, grant)
        base["source_versions"]["entity:synastry_consent:" + grant] = grant_row["revision"]
        for ident in grant_row["source_ids"]:
            original = service.memory.get_source(ctx.owner, ident)
            base["source_versions"]["message:" + ident] = original["revision"]
        base["source_ids"] = list(dict.fromkeys(base["source_ids"] + grant_row["source_ids"]))
        base.update(
            consent_id=grant,
            used_fact_ids=[row["id"] for row in facts],
            source_refs=[ref for row in facts for ref in row.get("source_refs", [])],
            snapshots=snapshots,
            arguments=args,
            state="calculating",
            reflection_eligible=False,
        )
        return None, store(service, ctx, base)


def calculate(service, ctx, args, snapshots):
    at = service.clock.now().date().isoformat()
    requests = [
        natal_request(row, owner=ctx.owner, subject=row["subject_id"], operation_id=ctx.operation_id, as_of=at)
        for row in snapshots
    ]
    try:
        payload = P8ChartAdapter(ctx.owner).synastry(
            dict(chart_a=requests[0], chart_b=requests[1], kind=args["kind"], consent="user_confirmed", as_of_date=at)
        )
    except CoreError:
        raise
    except (OSError, RuntimeError, ValueError, TypeError, TimeoutExpired):
        raise P8CalculationUnavailable("本次合盘未完成，原授权已消费；没有采用未核对结果") from None
    verify_synastry(payload, ctx.owner, snapshots, ctx.operation_id, args["kind"])
    return payload


def execute_synastry(service, arguments, ctx):
    args = Synastry.model_validate(arguments).model_dump()
    if ctx.private or ctx.crisis:
        raise ScopeError("当前模式不可进行合盘")
    if ctx.name != "synastry" or ctx.input_fp != tool_input_fingerprint("synastry", args, ctx.source_versions):
        raise EvidenceError("合盘参数与原生步骤不符")
    if getattr(service.repo._local, "connection", None) is not None:
        raise EvidenceError("合盘计算必须在外层数据库事务外运行")
    immediate, marker = prepare(service, ctx, args)
    if immediate is not None:
        return immediate
    payload = calculate(service, ctx, args, marker["snapshots"])
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        if stopped := privacy_refusal(service, "synastry", args, ctx):
            return stopped
        if not service.repo.verify_versions(ctx.owner, marker["source_versions"]):
            raise EvidenceError("合盘计算期间资料改变，结果未采用")
        grant = SynastryConsentService(service.repo, clock=service.clock)._current(ctx.owner, marker["consent_id"])
        if grant.get("consumed_by") != ctx.operation_id:
            raise EvidenceError("合盘授权消费已失效")
        result = ToolResult(
            ok=True,
            data={
                "adapter_mode": "p8_synastry_transient",
                "calculation": payload,
                "record_policy": {"memory": False, "profile": False, "reflection": False},
            },
            summary="本次合盘已计算，仅供本轮讨论；未写入记忆或档案，不保证关系结果",
        )
        store(service, ctx, dict(deepcopy(marker), state="completed", tool_output=result.model_dump()), previous=marker)
        return result
