"""PostgreSQL owner-scoped tarot effects; models never shuffle or change cards."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import secrets
import uuid

from psycopg import sql
from psycopg.types.json import Jsonb
from mingjing_core.timekit.clock import get_clock
from hermes.tarot_deck import CARDS, CARD_BY_ID, SPREADS, DECK_VERSION, MEANING_VERSION, METHOD_VERSION, card


class IdempotencyConflict(ValueError):
    code = 'IDEMPOTENCY_CONFLICT'
    http_status = 409


def _text(value, name, limit=2000, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError(name + '无效')
    return value.strip()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _stamp():
    return get_clock().now().isoformat()


class TarotService:
    def __init__(self, repo, *, randbelow=None):
        self.repo = repo
        self._randbelow = randbelow or secrets.randbelow

    def _row(self, conn, owner, draw_id, lock=False):
        suffix = sql.SQL(' FOR UPDATE') if lock else sql.SQL('')
        row = conn.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND id=%s').format(self.repo.table('tarot_draws')) + suffix, (owner, draw_id)).fetchone()
        if not row:
            raise KeyError('牌阵不存在或无权访问')
        self.repo.assert_scope(owner, row['subject'])
        return row

    def _request(self, conn, owner, operation, key, payload=None):
        _text(key, '请求标识', 160)
        row = conn.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND operation=%s AND request_key=%s').format(self.repo.table('tarot_requests')), (owner, operation, key)).fetchone()
        if row and row['deleted']:
            raise IdempotencyConflict('该请求已删除或背景已撤销，请明确建立新请求')
        if row and payload is not None and row['fingerprint'] != fingerprint(payload):
            raise IdempotencyConflict('同一请求标识不能用于不同内容')
        return row

    def _save_request(self, conn, owner, operation, key, payload, ident, kind='draw'):
        conn.execute(sql.SQL('INSERT INTO {}(owner,operation,request_key,fingerprint,result_id,result_type) VALUES(%s,%s,%s,%s,%s,%s)').format(self.repo.table('tarot_requests')), (owner, operation, key, fingerprint(payload), ident, kind))

    def _viewer(self, row):
        result = deepcopy(row['payload'])
        private = row['private_deck']
        cards = []
        for selected in result.pop('selected', []):
            visible = {key:selected[key] for key in ('position', 'label', 'back_id', 'revealed')}
            if selected['revealed']:
                visible.update(card_id=selected['card_id'], orientation=selected['orientation'], card=deepcopy(selected['card_snapshot']))
            cards.append(visible)
        selected_ids = {c['back_id'] for c in cards}
        result.update(id=row['id'], subject_id=row['subject'], case_id=row['case_id'], stage=row['stage'], cards=cards,
                      backs=[{'back_id':c['back_id'], 'selected':c['back_id'] in selected_ids} for c in private] if result['draw_source']=='pick' else [],
                      required_cards=len(result['spread']['positions']), selected_count=len(cards), revealed_count=sum(c['revealed'] for c in cards),
                      context_revoked=bool(result.get('context_snapshot', {}).get('context_revoked')))
        return result

    def _update(self, conn, row, payload):
        payload = dict(payload, updated_at=_stamp())
        conn.execute(sql.SQL('UPDATE {} SET payload=%s,updated_at=now() WHERE owner=%s AND id=%s').format(self.repo.table('tarot_draws')), (Jsonb(payload), row['owner'], row['id']))
        self.repo.bump_revision(conn, row['owner'], case_id=row['case_id'])
        return self._viewer(self._row(conn, row['owner'], row['id']))

    def _shuffle(self, reversals):
        ids = [c['card_id'] for c in CARDS]
        for i in range(len(ids)-1, 0, -1):
            j = self._randbelow(i+1)
            if type(j) is not int or not 0 <= j <= i:
                raise ValueError('随机来源返回越界值')
            ids[i], ids[j] = ids[j], ids[i]
        output = []
        for ident in ids:
            direction = self._randbelow(2) if reversals else 0
            if type(direction) is not int or direction not in (0,1):
                raise ValueError('随机方向无效')
            output.append({'back_id':secrets.token_urlsafe(18), 'card_id':ident, 'orientation':'reversed' if direction else 'upright', 'card_snapshot':card(ident)})
        return output

    def _manual(self, cards, count, reversals):
        if not isinstance(cards, list) or len(cards) != count:
            raise ValueError('手动牌数与牌阵不符')
        output = []
        seen = set()
        for item in cards:
            if not isinstance(item, dict) or item.get('card_id') not in CARD_BY_ID:
                raise ValueError('手动牌不存在')
            ident = item['card_id']; direction = item.get('orientation', 'upright')
            if ident in seen or direction not in ('upright','reversed') or (not reversals and direction!='upright'):
                raise ValueError('牌面重复或方向与正逆位设置不符')
            seen.add(ident)
            output.append({'back_id':secrets.token_urlsafe(18), 'card_id':ident, 'orientation':direction, 'card_snapshot':card(ident)})
        return output

    def create_draw(self, owner, *, subject_id, case_id, question, spread_id='reflect3', draw_source='auto', reversals=True,
                    options=None, context_snapshot=None, stage='open', idempotency_key, explicit_new=False, previous_draw_id=None, manual_cards=None):
        _text(owner,'身份',160); _text(subject_id,'人物',160); _text(case_id,'事项',160)
        question = _text(question,'问题'); stage = _text(stage,'阶段',120)
        if spread_id not in SPREADS or draw_source not in ('auto','pick','manual'):
            raise ValueError('未知牌阵或抽牌方式')
        if type(reversals) is not bool or type(explicit_new) is not bool:
            raise ValueError('开关格式无效')
        options = deepcopy(options or {}); snapshot = deepcopy(context_snapshot or {})
        if not isinstance(options,dict) or not isinstance(snapshot,dict) or len(json.dumps(snapshot))>80000:
            raise ValueError('背景或选项过长或无效')
        if spread_id=='choice5':
            options['A'] = _text(options.get('A'),'A选项',1200); options['B'] = _text(options.get('B'),'B选项',1200)
            if options['A']==options['B']: raise ValueError('请区分 A 与 B 的实际含义')
        if draw_source!='manual' and manual_cards is not None:
            raise ValueError('只有手动模式可以指定牌面')
        # Server revision can advance between retries; client intent is frozen
        # independently on EACH request, including requests reusing older draws.
        intent = {'subject_id':subject_id,'case_id':case_id,'stage':stage,'question':question,'spread_id':spread_id,'draw_source':draw_source,
                  'reversals':reversals,'options':options,'explicit_new':explicit_new,'previous_draw_id':previous_draw_id,'manual_cards':manual_cards,
                  'background':snapshot.get('background',''),'client_request_hash':snapshot.get('client_request_hash')}
        self.repo.ensure_owner(owner)
        with self.repo.transaction(owner) as conn:
            self.repo.assert_scope(owner,subject_id)
            case = self.repo.get(owner,'case',case_id)
            if case.get('subject',case.get('subject_id','self'))!=subject_id or case['status']=='deleted':
                raise ValueError('事项与人物范围不符')
            request = self._request(conn,owner,'create',idempotency_key,intent)
            if request:
                return {'draw':self._viewer(self._row(conn,owner,request['result_id'])),'created':False,'reused':False}
            prior = conn.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND subject=%s AND case_id=%s AND stage=%s ORDER BY created_at DESC,id DESC LIMIT 1').format(self.repo.table('tarot_draws')), (owner,subject_id,case_id,stage)).fetchone()
            if prior and not explicit_new:
                self._save_request(conn,owner,'create',idempotency_key,intent,prior['id'])
                return {'draw':self._viewer(prior),'created':False,'reused':True}
            if previous_draw_id:
                old = self._row(conn,owner,previous_draw_id)
                if old['subject']!=subject_id or old['case_id']!=case_id:raise ValueError('关联牌阵须属于同一人物与事项')
            elif prior:
                previous_draw_id=prior['id']
            spread=deepcopy(SPREADS[spread_id]); count=len(spread['positions'])
            private=self._manual(manual_cards,count,reversals) if draw_source=='manual' else self._shuffle(reversals)
            ident=uuid.uuid4().hex; stamp=_stamp()
            payload={'question':question,'options':options,'context_snapshot':snapshot,'spread_id':spread_id,'spread':spread,
                     'deck_version':DECK_VERSION,'meaning_version':MEANING_VERSION,'method_version':METHOD_VERSION if draw_source!='manual' else 'manual-entry-v1',
                     'draw_source':draw_source,'reversals':reversals,'status':'selecting' if draw_source=='pick' else 'pending_reveal',
                     'selected':[] if draw_source=='pick' else [dict(c,position=i+1,label=spread['positions'][i],revealed=False) for i,c in enumerate(private[:count])],
                     'revision':1,'revision_root':ident,'previous_draw_id':previous_draw_id,'correction_reason':'','created_at':stamp,'updated_at':stamp}
            conn.execute(sql.SQL('INSERT INTO {}(id,owner,subject,case_id,stage,payload,private_deck) VALUES(%s,%s,%s,%s,%s,%s,%s)').format(self.repo.table('tarot_draws')), (ident,owner,subject_id,case_id,stage,Jsonb(payload),Jsonb(private)))
            self._save_request(conn,owner,'create',idempotency_key,intent,ident)
            self.repo.bump_revision(conn,owner,case_id=case_id)
            return {'draw':self._viewer(self._row(conn,owner,ident)),'created':True,'reused':False}

    def get(self,owner,draw_id):
        with self.repo.connection() as conn:return self._viewer(self._row(conn,owner,draw_id))

    def list_draws(self,owner,subject_id=None,case_id=None,limit=50):
        self.repo.assert_scope(owner,subject_id or 'self')
        filters=[sql.SQL('owner=%s')]; args=[owner]
        if subject_id is not None:filters.append(sql.SQL('subject=%s'));args.append(subject_id)
        if case_id is not None:filters.append(sql.SQL('case_id=%s'));args.append(case_id)
        args.append(max(1,min(int(limit),200)))
        with self.repo.connection() as conn:
            rows=conn.execute(sql.SQL('SELECT * FROM {} WHERE {} ORDER BY created_at DESC,id DESC LIMIT %s').format(self.repo.table('tarot_draws'),sql.SQL(' AND ').join(filters)),args).fetchall()
            return [self._viewer(r) for r in rows]

    def preferences(self,owner):
        rows=self.list_draws(owner,limit=1)
        return {'reversals':rows[0]['reversals'] if rows else True}

    def request_result(self,owner,operation,key,client_fingerprint=None):
        with self.repo.connection() as conn:
            row=self._request(conn,owner,operation,key)
            if not row:return None
            if client_fingerprint and client_fingerprint!=row['fingerprint']:
                raise IdempotencyConflict('同一请求标识不能用于不同内容')
            if row['result_type']=='reading':return {'reading':self.get_reading(owner,row['result_id']),'created':False}
            draw=self._viewer(self._row(conn,owner,row['result_id']))
            return {'draw':draw,'created':False,'reused':False} if operation=='create' else draw

    def select(self,owner,draw_id,back_id,idempotency_key):
        intent={'draw_id':draw_id,'back_id':back_id}
        with self.repo.transaction(owner) as conn:
            row=self._row(conn,owner,draw_id,True); p=deepcopy(row['payload'])
            request=self._request(conn,owner,'select',idempotency_key,intent)
            if request:return self._viewer(row)
            if p['draw_source']!='pick' or p['status']=='cancelled':raise ValueError('此牌阵现在不能选牌')
            if not any(c['back_id']==back_id for c in p['selected']):
                if len(p['selected'])>=len(p['spread']['positions']):raise ValueError('此牌阵已经选满')
                entry=next((c for c in row['private_deck'] if c['back_id']==back_id),None)
                if entry is None:raise ValueError('牌背不属于本次洗牌')
                i=len(p['selected']);p['selected'].append(dict(entry,position=i+1,label=p['spread']['positions'][i],revealed=False))
                p['status']='pending_reveal' if len(p['selected'])==len(p['spread']['positions']) else 'selecting'
            self._save_request(conn,owner,'select',idempotency_key,intent,draw_id)
            return self._update(conn,row,p)

    def reveal(self,owner,draw_id,position=None):
        with self.repo.transaction(owner) as conn:
            row=self._row(conn,owner,draw_id,True);p=deepcopy(row['payload'])
            if p['status']=='cancelled' or not p['selected']:raise ValueError('请先选牌，取消的牌阵不能继续翻牌')
            if position is not None and (type(position) is not int or not 1<=position<=len(p['selected'])):raise ValueError('牌位未选择或不存在')
            for c in p['selected']:
                if position is None or c['position']==position:c['revealed']=True
            if len(p['selected'])==len(p['spread']['positions']) and all(c['revealed'] for c in p['selected']):p['status']='ready'
            return self._update(conn,row,p)

    def cancel(self,owner,draw_id):
        with self.repo.transaction(owner) as conn:
            row=self._row(conn,owner,draw_id,True);p=dict(row['payload'],status='cancelled')
            conn.execute(sql.SQL("UPDATE {} SET payload=payload||%s WHERE owner=%s AND draw_id=%s AND payload->>'status'='running'").format(self.repo.table('tarot_readings')), (Jsonb({'status':'failed','error':'牌阵已取消','updated_at':_stamp()}),owner,draw_id))
            return self._update(conn,row,p)

    def revise_manual(self,owner,draw_id,cards,reason,idempotency_key):
        reason=_text(reason,'更正说明',800);intent={'draw_id':draw_id,'cards':cards,'reason':reason}
        with self.repo.transaction(owner) as conn:
            request=self._request(conn,owner,'revise',idempotency_key,intent)
            if request:return self._viewer(self._row(conn,owner,request['result_id']))
            row=self._row(conn,owner,draw_id,True);p=deepcopy(row['payload'])
            if p['draw_source']!='manual':raise ValueError('仅实体牌录入允许修订牌面')
            private=self._manual(cards,len(p['spread']['positions']),p['reversals'])
            revision=conn.execute(sql.SQL("SELECT max((payload->>'revision')::int) AS version FROM {} WHERE owner=%s AND payload->>'revision_root'=%s").format(self.repo.table('tarot_draws')), (owner,p['revision_root'])).fetchone()['version']+1
            ident=uuid.uuid4().hex;stamp=_stamp()
            p.update(selected=[dict(c,position=i+1,label=p['spread']['positions'][i],revealed=False) for i,c in enumerate(private)],revision=revision,status='pending_reveal',previous_draw_id=draw_id,correction_reason=reason,created_at=stamp,updated_at=stamp)
            conn.execute(sql.SQL('INSERT INTO {}(id,owner,subject,case_id,stage,payload,private_deck) VALUES(%s,%s,%s,%s,%s,%s,%s)').format(self.repo.table('tarot_draws')), (ident,owner,row['subject'],row['case_id'],row['stage'],Jsonb(p),Jsonb(private)))
            self._save_request(conn,owner,'revise',idempotency_key,intent,ident)
            self.repo.bump_revision(conn,owner,case_id=row['case_id'])
            return self._viewer(self._row(conn,owner,ident))

    def get_for_reading(self,owner,draw_id):
        draw=self.get(owner,draw_id)
        if draw['status']!='ready':raise ValueError('请完成翻牌，取消的牌阵不能解读')
        draw.pop('backs',None)
        return draw

    def begin_reading(self,owner,draw_id,*,model,prompt_version,context_snapshot,idempotency_key):
        _text(model,'模型',160);_text(prompt_version,'提示版本',160)
        intent={'draw_id':draw_id,'model':model,'prompt_version':prompt_version,'supplement':context_snapshot.get('supplement','')}
        with self.repo.transaction(owner) as conn:
            row=self._row(conn,owner,draw_id,True);request=self._request(conn,owner,'reading',idempotency_key,intent)
            if request:return {'reading':self.get_reading(owner,request['result_id']),'created':False}
            if row['payload']['status']!='ready':raise ValueError('请先完成翻牌')
            version=conn.execute(sql.SQL('SELECT coalesce(max(version),0)+1 AS version FROM {} WHERE draw_id=%s').format(self.repo.table('tarot_readings')), (draw_id,)).fetchone()['version']
            ident=uuid.uuid4().hex;stamp=_stamp()
            payload={'id':ident,'draw_id':draw_id,'version':version,'status':'running','model':model,'prompt_version':prompt_version,
                     'meaning_version':row['payload']['meaning_version'],'context_snapshot':deepcopy(context_snapshot),'result':None,'error':'','validation':{},'created_at':stamp,'updated_at':stamp}
            conn.execute(sql.SQL('INSERT INTO {}(id,owner,draw_id,version,payload) VALUES(%s,%s,%s,%s,%s)').format(self.repo.table('tarot_readings')), (ident,owner,draw_id,version,Jsonb(payload)))
            self._save_request(conn,owner,'reading',idempotency_key,intent,ident,'reading')
            return {'reading':payload,'created':True}

    def get_reading(self,owner,reading_id):
        with self.repo.connection() as conn:
            row=conn.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND id=%s').format(self.repo.table('tarot_readings')), (owner,reading_id)).fetchone()
            if not row:raise KeyError('解读不存在或无权访问')
            self._row(conn,owner,row['draw_id'])
            return deepcopy(row['payload'])

    def list_readings(self,owner,draw_id):
        with self.repo.connection() as conn:
            self._row(conn,owner,draw_id)
            rows=conn.execute(sql.SQL('SELECT payload FROM {} WHERE owner=%s AND draw_id=%s ORDER BY version').format(self.repo.table('tarot_readings')), (owner,draw_id)).fetchall()
            return [deepcopy(r['payload']) for r in rows]

    def resume_reading(self,owner,reading_id,run_id):
        """Resume the same saved reading after the same Core run is queued."""
        with self.repo.transaction(owner) as conn:
            row=conn.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND id=%s FOR UPDATE').format(self.repo.table('tarot_readings')), (owner,reading_id)).fetchone()
            if not row:raise KeyError('解读不存在或无权访问')
            run=self.repo.fetch_run(owner,run_id)
            if run['request'].get('reading_id')!=reading_id or run['request'].get('draw_id')!=row['draw_id'] or run['status'] not in ('queued','running'):
                raise ValueError('只有原Core执行已恢复时才能继续同一解释')
            self.get_for_reading(owner,row['draw_id']);p=deepcopy(row['payload'])
            if p['status']=='running':return p
            if p['status']=='success':raise ValueError('已经成功的解释不能重新领取')
            p.update(status='running',error='',updated_at=_stamp())
            conn.execute(sql.SQL('UPDATE {} SET payload=%s WHERE owner=%s AND id=%s').format(self.repo.table('tarot_readings')), (Jsonb(p),owner,reading_id))
            return p

    def finish_reading(self,owner,reading_id,*,result=None,validation=None,error=None):
        if error is None and (not isinstance(result,dict) or not isinstance(validation,dict)):raise ValueError('成功解读须有校验对象')
        with self.repo.transaction(owner) as conn:
            row=conn.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND id=%s FOR UPDATE').format(self.repo.table('tarot_readings')), (owner,reading_id)).fetchone()
            if not row:raise KeyError('解读不存在或无权访问')
            p=deepcopy(row['payload'])
            if p['status']!='running':return p
            draw=self._row(conn,owner,row['draw_id'])
            if draw['payload']['status']!='ready' and error is None:raise ValueError('原牌阵已结束或撤销')
            if error is None:
                from .channels.hermes import validated_payload
                validated_payload(result)
                run_id=result['meta']['core_run']['run_id'];run=self.repo.fetch_run(owner,run_id)
                if run['status']!='succeeded' or run.get('result')!=result or run['request'].get('draw_id')!=row['draw_id'] or run['request'].get('reading_id')!=reading_id:
                    raise ValueError('成功解释必须来自此reading关联的持久Core执行')
                if not self.repo.verify_versions(owner,run['dependencies']):raise ValueError('解释依赖已经改变，须恢复原执行后重新核对')
                validation=result['validation']
            p.update(status='failed' if error is not None else 'success',result=None if error is not None else result,
                     validation=validation or {},error=str(error)[:1500] if error is not None else '',updated_at=_stamp())
            if error is None:
                # core4 keeps authoritative source versions on the run rather
                # than copying private dependency metadata into its envelope.
                p['execution_snapshot']={
                    'run_id':run['id'],'revision':result['meta'].get('revision'),
                    'dependencies':deepcopy(run['dependencies'])}
            conn.execute(sql.SQL('UPDATE {} SET payload=%s WHERE owner=%s AND id=%s').format(self.repo.table('tarot_readings')), (Jsonb(p),owner,reading_id))
            return p

    def recover_running(self,owner,older_than_seconds=900):
        with self.repo.transaction(owner) as conn:
            result=conn.execute(sql.SQL("UPDATE {} SET payload=payload||%s WHERE owner=%s AND payload->>'status'='running' AND (payload->>'updated_at')::timestamptz < now()-(%s * interval '1 second')").format(self.repo.table('tarot_readings')), (Jsonb({'status':'failed','error':'上次解读中断，可沿用原牌重试','updated_at':_stamp()}),owner,max(0,int(older_than_seconds))))
            return result.rowcount

    def validate_cards(self,owner,draw_id,cards,deck_version):
        draw=self.get_for_reading(owner,draw_id)
        if deck_version!=draw['deck_version'] or not isinstance(cards,list) or len(cards)!=len(draw['cards']):raise ValueError('DRAW_MISMATCH')
        expected={c['position']:c for c in draw['cards']};seen=set()
        for c in cards:
            if not isinstance(c,dict) or type(c.get('position')) is not int or c['position'] in seen or c['position'] not in expected:raise ValueError('DRAW_MISMATCH')
            seen.add(c['position']);real=expected[c['position']]
            if c.get('card_id')!=real['card_id'] or c.get('orientation')!=real['orientation']:raise ValueError('DRAW_MISMATCH')
        return {'draw_id_checked':True,'owner_checked':True,'cards_checked':True,'deck_version_checked':True}

    def delete(self,owner,draw_id,include_revisions=True):
        from ..application.tarot import revoke_draw_dependencies,purge_committed_checkpoints
        nested=getattr(self.repo._local,'connection',None) is not None
        with self.repo.transaction(owner) as conn:
            row=self._row(conn,owner,draw_id,True)
            rows=conn.execute(sql.SQL("SELECT * FROM {} WHERE owner=%s AND payload->>'revision_root'=%s FOR UPDATE").format(self.repo.table('tarot_draws')), (owner,row['payload']['revision_root'])).fetchall() if include_revisions else [row]
            ids=[r['id'] for r in rows]
            readings=conn.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND draw_id=ANY(%s) FOR UPDATE').format(self.repo.table('tarot_readings')), (owner,ids)).fetchall()
            withdrawn=revoke_draw_dependencies(self.repo,conn,owner,rows,readings)
            results=ids+[r['id'] for r in readings]
            conn.execute(sql.SQL("UPDATE {} SET deleted=true,result_id='' WHERE owner=%s AND result_id=ANY(%s)").format(self.repo.table('tarot_requests')), (owner,results))
            conn.execute(sql.SQL('DELETE FROM {} WHERE owner=%s AND id=ANY(%s)').format(self.repo.table('tarot_draws')), (owner,ids))
            if withdrawn['source_ids']:self.purge_context(owner,withdrawn['fact_ids'],withdrawn['source_ids'])
            self.repo.bump_revision(conn,owner,case_id=row['case_id'])
            receipt={'deleted':True,'deleted_ids':ids,'affected_ids':withdrawn['affected_ids']}
        if not nested:purge_committed_checkpoints(self.repo,owner,receipt)
        return receipt

    def purge_context(self,owner,fact_ids,source_ids=None):
        targets=set(fact_ids or [])|set(source_ids or [])
        def matches(value):
            if isinstance(value,dict):return any(matches(k) or matches(v) for k,v in value.items())
            if isinstance(value,list):return any(matches(v) for v in value)
            return isinstance(value,str) and any(value==t or value.endswith(':'+t) for t in targets)
        affected=[];deleted=0
        if not targets:return {'draw_ids':affected,'readings_deleted':deleted}
        with self.repo.transaction(owner) as conn:
            for row in conn.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s FOR UPDATE').format(self.repo.table('tarot_draws')), (owner,)).fetchall():
                readings=conn.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND draw_id=%s').format(self.repo.table('tarot_readings')), (owner,row['id'])).fetchall()
                if not matches(row['payload'].get('context_snapshot',{})) and not any(matches(r['payload']) for r in readings):continue
                affected.append(row['id']);deleted+=len(readings)
                conn.execute(sql.SQL("UPDATE {} SET deleted=true,result_id='' WHERE owner=%s AND result_id=ANY(%s)").format(self.repo.table('tarot_requests')), (owner,[row['id']]+[r['id'] for r in readings]))
                conn.execute(sql.SQL('DELETE FROM {} WHERE owner=%s AND draw_id=%s').format(self.repo.table('tarot_readings')), (owner,row['id']))
                p=deepcopy(row['payload']);p['context_snapshot']={'context_revoked':True,'revoked_at':_stamp()}
                self._update(conn,row,p)
        return {'draw_ids':affected,'readings_deleted':deleted}


TarotDrawService = TarotService
