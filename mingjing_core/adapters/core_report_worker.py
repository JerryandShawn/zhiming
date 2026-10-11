"""One-minute scheduled Core worker; configuration and effects live in PG."""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime,timedelta
import json
import os

from mingjing_core.domain.contracts import ScopeError,EvidenceError,RevisionConflict,LeaseConflict
from .channels.reports import CoreReportAdapter,report_schedule,SHANGHAI
from .channels.delivery import CoreDeliveryWorker


class CoreReportWorker:
    def __init__(self,service,transport):
        self.service=service;self.repo=service.repo
        self.reports=CoreReportAdapter('.',service=service)
        self.delivery=CoreDeliveryWorker(service,transport)

    def _manifest(self,owner,business):
        try:return self.repo.get(owner,'report',business)
        except (ScopeError,EvidenceError):return None

    def _fresh_manifest(self,owner,manifest):
        if not manifest or not manifest.get('run_id'):return False
        try:
            run=self.repo.fetch_run(owner,manifest['run_id'])
            return run['status']=='succeeded' and self.repo.verify_versions(owner,run['dependencies'])
        except (ScopeError,EvidenceError):return False

    def _claim_generation(self,owner,business,subject,now):
        ident='report-preparation:'+business
        with self.repo.transaction(owner):
            try:old=self.repo.get(owner,'request',ident)
            except ScopeError:old=None
            if old and old.get('next_attempt') and now<datetime.fromisoformat(old['next_attempt']):return None
            if old and old.get('generation_status')=='running' and now<datetime.fromisoformat(old['lease_until']):return None
            attempts=(old.get('attempts',0) if old else 0)+1
            if attempts>3:return None
            data={'business_id':business,'attempts':attempts,'generation_status':'running','lease_until':(now+timedelta(minutes=15)).isoformat(),'next_attempt':(now+timedelta(minutes=10)).isoformat()}
            return self.repo.put(owner,'request',ident,data,subject=subject,expected_revision=old['revision'] if old else 0)

    def _finish_generation(self,owner,state,success):
        with self.repo.transaction(owner):
            latest=self.repo.get(owner,'request',state['id'])
            if latest.get('attempts')!=state['attempts']:return
            self.repo.update(owner,'request',state['id'],{'generation_status':'complete' if success else 'failed'},expected_revision=latest['revision'])

    async def tick(self,owner,now=None):
        now=now or datetime.now(SHANGHAI)
        if now.tzinfo is None:raise ValueError('worker时刻须含时区')
        config=self.repo.assert_scope(owner)['settings'].get('report_pipeline',{})
        if not config.get('enabled'):return {'enabled':False,'prepared':0,'sent':0,'failures':0}
        counts={'enabled':True,'prepared':0,'sent':0,'failures':0}
        allowed_deliveries=set()
        self.service.outbox.recover_claims(owner,now)
        self.service.outbox.invalidate_pending(owner)
        for delta in (0,1):
            day=(now+timedelta(days=delta)).date()
            for job in config.get('jobs',[]):
                if job.get('enabled') is False:continue
                schedule=report_schedule(job['kind'],day)
                if not schedule or now<schedule['prepare_at'] or now>schedule['deliver_at']+timedelta(hours=12):continue
                if config.get('start_at') and schedule['deliver_at']<datetime.fromisoformat(config['start_at']):continue
                external=job.get('external_id') or job['id']
                binding=self.repo.resolve_channel('report',external)
                if binding['owner']!=owner:raise ScopeError('报告job绑定其他owner')
                business='report:'+external+':'+job['kind']+':'+day.isoformat()
                allowed_deliveries.add((business,job.get('channel','feishu'),job['target']))
                manifest=self._manifest(owner,business)
                if not self._fresh_manifest(owner,manifest):
                    # Never regenerate a potentially delivered report under a
                    # new operation to evade reconciliation.
                    relevant=self.service.outbox.business_status(owner,business)
                    if any(r['status'] in ('sending','uncertain','sent') for r in relevant):continue
                    state=self._claim_generation(owner,business,binding['subject'],now)
                    if state is None:continue
                    try:
                        result=await self.reports.prepare(external_id=external,kind=job['kind'],day=day.isoformat(),operation_id=business+':generation:'+str(state['attempts']))
                        self._finish_generation(owner,state,True);counts['prepared']+=1
                        manifest=self._manifest(owner,business)
                    except Exception:
                        self._finish_generation(owner,state,False);counts['failures']+=1;continue
                result=dict(manifest['guidance'],report={k:manifest[k] for k in ('kind','date','business_id','prepare_at','deliver_at','timezone','run_id')})
                try:await self.reports.prepare_delivery(external_id=external,result=result,channel=job.get('channel','feishu'),target=job['target'])
                except (ScopeError,EvidenceError,RevisionConflict,LeaseConflict):counts['failures']+=1
        delivery_rows={row['id']:row for business,channel,target in allowed_deliveries
                       for row in self.service.outbox.business_status(owner,business)
                       if row['channel']=='feishu' and row['channel']==channel and row['target']==target}
        for row in delivery_rows.values():
            if row['status'] not in ('pending','rejected') or datetime.fromisoformat(row['due'])>now:continue
            try:
                receipt=await self.delivery.deliver(owner=owner,outbox_id=row['id'],now=now)
                counts['sent']+=receipt['status']=='sent'
            except (ScopeError,EvidenceError,RevisionConflict,LeaseConflict):counts['failures']+=1
        return counts


def main(argv=None):
    parser=argparse.ArgumentParser(description='PostgreSQL Core定时报表；仅可信配置可启用真实投递')
    parser.add_argument('--owner',default=os.environ.get('MINGJING_OWNER_ID'))
    parser.add_argument('--dry-run',action='store_true',help='只读取配置与队列状态，不生成或发送')
    args=parser.parse_args(argv)
    if not args.owner:parser.error('需要明确--owner')
    from mingjing_core.application.consultation import ConsultationService
    service=ConsultationService.from_base()
    try:
        if args.dry_run:
            settings=service.repo.assert_scope(args.owner)['settings'].get('report_pipeline',{})
            result={'enabled':bool(settings.get('enabled')),'configured_jobs':len(settings.get('jobs',[])),'queue':service.outbox.status(args.owner)}
        else:
            from .channels.feishu import FeishuTransport
            result=asyncio.run(CoreReportWorker(service,FeishuTransport()).tick(args.owner))
        print(json.dumps(result,ensure_ascii=False,default=str))
    finally:service.repo.close()


if __name__=='__main__':main()
