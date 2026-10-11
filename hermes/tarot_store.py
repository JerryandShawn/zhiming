"""Owner-scoped, durable tarot draws. Randomness never passes through an LLM.

Draws are immutable after selection, except visibility/cancellation flags.
Explicit manual corrections create revisions. Privacy erasure removes revisions,
readings and snapshots; content-free retry tombstones prevent resurrection.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import uuid
from tarot_deck import CARDS, CARD_BY_ID, SPREADS, DECK_VERSION, MEANING_VERSION, METHOD_VERSION, card

def _now(): return datetime.now(timezone.utc).isoformat(timespec='microseconds')
def _json(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def _hash(value): return hashlib.sha256(_json(value).encode()).hexdigest()
def _text(value,name,limit=2000,empty=False):
    if not isinstance(value,str) or len(value)>limit or (not empty and not value.strip()):raise ValueError(name+'无效')
    return value.strip()

class TarotDrawService:
    def __init__(self,base,*,randbelow=None):
        self.path=Path(base)/'tarot.db';self.path.parent.mkdir(parents=True,exist_ok=True)
        # Only tests instantiate an explicit dependency; runtime has no seed/env override.
        self._randbelow=randbelow or secrets.randbelow
        with self.db() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS tarot_draws(
              id TEXT PRIMARY KEY,owner TEXT NOT NULL,subject_id TEXT NOT NULL,case_id TEXT NOT NULL,
              stage TEXT NOT NULL,question TEXT NOT NULL,options_json TEXT NOT NULL,snapshot_json TEXT NOT NULL,
              spread_id TEXT NOT NULL,spread_json TEXT NOT NULL,deck_version TEXT NOT NULL,meaning_version TEXT NOT NULL,
              method_version TEXT NOT NULL,draw_source TEXT NOT NULL,reversals INTEGER NOT NULL,
              private_deck_json TEXT NOT NULL,selected_json TEXT NOT NULL,status TEXT NOT NULL,
              revision INTEGER NOT NULL,revision_root TEXT NOT NULL,previous_draw_id TEXT,
              correction_reason TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS tarot_case ON tarot_draws(owner,subject_id,case_id,stage,created_at);
            CREATE TABLE IF NOT EXISTS tarot_readings(
              id TEXT PRIMARY KEY,owner TEXT NOT NULL,draw_id TEXT NOT NULL,version INTEGER NOT NULL,
              status TEXT NOT NULL,model TEXT NOT NULL,prompt_version TEXT NOT NULL,meaning_version TEXT NOT NULL,
              context_json TEXT NOT NULL,result_json TEXT,error TEXT NOT NULL,validation_json TEXT NOT NULL,
              created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
              FOREIGN KEY(draw_id) REFERENCES tarot_draws(id) ON DELETE CASCADE,
              UNIQUE(draw_id,version));
            CREATE TABLE IF NOT EXISTS tarot_requests(
              owner TEXT NOT NULL,operation TEXT NOT NULL,request_key TEXT NOT NULL,payload_hash TEXT NOT NULL,
              draw_id TEXT NOT NULL,reading_id TEXT,PRIMARY KEY(owner,operation,request_key),
              FOREIGN KEY(draw_id) REFERENCES tarot_draws(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS tarot_deleted_requests(
              owner TEXT NOT NULL,operation TEXT NOT NULL,key_hash TEXT NOT NULL,
              PRIMARY KEY(owner,operation,key_hash));
            CREATE TABLE IF NOT EXISTS tarot_preferences(owner TEXT PRIMARY KEY,reversals INTEGER NOT NULL);
            ''')

    @contextmanager
    def db(self,write=False):
        c=sqlite3.connect(str(self.path),timeout=20);c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA secure_delete=ON')
        try:
            if write:c.execute('BEGIN IMMEDIATE')
            with c:yield c
        finally:c.close()

    def _row(self,c,owner,ident):
        _text(owner,'身份',160);_text(ident,'记录',160)
        row=c.execute('SELECT * FROM tarot_draws WHERE owner=? AND id=?',(owner,ident)).fetchone()
        if not row:raise KeyError('牌阵不存在或无权访问')
        return row

    def _request(self,c,owner,operation,key,payload):
        key=_text(key,'请求标识',160)
        if c.execute('SELECT 1 FROM tarot_deleted_requests WHERE owner=? AND operation=? AND key_hash=?',(owner,operation,_hash(key))).fetchone():
            raise ValueError('此请求对应记录已删除，请开始明确的新请求')
        row=c.execute('SELECT * FROM tarot_requests WHERE owner=? AND operation=? AND request_key=?',(owner,operation,key)).fetchone()
        if row and row['payload_hash']!=_hash(payload):raise ValueError('同一请求标识不能用于不同内容')
        return row

    def _save_request(self,c,owner,operation,key,payload,draw_id,reading_id=None):
        c.execute('INSERT INTO tarot_requests VALUES(?,?,?,?,?,?)',(owner,operation,key,_hash(payload),draw_id,reading_id))

    def request_result(self,owner,operation,key):
        """Recover an existing retry before assembling a newer context snapshot."""
        _text(owner,'身份',160);_text(key,'请求标识',160)
        if operation not in ('create','select','revise','reading'):raise ValueError('未知请求操作')
        with self.db() as c:
            if c.execute('SELECT 1 FROM tarot_deleted_requests WHERE owner=? AND operation=? AND key_hash=?',(owner,operation,_hash(key))).fetchone():
                raise ValueError('该请求已被删除或背景已撤销，请读取最新状态并使用新请求')
            req=c.execute('SELECT * FROM tarot_requests WHERE owner=? AND operation=? AND request_key=?',(owner,operation,key)).fetchone()
            if not req:return None
            if operation=='reading':
                row=c.execute('SELECT * FROM tarot_readings WHERE owner=? AND id=?',(owner,req['reading_id'])).fetchone()
                if not row:return None
                return {'reading':self._reading(row),'created':False}
            draw=self._viewer(self._row(c,owner,req['draw_id']))
            return {'draw':draw,'created':False,'reused':False} if operation=='create' else draw

    def _shuffle(self,reversals):
        ids=[c['card_id'] for c in CARDS]
        for i in range(len(ids)-1,0,-1):
            j=self._randbelow(i+1)
            if not isinstance(j,int) or not 0<=j<=i:raise ValueError('随机来源返回越界值')
            ids[i],ids[j]=ids[j],ids[i]
        result=[]
        for ident in ids:
            direction=self._randbelow(2) if reversals else 0
            if direction not in (0,1):raise ValueError('随机方向无效')
            result.append({'back_id':secrets.token_urlsafe(18),'card_id':ident,'orientation':'reversed' if direction else 'upright',
                           'card_snapshot':card(ident)})
        return result

    def _manual(self,cards,count,reversals):
        if not isinstance(cards,list) or len(cards)!=count:raise ValueError('手动牌数与牌阵不符')
        result=[];seen=set()
        for item in cards:
            if not isinstance(item,dict) or item.get('card_id') not in CARD_BY_ID:raise ValueError('手动牌不存在')
            ident=item['card_id'];direction=item.get('orientation','upright')
            if ident in seen:raise ValueError('同一次牌阵不能重复同一张牌')
            if direction not in ('upright','reversed') or not reversals and direction!='upright':raise ValueError('方向与正逆位设置不符')
            seen.add(ident);result.append({'back_id':secrets.token_urlsafe(18),'card_id':ident,'orientation':direction,'card_snapshot':card(ident)})
        return result

    def _viewer(self,row):
        selected=json.loads(row['selected_json']);private=json.loads(row['private_deck_json']);spread=json.loads(row['spread_json'])
        cards=[]
        for entry in selected:
            visible={k:entry[k] for k in ('position','label','back_id','revealed')}
            if entry['revealed']:
                visible.update(card_id=entry['card_id'],orientation=entry['orientation'],card=deepcopy(entry.get('card_snapshot') or card(entry['card_id'])))
            cards.append(visible)
        selected_ids={entry['back_id'] for entry in selected}
        backs=[{'back_id':x['back_id'],'selected':x['back_id'] in selected_ids} for x in private] if row['draw_source']=='pick' else []
        result={key:row[key] for key in ('id','subject_id','case_id','stage','question','spread_id','deck_version','meaning_version',
          'method_version','draw_source','status','revision','revision_root','previous_draw_id','correction_reason','created_at','updated_at')}
        result.update(options=json.loads(row['options_json']),context_snapshot=json.loads(row['snapshot_json']),spread=spread,
                      reversals=bool(row['reversals']),cards=cards,backs=backs,required_cards=len(spread['positions']),
                      selected_count=len(cards),revealed_count=sum(x['revealed'] for x in selected),
                      context_revoked=bool(json.loads(row['snapshot_json']).get('context_revoked')))
        return result

    def create_draw(self,owner,*,subject_id,case_id,question,spread_id='reflect3',draw_source='auto',reversals=True,
                    options=None,context_snapshot=None,stage='open',idempotency_key,explicit_new=False,previous_draw_id=None,manual_cards=None):
        owner=_text(owner,'身份',160);subject_id=_text(subject_id,'人物',160);case_id=_text(case_id,'事项',160)
        question=_text(question,'问题',2000);stage=_text(stage,'阶段',120)
        if spread_id not in SPREADS:raise ValueError('未知牌阵')
        if draw_source not in ('auto','pick','manual'):raise ValueError('未知抽牌方式')
        if type(reversals) is not bool or type(explicit_new) is not bool:raise ValueError('开关格式无效')
        options=deepcopy(options or {});snapshot=deepcopy(context_snapshot or {})
        if not isinstance(options,dict) or not isinstance(snapshot,dict) or len(_json(options))>8000 or len(_json(snapshot))>40000:raise ValueError('背景或选项过长或无效')
        if spread_id=='choice5':
            options['A']=_text(options.get('A'),'A选项',1200);options['B']=_text(options.get('B'),'B选项',1200)
            if options['A']==options['B']:raise ValueError('请区分 A 与 B 的实际含义')
        if draw_source!='manual' and manual_cards is not None:raise ValueError('只有手动模式可指定牌面')
        payload={'subject_id':subject_id,'case_id':case_id,'stage':stage,'question':question,'spread_id':spread_id,'draw_source':draw_source,
                 'reversals':reversals,'options':options,'context_snapshot':snapshot,'explicit_new':explicit_new,'previous_draw_id':previous_draw_id,'manual_cards':manual_cards}
        with self.db(True) as c:
            request=self._request(c,owner,'create',idempotency_key,payload)
            if request:return {'draw':self._viewer(self._row(c,owner,request['draw_id'])),'created':False,'reused':False}
            prior=c.execute('SELECT * FROM tarot_draws WHERE owner=? AND subject_id=? AND case_id=? AND stage=? ORDER BY created_at DESC LIMIT 1',
                            (owner,subject_id,case_id,stage)).fetchone()
            if prior and not explicit_new:
                self._save_request(c,owner,'create',idempotency_key,payload,prior['id'])
                return {'draw':self._viewer(prior),'created':False,'reused':True}
            if previous_draw_id:
                previous=self._row(c,owner,previous_draw_id)
                if previous['subject_id']!=subject_id or previous['case_id']!=case_id:raise ValueError('关联牌阵必须属于同一人物与事项')
            elif prior:previous_draw_id=prior['id']
            count=len(SPREADS[spread_id]['positions'])
            private=self._manual(manual_cards,count,reversals) if draw_source=='manual' else self._shuffle(reversals)
            selected=[] if draw_source=='pick' else [dict(x,position=i+1,label=SPREADS[spread_id]['positions'][i],revealed=False) for i,x in enumerate(private[:count])]
            ident=uuid.uuid4().hex;stamp=_now();status='selecting' if draw_source=='pick' else 'pending_reveal'
            values=(ident,owner,subject_id,case_id,stage,question,_json(options),_json(snapshot),spread_id,_json(SPREADS[spread_id]),
                    DECK_VERSION,MEANING_VERSION,METHOD_VERSION if draw_source!='manual' else 'manual-entry-v1',draw_source,int(reversals),
                    _json(private),_json(selected),status,1,ident,previous_draw_id,'',stamp,stamp)
            c.execute('INSERT INTO tarot_draws VALUES('+','.join('?' for _ in values)+')',values)
            c.execute('INSERT INTO tarot_preferences VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET reversals=excluded.reversals',(owner,int(reversals)))
            self._save_request(c,owner,'create',idempotency_key,payload,ident)
            return {'draw':self._viewer(self._row(c,owner,ident)),'created':True,'reused':False}

    def preferences(self,owner):
        with self.db() as c:row=c.execute('SELECT reversals FROM tarot_preferences WHERE owner=?',(owner,)).fetchone()
        return {'reversals':bool(row[0]) if row else True}

    def get(self,owner,draw_id):
        with self.db() as c:return self._viewer(self._row(c,owner,draw_id))

    def list_draws(self,owner,subject_id=None,case_id=None,limit=50):
        _text(owner,'身份',160);sql='SELECT * FROM tarot_draws WHERE owner=?';args=[owner]
        if subject_id is not None:sql+=' AND subject_id=?';args.append(subject_id)
        if case_id is not None:sql+=' AND case_id=?';args.append(case_id)
        sql+=' ORDER BY created_at DESC LIMIT ?';args.append(max(1,min(int(limit),200)))
        with self.db() as c:return [self._viewer(r) for r in c.execute(sql,args)]

    def select(self,owner,draw_id,back_id,idempotency_key):
        payload={'draw_id':draw_id,'back_id':back_id}
        with self.db(True) as c:
            row=self._row(c,owner,draw_id);request=self._request(c,owner,'select',idempotency_key,payload)
            if request:return self._viewer(row)
            if row['draw_source']!='pick' or row['status']=='cancelled':raise ValueError('此牌阵现在不能选牌')
            selected=json.loads(row['selected_json']);spread=json.loads(row['spread_json'])
            existing=next((x for x in selected if x['back_id']==back_id),None)
            if not existing:
                if len(selected)>=len(spread['positions']):raise ValueError('此牌阵已选满，请使用原结果')
                entry=next((x for x in json.loads(row['private_deck_json']) if x['back_id']==back_id),None)
                if entry is None:raise ValueError('牌背不属于本次洗牌')
                selected.append(dict(entry,position=len(selected)+1,label=spread['positions'][len(selected)],revealed=False))
                status='pending_reveal' if len(selected)==len(spread['positions']) else 'selecting'
                c.execute('UPDATE tarot_draws SET selected_json=?,status=?,updated_at=? WHERE id=?',(_json(selected),status,_now(),draw_id))
            self._save_request(c,owner,'select',idempotency_key,payload,draw_id)
            return self._viewer(self._row(c,owner,draw_id))

    def reveal(self,owner,draw_id,position=None):
        with self.db(True) as c:
            row=self._row(c,owner,draw_id)
            if row['status']=='cancelled':raise ValueError('已取消牌阵不能继续翻牌')
            selected=json.loads(row['selected_json']);count=len(json.loads(row['spread_json'])['positions'])
            if position is not None and (type(position) is not int or position<1 or position>len(selected)):raise ValueError('牌位未选择或不存在')
            if not selected:raise ValueError('请先选牌')
            for x in selected:
                if position is None or x['position']==position:x['revealed']=True
            status='ready' if len(selected)==count and all(x['revealed'] for x in selected) else row['status']
            c.execute('UPDATE tarot_draws SET selected_json=?,status=?,updated_at=? WHERE id=?',(_json(selected),status,_now(),draw_id))
            return self._viewer(self._row(c,owner,draw_id))

    def cancel(self,owner,draw_id):
        with self.db(True) as c:
            self._row(c,owner,draw_id)
            c.execute("UPDATE tarot_draws SET status='cancelled',updated_at=? WHERE id=?",(_now(),draw_id))
            c.execute("UPDATE tarot_readings SET status='failed',error='牌阵已取消',updated_at=? WHERE draw_id=? AND status='running'",(_now(),draw_id))
            return self._viewer(self._row(c,owner,draw_id))

    def revise_manual(self,owner,draw_id,cards,reason,idempotency_key):
        reason=_text(reason,'更正说明',800);payload={'draw_id':draw_id,'cards':cards,'reason':reason}
        with self.db(True) as c:
            old=self._row(c,owner,draw_id);request=self._request(c,owner,'revise',idempotency_key,payload)
            if request:return self._viewer(self._row(c,owner,request['draw_id']))
            if old['draw_source']!='manual':raise ValueError('仅实体牌手动录入允许更正牌面；随机抽牌须明确新开一轮')
            spread=json.loads(old['spread_json']);private=self._manual(cards,len(spread['positions']),bool(old['reversals']))
            ident=uuid.uuid4().hex;stamp=_now();row=dict(old)
            revision=c.execute('SELECT MAX(revision) FROM tarot_draws WHERE owner=? AND revision_root=?',(owner,old['revision_root'])).fetchone()[0]+1
            row.update(id=ident,private_deck_json=_json(private),selected_json=_json([dict(x,position=i+1,label=spread['positions'][i],revealed=False) for i,x in enumerate(private)]),
                       status='pending_reveal',revision=revision,previous_draw_id=draw_id,correction_reason=reason,created_at=stamp,updated_at=stamp)
            c.execute('INSERT INTO tarot_draws ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',list(row.values()))
            self._save_request(c,owner,'revise',idempotency_key,payload,ident)
            return self._viewer(self._row(c,owner,ident))

    def get_for_reading(self,owner,draw_id):
        draw=self.get(owner,draw_id)
        if draw['status']!='ready':raise ValueError('请先完成选牌与翻牌；取消的牌阵不能生成新解读')
        draw.pop('backs',None)
        return draw

    def _reading(self,row):
        result={key:row[key] for key in ('id','draw_id','version','status','model','prompt_version','meaning_version','error','created_at','updated_at')}
        result.update(context_snapshot=json.loads(row['context_json']),result=json.loads(row['result_json']) if row['result_json'] else None,
                      validation=json.loads(row['validation_json']))
        return result

    def begin_reading(self,owner,draw_id,*,model,prompt_version,context_snapshot,idempotency_key):
        _text(model,'模型',160);_text(prompt_version,'提示版本',160)
        if not isinstance(context_snapshot,dict) or len(_json(context_snapshot))>80000:raise ValueError('上下文无效或过长')
        payload={'draw_id':draw_id,'model':model,'prompt_version':prompt_version,'context_snapshot':context_snapshot}
        with self.db(True) as c:
            row=self._row(c,owner,draw_id);request=self._request(c,owner,'reading',idempotency_key,payload)
            if request:
                found=c.execute('SELECT * FROM tarot_readings WHERE owner=? AND id=?',(owner,request['reading_id'])).fetchone()
                return {'reading':self._reading(found),'created':False}
            if row['status']!='ready':raise ValueError('请先完成翻牌，取消的牌阵不能解读')
            version=c.execute('SELECT COALESCE(MAX(version),0)+1 FROM tarot_readings WHERE draw_id=?',(draw_id,)).fetchone()[0]
            ident=uuid.uuid4().hex;stamp=_now()
            c.execute('INSERT INTO tarot_readings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (ident,owner,draw_id,version,'running',model,prompt_version,row['meaning_version'],_json(context_snapshot),None,'','{}',stamp,stamp))
            self._save_request(c,owner,'reading',idempotency_key,payload,draw_id,ident)
            return {'reading':self._reading(c.execute('SELECT * FROM tarot_readings WHERE id=?',(ident,)).fetchone()),'created':True}

    def finish_reading(self,owner,reading_id,*,result=None,validation=None,error=None):
        if error is None and (not isinstance(result,dict) or not isinstance(validation,dict)):raise ValueError('成功解读需正文对象与校验记录')
        if len(_json(result))>120000 or len(_json(validation))>12000:raise ValueError('解读内容过长')
        with self.db(True) as c:
            row=c.execute('SELECT * FROM tarot_readings WHERE owner=? AND id=?',(owner,reading_id)).fetchone()
            if not row:raise KeyError('解读不存在或无权访问')
            if row['status']!='running':return self._reading(row)
            c.execute('UPDATE tarot_readings SET status=?,result_json=?,validation_json=?,error=?,updated_at=? WHERE id=?',
                      ('failed' if error is not None else 'success',None if error is not None else _json(result),_json(validation or {}),
                       _text(str(error),'错误',1500,True) if error is not None else '',_now(),reading_id))
            return self._reading(c.execute('SELECT * FROM tarot_readings WHERE id=?',(reading_id,)).fetchone())

    def get_reading(self,owner,reading_id):
        with self.db() as c:
            row=c.execute('SELECT * FROM tarot_readings WHERE owner=? AND id=?',(owner,reading_id)).fetchone()
            if not row:raise KeyError('解读不存在或无权访问')
            return self._reading(row)

    def list_readings(self,owner,draw_id):
        with self.db() as c:
            self._row(c,owner,draw_id)
            return [self._reading(r) for r in c.execute('SELECT * FROM tarot_readings WHERE owner=? AND draw_id=? ORDER BY version',(owner,draw_id))]

    def recover_running(self,owner,older_than_seconds=900):
        threshold=(datetime.now(timezone.utc)-timedelta(seconds=max(0,int(older_than_seconds)))).isoformat(timespec='microseconds')
        with self.db(True) as c:
            result=c.execute("UPDATE tarot_readings SET status='failed',error='上次解读未完成，可以沿用原牌重试',updated_at=? WHERE owner=? AND status='running' AND updated_at<?",(_now(),owner,threshold))
            return result.rowcount

    def validate_cards(self,owner,draw_id,cards,deck_version):
        draw=self.get_for_reading(owner,draw_id)
        if deck_version!=draw['deck_version']:raise ValueError('解释引用了错误牌库版本')
        if not isinstance(cards,list) or len(cards)!=len(draw['cards']):raise ValueError('解释牌数与实际牌阵不符')
        expected={x['position']:x for x in draw['cards']};seen=set()
        for row in cards:
            if not isinstance(row,dict) or type(row.get('position')) is not int or row['position'] not in expected or row['position'] in seen:raise ValueError('解释牌位不存在或重复')
            seen.add(row['position']);actual=expected[row['position']]
            if row.get('card_id')!=actual['card_id'] or row.get('orientation')!=actual['orientation']:raise ValueError('解释改变了实际牌面或方向')
        return {'draw_id_checked':True,'owner_checked':True,'cards_checked':True,'deck_version_checked':True,
                'scope':'仅核对抽牌记录与结构；不证明象征解释在现实中成立'}

    def delete(self,owner,draw_id,include_revisions=True):
        with self.db(True) as c:
            row=self._row(c,owner,draw_id)
            ids=[x[0] for x in c.execute('SELECT id FROM tarot_draws WHERE owner=? AND revision_root=?',(owner,row['revision_root']))] if include_revisions else [draw_id]
            for ident in ids:
                for req in c.execute('SELECT operation,request_key FROM tarot_requests WHERE owner=? AND draw_id=?',(owner,ident)).fetchall():
                    c.execute('INSERT OR IGNORE INTO tarot_deleted_requests VALUES(?,?,?)',(owner,req['operation'],_hash(req['request_key'])))
                c.execute('DELETE FROM tarot_draws WHERE owner=? AND id=?',(owner,ident))
                c.execute('UPDATE tarot_draws SET previous_draw_id=NULL WHERE owner=? AND previous_draw_id=?',(owner,ident))
            return {'deleted_ids':ids,'deleted':True,'scope':'牌阵及所选修订、问题和背景快照、解读版本；关联事项/聊天由共享隐私层按所选范围处理'}

    def purge_context(self,owner,fact_ids,source_ids=None):
        """Forget derived contexts without rewriting the historical selected cards.

        The shared privacy layer passes real fact/source IDs. Only exact IDs or
        namespace-prefixed IDs match; matching does not search private prose.
        Tombstones contain no original snapshot or removed content.
        """
        _text(owner,'身份',160)
        if not isinstance(fact_ids,(list,tuple,set)) or not isinstance(source_ids or [],(list,tuple,set)):
            raise ValueError('事实与来源标识须为数组')
        targets={_text(x,'来源标识',300) for x in list(fact_ids)+list(source_ids or [])}
        if not targets:return {'draw_ids':[],'readings_deleted':0}
        def matches(value):
            if isinstance(value,dict):return any(matches(k) or matches(v) for k,v in value.items())
            if isinstance(value,list):return any(matches(v) for v in value)
            return isinstance(value,str) and any(value==t or value.endswith(':'+t) for t in targets)
        affected=[];deleted=0
        with self.db(True) as c:
            for draw in c.execute('SELECT * FROM tarot_draws WHERE owner=?',(owner,)).fetchall():
                readings=c.execute('SELECT * FROM tarot_readings WHERE owner=? AND draw_id=?',(owner,draw['id'])).fetchall()
                hit=matches(json.loads(draw['snapshot_json'])) or any(matches(json.loads(r['context_json'])) or matches(json.loads(r['validation_json'])) or (r['result_json'] and matches(json.loads(r['result_json']))) for r in readings)
                if not hit:continue
                affected.append(draw['id']);deleted+=len(readings)
                c.execute('DELETE FROM tarot_readings WHERE owner=? AND draw_id=?',(owner,draw['id']))
                for req in c.execute('SELECT operation,request_key FROM tarot_requests WHERE owner=? AND draw_id=?',(owner,draw['id'])).fetchall():
                    c.execute('INSERT OR IGNORE INTO tarot_deleted_requests VALUES(?,?,?)',(owner,req['operation'],_hash(req['request_key'])))
                c.execute('DELETE FROM tarot_requests WHERE owner=? AND draw_id=?',(owner,draw['id']))
                c.execute('UPDATE tarot_draws SET snapshot_json=?,updated_at=? WHERE owner=? AND id=?',
                          (_json({'context_revoked':True,'revoked_at':_now()}),_now(),owner,draw['id']))
        return {'draw_ids':affected,'readings_deleted':deleted}
