"""Versioned owner report times; bindings and recipients remain protected."""
from __future__ import annotations

from datetime import date, datetime

from psycopg import sql
from mingjing_core.timekit.clock import get_clock
from pydantic import ValidationError

from mingjing_core.domain.consultation import MissingInput
from mingjing_core.domain.contracts import ScopeError, EvidenceError, RevisionConflict, LeaseConflict
from mingjing_core.domain.report_schedules import (
    KINDS, LABELS, POLICY_FIELDS, SHANGHAI, ReportSchedulePatch, ReportSchedulePolicy,
    default_policy, next_schedule, report_period,
)


class ReportScheduleService:
    def __init__(self, repository):
        self.repo = repository

    def _configuration(self, owner, kind):
        pipeline = self.repo.assert_scope(owner)['settings'].get('report_pipeline', {})
        if not isinstance(pipeline,dict) or not isinstance(pipeline.get('jobs',[]),list):
            return None, '报告渠道尚未配置'
        jobs = [job for job in pipeline.get('jobs',[]) if isinstance(job,dict) and job.get('kind')==kind]
        if len(jobs) != 1:
            return None, '报告渠道尚未配置' if not jobs else '同类报告任务配置不明确'
        job = jobs[0]
        external = job.get('external_id') or job.get('id')
        channel = job.get('channel','feishu')
        target = job.get('target')
        subject = job.get('subject','self')
        if not isinstance(external,str) or not external or channel != 'feishu' or not isinstance(target,str):
            return None, '报告渠道尚未配置'
        try:
            self.repo.assert_scope(owner,subject)
            task = self.repo.resolve_channel('report',external)
            receiver = self.repo.resolve_channel(channel,target)
            if (task['owner'],task['subject'],task['binding_kind']) != (owner,subject,'task'):
                return None, '报告任务未验证当前用户权限'
            expected = 'chat' if target.startswith('oc_') else 'user' if target.startswith('ou_') else None
            if expected is None or (receiver['owner'],receiver['subject'],receiver['binding_kind']) != (owner,subject,expected):
                return None, '报告收件渠道未验证当前用户权限'
        except (ScopeError,EvidenceError):
            return None, '报告渠道尚未配置'
        return dict(job, external_id=external, subject=subject,
                    legacy_enabled=pipeline.get('enabled') is True and job.get('enabled',True) is True), ''

    def effective(self, owner, kind):
        """Worker policy; reading an old configuration never creates authority."""
        if kind not in KINDS:raise MissingInput('报告类型无效')
        job, reason = self._configuration(owner,kind)
        try:
            entity = self.repo.get(owner,'report_schedule',kind)
        except ScopeError:
            entity = None
        values = {key:value for key,value in entity.items() if key in POLICY_FIELDS} if entity else default_policy(kind,enabled=bool(job and job['legacy_enabled']))
        policy = ReportSchedulePolicy.model_validate(values).model_dump(exclude_none=True)
        if not job:policy['enabled'] = False
        return dict(policy,configured=bool(job),initialized=entity is not None,
                    revision=entity['revision'] if entity else 0,
                    dependency={'report_schedule:'+kind:entity['revision'] if entity else 0},
                    policy_changed_at=entity.get('effective_after') if entity else None,
                    status_reason=reason)

    def _deliveries(self, owner, kind):
        job, _ = self._configuration(owner,kind)
        if not job:return []
        prefix = 'report:' + job['external_id'] + ':' + kind + ':'
        with self.repo.transaction(owner) as connection:
            return connection.execute(sql.SQL('SELECT id,status,business_id FROM {} WHERE owner=%s AND left(business_id,length(%s))=%s').format(
                self.repo.table('delivery_outbox')), (owner,prefix,prefix)).fetchall()

    def _row_period(self, kind, row):
        # Only rows already selected by the exact trusted prefix reach here.
        try:
            return report_period(kind,date.fromisoformat(row['business_id'].rsplit(':',1)[-1]))
        except (ValueError,TypeError):
            return None

    def _protected(self, owner, kind, rows=None):
        periods = set();unknown = False
        for row in rows if rows is not None else self._deliveries(owner,kind):
            if row['status'] not in ('sent','sending','uncertain'):continue
            period = self._row_period(kind,row)
            if period is None:unknown = True
            else:periods.add(period)
        return periods, unknown

    def protected_period(self, owner, kind, day: date):
        """Never make a new delivery date evade a same-period sent ledger."""
        with self.repo.transaction(owner):
            periods, unknown = self._protected(owner,kind)
            return unknown or report_period(kind,day) in periods

    def get(self, owner, kind, *, now: datetime | None = None):
        with self.repo.transaction(owner):
            policy = self.effective(owner,kind)
            current = now or get_clock().now()
            if current.tzinfo is None:raise ValueError('预览时刻需要时区')
            current = current.astimezone(SHANGHAI)
            deliveries = self._deliveries(owner,kind)
            periods, unknown = self._protected(owner,kind,deliveries)
            preview = next_schedule(kind,policy,now=current,blocked_periods=periods) if not unknown else None
            period = report_period(kind,current.date())
            current_rows = [row for row in deliveries if self._row_period(kind,row) in (period,None)]
            sending = sum(row['status']=='sending' for row in deliveries)
            uncertain = sum(row['status']=='uncertain' for row in current_rows)
            pending = sum(row['status'] in ('pending','ready','queued','rejected') for row in current_rows)
            sent = sum(row['status']=='sent' for row in current_rows)
            blocked = unknown or period in periods
            status = 'unconfigured' if not policy['configured'] else 'uninitialized' if not policy['initialized'] else 'active' if policy['enabled'] else 'paused'
            reason = policy['status_reason']
            if blocked:reason = '本期已发送或送达情况待确认，本次时间设置从下期生效'
            if unknown:reason = '已有报告送达记录的期次待核实，核实前不会另行安排发送'
            if sending:reason = '当前报告已开始投递，无法保证撤回；请等待状态确认后修改'
            return {key:value for key,value in dict(policy,id=kind,label=LABELS[kind],status=status,
                timezone='Asia/Shanghai',can_modify=policy['configured'] and not sending,status_reason=reason,
                next_prepare=preview['prepare_at'].isoformat() if preview and policy['enabled'] and policy['configured'] else None,
                next_delivery=preview['deliver_at'].isoformat() if preview and policy['enabled'] and policy['configured'] else None,
                preview_prepare=preview['prepare_at'].isoformat() if preview else None,
                preview_delivery=preview['deliver_at'].isoformat() if preview else None,
                blocked_current_period=blocked,
                delivery_state={'sending':sending,'uncertain':uncertain,'pending':pending,'sent':sent}).items() if key!='dependency'}

    def list(self, owner, *, now: datetime | None = None):
        with self.repo.transaction(owner):
            return {'timezone':'Asia/Shanghai','prepare_minutes':15,
                    'schedules':[self.get(owner,kind,now=now) for kind in KINDS]}

    def seed_defaults(self, owner):
        """Deployment-only initialization after protected legacy configuration."""
        counts = {'created':0,'existing':0,'unconfigured':0}
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner)
            for kind in KINDS:
                policy = self.effective(owner,kind)
                if policy['initialized']:
                    counts['existing'] += 1
                elif not policy['configured']:
                    counts['unconfigured'] += 1
                else:
                    data = {key:value for key,value in policy.items() if key in POLICY_FIELDS}
                    self.repo.put(owner,'report_schedule',kind,data,expected_revision=0)
                    counts['created'] += 1
        return counts

    def patch(self, owner, payload, *, now: datetime | None = None):
        try:
            command = ReportSchedulePatch.model_validate(payload)
        except ValidationError:
            raise MissingInput('仅可修改报告开关、24小时 HH:mm、周报星期及月报/季报日期（1至28或月末）') from None
        intent = command.model_dump(exclude_none=True,exclude={'request_id'})
        changes = {key:value for key,value in intent.items() if key in POLICY_FIELDS and key!='kind'}

        def effect():
            current = self.effective(owner,command.kind)
            if not current['configured']:
                raise ScopeError('报告渠道尚未配置；此页面不能新增绑定或收件目标')
            if current['revision'] != command.expected_revision:
                raise RevisionConflict('报告设置已变化，请读取最新版本后核对')
            old = {key:value for key,value in current.items() if key in POLICY_FIELDS}
            updated = ReportSchedulePolicy.model_validate(dict(old,**changes)).model_dump(exclude_none=True)
            if current['initialized'] and updated==old:
                return {'id':command.kind,'kind':'report_schedule','revision':current['revision'],'write_status':'saved'}
            rows = self._deliveries(owner,command.kind)
            if any(row['status']=='sending' for row in rows):
                raise LeaseConflict('当前报告已开始投递，无法保证撤回；请等待状态确认后修改')
            changed_at = now or get_clock().now()
            if changed_at.tzinfo is None:raise MissingInput('报告生效时刻需要时区')
            entity = self.repo.put(owner,'report_schedule',command.kind,
                                   dict(updated,effective_after=changed_at.astimezone(SHANGHAI).isoformat()),
                                   expected_revision=command.expected_revision)
            ids = [row['id'] for row in rows if row['status'] in ('pending','ready','queued','rejected')]
            if ids:
                with self.repo.transaction(owner) as connection:
                    connection.execute(sql.SQL("UPDATE {} SET status='stale',payload='{{}}',error='SCHEDULE_CHANGED',claim_token=NULL,lease_until=NULL,updated_at=now() WHERE owner=%s AND id=ANY(%s)").format(
                        self.repo.table('delivery_outbox')), (owner,ids))
            return {'id':command.kind,'kind':'report_schedule','revision':entity['revision'],'write_status':'saved'}

        receipt = self.repo.mutation_request(owner,'report-schedules',command.request_id,intent,effect)
        current = self.get(owner,command.kind,now=now)
        return dict(current,receipt=dict(receipt,revision=current['revision']))
