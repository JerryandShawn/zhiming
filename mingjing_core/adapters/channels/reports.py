"""Scheduled report requests use Core; no second report-writing agent."""
from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from mingjing_core.domain.contracts import ScopeError, EvidenceError
from .hermes import validated_payload

SHANGHAI = timezone(timedelta(hours=8))
KINDS = {"daily": "晨报", "weekly": "周报", "monthly": "月报", "quarterly": "季报"}


def report_schedule(kind: str, day: date):
    """Preserve existing Asia/Shanghai preparation/delivery times."""
    if kind not in KINDS:
        raise ValueError("报告类型无效")
    if kind == "weekly" and day.weekday() != 6:
        return None
    if kind in ("monthly", "quarterly") and day.day != 1:
        return None
    if kind == "quarterly" and day.month not in (1, 4, 7, 10):
        return None
    due = datetime(day.year, day.month, day.day,
                   {"daily": 7, "weekly": 20, "monthly": 9, "quarterly": 10}[kind], tzinfo=SHANGHAI)
    return {"prepare_at": due - timedelta(minutes=15), "deliver_at": due, "timezone": "Asia/Shanghai"}


class CoreReportAdapter:
    def __init__(self, base: str | Path, *, service=None):
        self.base = Path(base)
        self._service = service

    @property
    def service(self):
        if self._service is None:
            from mingjing_core.application.consultation import ConsultationService
            self._service = ConsultationService.from_base(self.base)
        return self._service

    def identity(self, external_id: str):
        if not external_id:
            raise ScopeError("定期任务需要已绑定的 report external_id")
        return self.service.repo.resolve_channel("report", str(external_id))

    async def prepare(self, *, external_id: str, kind: str, day: str,
                      operation_id: str | None = None, case_ids=None,
                      depth="standard", emit=None):
        binding = self.identity(external_id)
        parsed = date.fromisoformat(day)
        schedule = report_schedule(kind, parsed)
        if schedule is None:
            raise ValueError("这一天不属于原定报告计划")
        business = "report:" + str(external_id) + ":" + kind + ":" + day
        operation = operation_id or business
        message = (
            f"请生成{day}的{KINDS[kind]}。这是定期报告：读取最新有效事实、事项与已确认反馈；"
            "只调用本期必要体系，不能随机新增塔罗。逐日差异必须实际计算，否则说明未计算；"
            "先白话重点，再现实安排，专业依据置于最后。旧预测不能当成已经发生的用户经历。"
        )
        result = await self.service.consult(
            owner=binding["owner"], subject=binding["subject"], message=message,
            conversation_id="report:" + str(external_id), case_ids=case_ids,
            request_id=operation, mode="scheduled_report", depth=depth, emit=emit,
        )
        validated_payload(result)
        manifest={"kind":kind,"date":day,"business_id":business,"run_id":result['meta']['core_run']['run_id'],
                  "prepare_at":schedule['prepare_at'].isoformat(),"deliver_at":schedule['deliver_at'].isoformat(),"timezone":schedule['timezone']}
        repo=self.service.repo
        with repo.transaction(binding['owner']):
            try:existing=repo.get(binding['owner'],'report',business,include_deleted=True)
            except ScopeError:existing=None
            if not existing or existing.get('run_id')!=manifest['run_id']:
                repo.put(binding['owner'],'report',business,dict(manifest,type=KINDS[kind],content=result['answer'],
                         schema_version='core3.0',validation=result['validation'],guidance=result,
                         dependencies=result['meta']['core_run']['dependencies']),subject=binding['subject'],
                         expected_revision=existing['revision'] if existing else 0,operation_id='report-manifest:'+manifest['run_id'])
        return dict(result,report=manifest)

    async def prepare_delivery(self, *, external_id: str, result: dict, channel: str, target: str):
        binding = self.identity(external_id)
        validated_payload(result)
        report = result.get("report", {})
        if not report.get("business_id"):
            raise ValueError("报告缺少稳定业务标识")
        # The service resolves ownership and rechecks dependencies against the
        # persisted run; the supplied result is never a free-form outbox input.
        manifest=self.service.repo.get(binding['owner'],'report',report['business_id'])
        run_id=result['meta']['core_run']['run_id']
        if manifest.get('run_id')!=run_id or manifest['subject_id']!=binding['subject']:
            raise EvidenceError('报告manifest与权威执行不一致')
        prepared = self.service.prepare_delivery(
            owner=binding["owner"], run_id=run_id,
            business_id=report["business_id"], channel=channel, target=target,
            due=manifest['deliver_at'], replace_stale=True,
        )
        return await prepared if inspect.isawaitable(prepared) else prepared
