"""Scheduled report requests use Core; no second report-writing agent."""
from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path
from psycopg import sql

from mingjing_core.domain.contracts import ScopeError, EvidenceError
from mingjing_core.domain.report_schedules import SHANGHAI as SHANGHAI, schedule_on_day, report_period_bounds
from .hermes import validated_payload

KINDS = {"daily": "晨报", "weekly": "周报", "monthly": "月报", "quarterly": "季报"}


def report_schedule(kind: str, day: date):
    """Preserve existing Asia/Shanghai preparation/delivery times."""
    return schedule_on_day(kind,day)


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
        from mingjing_core.application.report_schedules import ReportScheduleService
        policy = ReportScheduleService(self.service.repo).effective(binding['owner'], kind)
        schedule = schedule_on_day(kind, parsed, policy if policy['configured'] or policy['initialized'] else None)
        if schedule is None:
            raise ValueError("这一天不属于原定报告计划")
        business = "report:" + str(external_id) + ":" + kind + ":" + day
        operation = operation_id or business
        repo = self.service.repo
        # A transport or process retry keeps the same Core operation and
        # budget. Only an explicit schedule revision starts a new operation.
        with repo.transaction(binding['owner']) as connection:
            old = connection.execute(sql.SQL('SELECT id,status,state_version FROM {} WHERE owner=%s AND operation_id=%s FOR UPDATE').format(repo.table('core_runs')), (binding['owner'],operation)).fetchone()
            if old and old['status']=='succeeded' and not repo.verify_versions(binding['owner'],old['state_version']):
                connection.execute(sql.SQL("UPDATE {} SET status='stale',error='报告依赖已更新' WHERE owner=%s AND id=%s AND status='succeeded'").format(repo.table('core_runs')), (binding['owner'],old['id']))
                old=dict(old,status='stale')
            if old and old['status'] in ('failed','stale'):
                retried=repo.prepare_retry(binding['owner'],old['id'])
                if retried['purge_checkpoint']:
                    self.service.runtime.purge(old['id'],retried['run']['retry_epoch']-1)
        period=report_period_bounds(kind,parsed)
        message = (
            f"请生成{day}的{KINDS[kind]}，覆盖期间{period['start']}至{period['end']}。这是定期报告：读取最新有效事实、事项与已确认反馈；"
            "只调用本期必要体系，不能随机新增塔罗。逐日差异必须实际计算，否则说明未计算；"
            "先白话重点，再现实安排，专业依据置于最后。旧预测不能当成已经发生的用户经历。"
        )
        result = await self.service.consult(
            owner=binding["owner"], subject=binding["subject"], message=message,
            conversation_id="report:" + str(external_id), case_ids=case_ids,
            request_id=operation, mode="scheduled_report", depth=depth, emit=emit,
            selection={'report_schedule_kind':kind,'report_schedule_revision':policy['revision'],'date':day,'period':period},
        )
        result=validated_payload(result)
        run=repo.fetch_run(binding['owner'],result['meta']['core_run']['run_id'])
        if run['status']!='succeeded' or run['result']!=result or run['subject']!=binding['subject']:
            raise EvidenceError('报告必须来自当前人物的持久成功执行')
        manifest={"kind":kind,"date":day,"period":period,"business_id":business,"run_id":result['meta']['core_run']['run_id'],
                  "prepare_at":schedule['prepare_at'].isoformat(),"deliver_at":schedule['deliver_at'].isoformat(),"timezone":schedule['timezone']}
        repo=self.service.repo
        with repo.transaction(binding['owner']):
            try:existing=repo.get(binding['owner'],'report',business,include_deleted=True)
            except ScopeError:existing=None
            if not existing or existing.get('run_id')!=manifest['run_id']:
                repo.put(binding['owner'],'report',business,dict(manifest,type=KINDS[kind],content=result['answer'],
                         schema_version=result['schema_version'],validation=result['validation'],guidance=result,
                         dependencies=run['dependencies']),subject=binding['subject'],
                         expected_revision=existing['revision'] if existing else 0,operation_id='report-manifest:'+manifest['run_id'])
        return dict(result,report=manifest)

    async def prepare_delivery(self, *, external_id: str, result: dict, channel: str, target: str):
        binding = self.identity(external_id)
        if not isinstance(result,dict):raise EvidenceError('报告结果格式无效')
        validated_payload({key:value for key,value in result.items() if key!='report'})
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
