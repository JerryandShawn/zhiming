"""PostgreSQL outbox with scoped dependency checks and explicit reconciliation."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import uuid

from psycopg import sql
from psycopg.types.json import Jsonb
from mingjing_core.timekit.clock import get_clock
from mingjing_core.domain.contracts import ScopeError, RevisionConflict, LeaseConflict, EvidenceError
from .channels.hermes import validated_payload
from .delivery_origin import assert_delivery_origin
from .tarot import fingerprint, IdempotencyConflict


class DeliveryUncertain(LeaseConflict):
    code = 'DELIVERY_UNCERTAIN'


class OutboxService:
    def __init__(self, repo, *, max_attempts=3, lease_seconds=120):
        self.repo=repo
        self.max_attempts=max(1,min(int(max_attempts),10))
        self.lease_seconds=max(30,min(int(lease_seconds),600))

    def _row(self,conn,owner,ident,lock=False):
        row=conn.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND id=%s').format(self.repo.table('delivery_outbox'))+(sql.SQL(' FOR UPDATE') if lock else sql.SQL('')), (owner,ident)).fetchone()
        if not row:raise ScopeError('投递记录不存在或无权访问')
        self.repo.assert_scope(owner,row['subject'])
        return row

    def _view(self,row,include_payload=False):
        hidden=('payload',) if include_payload else ('payload','claim_token')
        result={k:v.isoformat() if isinstance(v,datetime) else deepcopy(v) for k,v in row.items() if k not in hidden}
        result['transport_id']=fingerprint(['core3-delivery',row['owner'],row['business_id'],row['channel'],row['target']])[:40]
        result['content_hash']=fingerprint(row['payload'])
        if include_payload:result['payload']=deepcopy(row['payload'])
        return result

    def _target(self,owner,subject,channel,target):
        binding=self.repo.resolve_channel(channel,target)
        if binding['owner']!=owner or binding['subject']!=subject:raise ScopeError('投递目标未绑定当前用户和人物')
        if target.startswith('oc_') and binding.get('binding_kind')!='chat':raise ScopeError('群聊目标须有显式 chat 绑定')
        return binding

    def _fresh(self,owner,run):
        subject=run.get('subject_id',run.get('subject','self'))
        self.repo.assert_scope(owner,subject)
        if run.get('owner_user_id',run.get('owner'))!=owner:raise ScopeError('执行记录归属不符')
        if run.get('status') not in ('succeeded','complete','completed','validated','success'):raise RevisionConflict('报告执行已过时或尚未成功')
        result=validated_payload(run.get('result'))
        if result['meta']['core_run']['run_id']!=run['id']:
            raise EvidenceError('结果与权威执行不一致')
        if result['meta'].get('subject_id',subject)!=subject:
            raise ScopeError('结果人物与执行不一致')
        dependencies=run.get('dependencies',run.get('state_version',{}))
        request=run.get('request',{})
        cases=request.get('case_ids') or result.get('meta',{}).get('case_ids') or []
        self.repo.versions(owner,subject,cases)
        if not dependencies or not self.repo.verify_versions(owner,dependencies):raise RevisionConflict('资料依赖已更新，旧报告不能投递')
        return subject,dependencies,result

    def prepare_delivery(self,*,owner,run_id,business_id,channel,target,due=None,replace_stale=False):
        if not all(isinstance(v,str) and v.strip() and len(v)<=250 for v in (run_id,business_id,channel,target)):
            raise ValueError('投递标识或目标无效')
        if isinstance(due,str):due=datetime.fromisoformat(due)
        due=due or get_clock().now()
        if due.tzinfo is None:raise ValueError('投递时间须含时区')
        with self.repo.transaction(owner) as conn:
            run=self.repo.fetch_run(owner,run_id)
            subject,dependencies,result=self._fresh(owner,run)
            assert_delivery_origin(self.repo,owner,run,business_id=business_id,channel=channel,target=target)
            self._target(owner,subject,channel,target)
            ambiguous=conn.execute(sql.SQL("SELECT id FROM {} WHERE owner=%s AND run_id=%s AND status IN ('sending','uncertain') FOR UPDATE").format(self.repo.table('delivery_outbox')), (owner,run_id)).fetchone()
            if ambiguous:raise DeliveryUncertain('同一执行送达不明，不能更换业务编号或目标重发')
            other_target=conn.execute(sql.SQL('SELECT id FROM {} WHERE owner=%s AND business_id=%s AND channel=%s AND target<>%s FOR UPDATE').format(self.repo.table('delivery_outbox')), (owner,business_id,channel,target)).fetchone()
            if other_target:raise IdempotencyConflict('同一业务的投递目标已经固定')
            existing=conn.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND business_id=%s AND channel=%s AND target=%s FOR UPDATE').format(self.repo.table('delivery_outbox')), (owner,business_id,channel,target)).fetchone()
            if existing:
                if existing['run_id']==run_id and fingerprint(existing['payload'])==fingerprint(result):return self._view(existing)
                legacy=not existing['payload'] and str(existing['run_id'] or '').startswith('legacy:')
                proof=existing.get('reconciliation') or {}
                confirmed_unsent=legacy and proof.get('delivered') is False and bool(proof.get('evidence_ref'))
                eligible=(existing['status']=='stale' and not existing['attempts']) or (confirmed_unsent and existing['status'] in ('stale','rejected') and existing['attempts']<self.max_attempts)
                if not replace_stale or not eligible:
                    raise IdempotencyConflict('同一投递业务不能更换正文；已发送或结果不明的记录不得重建')
                # Old unsent rows carry the original schedule, not an accepted
                # interpretation. Replacement uses a new validated Core run;
                # it never shifts that original due time to obtain a new slot.
                if legacy:due=existing['due']
                reconciliation=proof if confirmed_unsent else {} if legacy else proof
                conn.execute(sql.SQL("UPDATE {} SET run_id=%s,payload=%s,dependencies=%s,status='pending',due=%s,error='',reconciliation=%s,claim_token=NULL,lease_until=NULL,updated_at=now() WHERE id=%s").format(self.repo.table('delivery_outbox')), (run_id,Jsonb(result),Jsonb(dependencies),due,Jsonb(reconciliation),existing['id']))
                return self._view(self._row(conn,owner,existing['id']))
            ident=uuid.uuid4().hex
            conn.execute(sql.SQL('INSERT INTO {}(id,owner,subject,business_id,channel,target,run_id,payload,dependencies,due) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)').format(self.repo.table('delivery_outbox')), (ident,owner,subject,business_id,channel,target,run_id,Jsonb(result),Jsonb(dependencies),due))
            return self._view(self._row(conn,owner,ident))

    def claim_delivery(self,*,owner,outbox_id,now=None):
        now=now or get_clock().now()
        failure=None;claim=None
        with self.repo.transaction(owner) as conn:
            row=self._row(conn,owner,outbox_id,True)
            if row['status'] in ('sending','uncertain'):raise DeliveryUncertain('DELIVERY_UNCERTAIN：须先对账，不能盲目重发')
            if row['status'] not in ('pending','rejected'):raise LeaseConflict('本记录不能再次领取')
            if row['attempts']>=self.max_attempts:raise LeaseConflict('已达到明确失败的重试上限')
            if row['due']>now:raise LeaseConflict('尚未到原定投递时间')
            if now-row['due']>timedelta(hours=12):
                conn.execute(sql.SQL("UPDATE {} SET status='expired',error='已超过投递时段',updated_at=now() WHERE id=%s").format(self.repo.table('delivery_outbox')), (outbox_id,))
                failure=LeaseConflict('已超过投递时段')
            else:
                try:
                    run=self.repo.fetch_run(owner,row['run_id'])
                    subject,dependencies,result=self._fresh(owner,run)
                    assert_delivery_origin(self.repo,owner,run,business_id=row['business_id'],
                                           channel=row['channel'],target=row['target'])
                    self._target(owner,subject,row['channel'],row['target'])
                    if row['dependencies']!=dependencies or fingerprint(row['payload'])!=fingerprint(result):raise RevisionConflict('已归档正文或依赖不一致')
                except (RevisionConflict,ScopeError,EvidenceError) as exc:
                    conn.execute(sql.SQL("UPDATE {} SET status='stale',error=%s,updated_at=now() WHERE id=%s").format(self.repo.table('delivery_outbox')), (exc.code,outbox_id))
                    failure=exc
                if failure is None:
                    token=uuid.uuid4().hex
                    conn.execute(sql.SQL("UPDATE {} SET status='sending',attempts=attempts+1,claim_token=%s,lease_until=%s,updated_at=now() WHERE id=%s").format(self.repo.table('delivery_outbox')), (token,now+timedelta(seconds=self.lease_seconds),outbox_id))
                    claim=self._view(self._row(conn,owner,outbox_id),True)
        if failure:raise failure
        return claim

    def record_delivery(self,*,owner,outbox_id,status,message_id=None,error='',claim_token=None):
        if status not in ('sent','uncertain','rejected'):raise ValueError('投递回执状态无效')
        if status=='sent' and (not isinstance(message_id,str) or not message_id.strip()):raise EvidenceError('送达必须有外部消息 ID')
        with self.repo.transaction(owner) as conn:
            row=self._row(conn,owner,outbox_id,True)
            if row['status']=='sent':return self._view(row)
            if row['status']!='sending' or not claim_token or row['claim_token']!=claim_token:raise LeaseConflict('过期或未授权的投递回执')
            conn.execute(sql.SQL('UPDATE {} SET status=%s,receipt=%s,error=%s,lease_until=NULL,updated_at=now() WHERE id=%s').format(self.repo.table('delivery_outbox')), (status,message_id or '',str(error)[:500],outbox_id))
            return self._view(self._row(conn,owner,outbox_id))

    def recover_claims(self,owner,now=None):
        now=now or get_clock().now()
        with self.repo.transaction(owner) as conn:
            cursor=conn.execute(sql.SQL("UPDATE {} SET status='uncertain',error='DELIVERY_UNCERTAIN：worker中断，须对账',updated_at=now() WHERE owner=%s AND status='sending' AND lease_until<%s").format(self.repo.table('delivery_outbox')), (owner,now))
            return cursor.rowcount

    def reconcile_delivery(self,*,owner,outbox_id,delivered,message_id=None,evidence_ref=None):
        if type(delivered) is not bool or not isinstance(evidence_ref,str) or not evidence_ref.strip():raise EvidenceError('对账须明确结果并提供核验记录标识')
        if delivered and (not isinstance(message_id,str) or not message_id.strip()):raise EvidenceError('确认已送达须提供真实外部消息 ID')
        with self.repo.transaction(owner) as conn:
            row=self._row(conn,owner,outbox_id,True)
            if row['status'] not in ('uncertain','sending'):raise LeaseConflict('只有送达不明记录需要对账')
            status='sent' if delivered else 'rejected'
            proof={'delivered':delivered,'evidence_ref':evidence_ref[:500],'message_id':message_id,'verified_at':get_clock().now().isoformat()}
            conn.execute(sql.SQL("UPDATE {} SET status=%s,receipt=%s,error='',reconciliation=%s,claim_token=NULL,lease_until=NULL,updated_at=now() WHERE id=%s").format(self.repo.table('delivery_outbox')), (status,message_id or '',Jsonb(proof),outbox_id))
            return self._view(self._row(conn,owner,outbox_id))

    def invalidate_pending(self,owner):
        # Scope-specific checks preserve unrelated cases, subjects and purely
        # stylistic preference changes; only changed dependencies become stale.
        count=0
        with self.repo.transaction(owner) as conn:
            rows=conn.execute(sql.SQL("SELECT * FROM {} WHERE owner=%s AND status IN ('pending','rejected') FOR UPDATE").format(self.repo.table('delivery_outbox')), (owner,)).fetchall()
            for row in rows:
                try:
                    run=self.repo.fetch_run(owner,row['run_id']);self._fresh(owner,run)
                    self._target(owner,row['subject'],row['channel'],row['target'])
                except (RevisionConflict,ScopeError,EvidenceError,KeyError):
                    conn.execute(sql.SQL("UPDATE {} SET status='stale',error='STALE_INPUT',updated_at=now() WHERE id=%s").format(self.repo.table('delivery_outbox')), (row['id'],));count+=1
        return count

    def status(self,owner):
        with self.repo.connection() as conn:
            rows=conn.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s ORDER BY due DESC LIMIT 120').format(self.repo.table('delivery_outbox')), (owner,)).fetchall()
            return {'enabled':True,'timezone':'Asia/Shanghai','prepare_minutes':15,'rows':[self._view(r) for r in rows]}

    def business_status(self,owner,business_id):
        """Safety lookup is independent of the bounded user-facing list."""
        with self.repo.connection() as conn:
            rows=conn.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND business_id=%s ORDER BY due').format(self.repo.table('delivery_outbox')),(owner,business_id)).fetchall()
            return [self._view(row) for row in rows]


DeliveryService=OutboxService
