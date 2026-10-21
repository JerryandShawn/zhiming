"""Authenticated compatibility endpoints; Core v3 is the only business writer."""
import asyncio
import base64
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import uuid
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from psycopg import sql
from psycopg.types.json import Jsonb
from hermes.tarot_deck import public_catalog
from ..application.consultation import ConsultationService, today
from ..application.read_result import read_result
from ..domain.consultation import CoreError, MissingInput
from ..domain.json_values import ensure_finite_json
from ..domain.contracts import ScopeError, RevisionConflict, EvidenceError, LeaseConflict, BudgetExceeded
from ..memory.history import history_window
from ..memory.private import is_private
from .tarot import IdempotencyConflict

ROOT = Path(__file__).resolve().parents[2]
HISTORY_LEGACY_ZONE = ZoneInfo('Asia/Shanghai')


def history_instant(value):
    """Compare instants without rewriting original source timestamps."""
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if stamp.tzinfo is None: stamp = stamp.replace(tzinfo=HISTORY_LEGACY_ZONE)
        return stamp.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def history_sort_key(row):
    stamp = history_instant(row.get('at')) or history_instant(row.get('created_at')) or datetime.min.replace(tzinfo=timezone.utc)
    role = str(row['role'])
    return stamp, str(row['turn_id']), {'user':0, 'assistant':1, 'tool':2, 'legacy':3}.get(role, 4), role


def history_before_key(cursor):
    prefix, separator, tail = cursor.partition('|')
    stamp = history_instant(prefix)
    if stamp is None: raise MissingInput('历史分页游标时间无效，请刷新历史列表')
    if not separator: return stamp, '', -1, ''
    turn_id, role_separator, role = tail.rpartition('|')
    if not role_separator or not turn_id or not role: raise MissingInput('历史分页游标格式无效，请刷新历史列表')
    return stamp, turn_id, {'user':0, 'assistant':1, 'tool':2, 'legacy':3}.get(role, 4), role


def auth(req):
    token = req.headers.get('X-Token', '')
    primary = os.getenv('MINGJING_TOKEN', '')
    mappings = json.loads(os.getenv('ZHIMING_TOKEN_OWNERS', '{}'))
    if not primary and not mappings: raise HTTPException(503, '网站口令未配置')
    if token and primary and hmac.compare_digest(token, primary): return os.getenv('MINGJING_OWNER_ID', 'primary')
    for configured, owner in mappings.items():
        if token and hmac.compare_digest(token, configured): return str(owner)
    raise HTTPException(401, '请登录后继续')


async def body(req):
    value = await req.json()
    if not isinstance(value, dict): raise MissingInput('请求需要对象')
    ensure_finite_json(value)
    return value


def key(data, field='request_id'):
    value = data.get(field)
    if not isinstance(value, str) or not 1 <= len(value) <= 200: raise MissingInput('写操作需要稳定请求标识')
    return value


def revision(data):
    value = data.get('expected_revision')
    if type(value) is not int: raise RevisionConflict('请刷新资料版本后重试')
    return value


async def optional_body(req):
    return await body(req) if await req.body() else {}


def mutation(svc,owner,operation,data,effect):
    """Persist only a command fingerprint and its minimal effect receipt."""
    payload={k:v for k,v in data.items() if k not in ('request_id','idempotency_key')}
    ident=data.get('request_id') or data.get('idempotency_key')
    if ident is None:
        # Old HTTP clients performed naturally idempotent actions without an
        # explicit key. Their complete versioned intent is a stable key.
        ident='compat:'+hashlib.sha256(json.dumps([operation,payload],sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    key({'request_id':ident})
    return svc.repo.mutation_request(owner,operation,ident,payload,effect)


def effect_receipt(result,kind):
    return {k:v for k,v in dict(result,kind=kind).items() if k in ('id','fact_id','status','revision','write_status','kind','deleted','deleted_ids','affected_ids')}


def create_app(service=None, *, event_hints: bool = False):
    if type(event_hints) is not bool:raise ValueError('事件提示候选开关必须是受信布尔配置')
    state = {'service': service, 'workers': {}, 'task': None, 'dispatcher': None, 'maintenance': None,
             'event_hints': None}
    def core(req=None):
        if state['service'] is None: state['service'] = ConsultationService.from_base()
        if req: state['service'].repo.ensure_owner(auth(req))
        return state['service']

    async def execute(owner, run_id, reading_id=None):
        svc = core()
        try:
            result = await asyncio.to_thread(svc.execute, owner, run_id)
            if reading_id: svc.tarot.finish_reading(owner, reading_id, result=result, validation=result['validation'])
        except Exception as exc:
            if reading_id: svc.tarot.finish_reading(owner, reading_id, error=str(exc) if hasattr(exc, 'code') else '解释尚未完成，原牌阵已保留')
        finally: state['workers'].pop(run_id, None)

    def launch(owner, run_id, reading_id=None):
        if core().repo.fetch_run(owner,run_id)['runtime']=='v4':
            if state['dispatcher']:state['dispatcher'].wake.set()
            return
        if run_id not in state['workers']: state['workers'][run_id] = asyncio.create_task(execute(owner, run_id, reading_id))

    async def worker():
        while True:
            from ..application.runtime_assembly import legacy_queue
            svc = core()
            await asyncio.to_thread(state['maintenance'].tick)
            svc.repo.cleanup_media_deletions()
            if not state['workers']:
                queue = legacy_queue(svc.repo,limit=1)
                if queue: launch(queue[0]['owner'], queue[0]['id'], queue[0]['request'].get('reading_id'))
            await asyncio.sleep(2)

    @asynccontextmanager
    async def lifespan(app):
        from ..application.maintenance_schedule import PrivacyMaintenanceSchedule
        svc=core(); assembly=getattr(svc,'runtime_assembly',None)
        state['maintenance']=PrivacyMaintenanceSchedule(svc.repo)
        if assembly:state['dispatcher']=assembly.dispatcher(svc)
        try:
            if event_hints:
                from ..application.run_event_service import acquire_event_hints
                state['event_hints']=acquire_event_hints(svc.repo)
            if state['dispatcher']:state['dispatcher'].start()
            state['task'] = asyncio.create_task(worker())
            yield
        finally:
            if state['task']:
                state['task'].cancel()
                await asyncio.gather(state['task'], return_exceptions=True)
            try:
                if state['dispatcher']:
                    from ..application.runtime_assembly import stop_dispatcher
                    await asyncio.to_thread(stop_dispatcher,state['dispatcher'])
            finally:
                if state['event_hints']:
                    await asyncio.to_thread(state['event_hints'].close)
                    state['event_hints']=None

    app = FastAPI(title='知命明镜台 Core v3', lifespan=lifespan)
    app.state.core = state
    app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')

    async def error(req, exc):
        if isinstance(exc, ScopeError): status = 403
        elif isinstance(exc, (RevisionConflict, LeaseConflict, IdempotencyConflict)): status = 409
        elif isinstance(exc, EvidenceError): status = 409 if 'reused' in str(exc).lower() else 422
        elif isinstance(exc, CoreError): status = exc.http_status
        else: status = 422
        return JSONResponse({'detail': str(exc), 'code': getattr(exc, 'code', 'INVALID_INPUT')}, status_code=status)
    for cls in (CoreError, ScopeError, RevisionConflict, EvidenceError, LeaseConflict, BudgetExceeded, IdempotencyConflict, ValueError, KeyError): app.add_exception_handler(cls, error)

    def lookup(owner, ident):
        svc = core()
        with svc.repo.transaction(owner) as conn:
            row = conn.execute(sql.SQL('SELECT id FROM {} WHERE owner=%s AND (id=%s OR operation_id=%s)').format(svc.repo.table('core_runs')), (owner,ident,ident)).fetchone()
        if not row: raise HTTPException(404, '记录不存在')
        return svc.repo.fetch_run(owner,row['id'])

    async def stream(owner, run, reading_id=None, draw_id=None, request=None):
        svc = core()
        if run['runtime']=='v4':
            from .thread_events import event_response
            if not state['dispatcher']:raise EvidenceError('v4 调度尚未启动，原请求已保留')
            state['dispatcher'].wake.set()
            return event_response(svc.repo,owner,run['id'],request)
        if run['status']=='queued' and not state['workers']: launch(owner,run['id'],reading_id)
        async def events():
            yield 'data: '+json.dumps({'type':'started','turn_id':run['operation_id'],'run_id':run['id'],'reading_id':reading_id,'draw_id':draw_id})+'\n\n'
            yield 'data: '+json.dumps({'type':'context','meta':{'core_run':run['id'],'case_ids':run['request'].get('case_ids',[])}})+'\n\n'
            yield 'data: '+json.dumps({'type':'status','stage':run['status'],'text':'正在恢复持久运行结果' if run['status']=='succeeded' else '问题已进入持久任务队列'},ensure_ascii=False)+'\n\n'
            last_phase = None
            while True:
                current = svc.repo.fetch_run(owner,run['id']); phase = current['checkpoint'].get('phase')
                if phase and phase!=last_phase:
                    last_phase=phase
                    yield 'data: '+json.dumps({'type':'status','stage':phase,'text':'正在核对本轮资料与依据'},ensure_ascii=False)+'\n\n'
                    if phase=='snapshot': yield 'data: '+json.dumps({'type':'context','meta':{'core_run':run['id'],'dependency_versions':current['dependencies']}})+'\n\n'
                if current['status']=='succeeded':
                    final={'type':'result','result':read_result(current['result']),
                           'reading_id':reading_id,'draw_id':draw_id}
                    yield 'data: '+json.dumps(final,ensure_ascii=False)+'\n\n'
                    break
                if current['status'] not in ('running','queued'):
                    yield 'data: '+json.dumps({'type':'error','message':current['error'] or '本轮已停止','run_id':run['id']},ensure_ascii=False)+'\n\n'; break
                yield ': heartbeat\n\n'
                await asyncio.sleep(1)
            yield 'data: [DONE]\n\n'
        return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    @app.get('/')
    async def index(): return FileResponse(ROOT/'static/index.html')

    @app.get('/api/health')
    async def health(req:Request):
        svc=core(req);owner=auth(req)
        return {'ok':True,'context_version':'core3.0','timezone':'Asia/Shanghai','daily_schedule':'07:00','model':getattr(svc.model,'model','test'),
                'retrieval':{'mode':'postgres_scoped','documents':len(svc.memory.facts(owner))},'database':'postgresql','runtime':'langgraph'}

    @app.get('/api/state')
    async def get_state(req:Request,subject_id:str='self'):
        svc=core(req);owner=auth(req);snap=svc.memory.snapshot(owner,subject_id)
        with svc.repo.transaction(owner) as conn: snap['bindings']=conn.execute(sql.SQL('SELECT channel,external_id,subject FROM {} WHERE owner=%s').format(svc.repo.table('core_channels')),(owner,)).fetchall()
        return snap

    @app.patch('/api/state/settings')
    async def settings(req:Request):
        svc=core(req);owner=auth(req);data=await body(req)
        receipt=mutation(svc,owner,'settings',data,lambda:effect_receipt(svc.memory.update_settings(owner,data.get('settings',{}),expected_revision=revision(data)),'settings'))
        return dict(receipt,settings=svc.repo.assert_scope(owner)['settings'])

    @app.get('/api/memories')
    async def memories(req:Request,subject_id:str='self'):
        svc=core(req)
        return [dict(f,text=f.get('content',''),context_revision=f['revision']) for f in svc.memory.facts(auth(req),subject_id,None,include_inactive=True)]

    @app.get('/api/memories/{ident}/source')
    async def source(ident:str,req:Request):
        svc=core(req);owner=auth(req);fact=svc.repo.get(owner,'fact',ident);sources=[]
        for ref in fact.get('source_refs',[]):
            original=svc.memory.get_source(owner,ref['message_id'])
            if original.get('content'): sources.append(dict(ref,content=original['content']))
        return {'sources':sources,'source_available':bool(sources)}

    @app.get('/api/memories/{ident}/audit')
    async def audit(ident:str,req:Request):
        svc=core(req);fact=svc.repo.get(auth(req),'fact',ident,include_deleted=True)
        return [{'operation':fact['status'],'revision':fact['revision'],'at':fact['updated_at']}]

    @app.patch('/api/memories/{ident}')
    async def edit(ident:str,req:Request):
        svc=core(req);owner=auth(req);data=await body(req)
        def apply():
            fact=svc.repo.get(owner,'fact',ident)
            if data.get('status')=='hidden': return effect_receipt(svc.memory.retire_fact(owner,ident,expected_revision=revision(data),operation='stop'),'fact')
            original=svc.memory.receive(owner,fact['subject_id'],'请更正这条已授权的记忆：'+data.get('text',''),source_id=key(data),channel='web-action',case_ids=[fact['case_id']] if fact['case_id'] else [])
            return effect_receipt(svc.memory.correct_fact(owner,ident,original['id'],data.get('text',''),expected_revision=revision(data),field=fact.get('field'),value=data.get('value'),operation_id=key(data)),'fact')
        receipt=mutation(svc,owner,'memory-edit:'+ident,data,apply)
        if not receipt.get('id'):return receipt
        return dict(svc.repo.get(owner,'fact',receipt['id']),write_status=receipt.get('write_status'))

    @app.delete('/api/memories/{ident}')
    async def delete(ident:str,req:Request,scope:str='fact',expected_revision:int|None=None):
        svc=core(req);owner=auth(req);data=await optional_body(req)
        if expected_revision is None:expected_revision=data.get('expected_revision')
        if expected_revision is None: raise RevisionConflict('删除需要最新版本')
        if data.get('scope',scope)!=scope or data.get('expected_revision',expected_revision)!=expected_revision:raise MissingInput('删除范围与版本不一致')
        data.update(scope=scope,expected_revision=expected_revision)
        return mutation(svc,owner,'memory-delete:'+ident,data,lambda:effect_receipt(svc.memory.retire_fact(owner,ident,expected_revision=revision(data),operation='delete',scope=scope),'fact'))

    @app.get('/api/cases')
    async def cases(req:Request,subject_id:str='self'):
        svc=core(req);owner=auth(req)
        return [dict(c,goal=c.get('state',{}).get('goal',''),context_revision=c['revision'],events=[e for e in svc.repo.list(owner,'feedback',subject=subject_id,case_ids=[c['id']]) if e['case_id']==c['id']]) for c in svc.repo.list(owner,'case',subject=subject_id)]

    @app.post('/api/cases')
    async def new_case(req:Request):
        svc=core(req);owner=auth(req);data=await body(req);subject=data.get('subject_id','self')
        def apply():
            text=data.get('title','')+('。目标：'+data['goal'] if data.get('goal') else '')
            original=svc.memory.receive(owner,subject,text,source_id=key(data),channel='web-action')
            return effect_receipt(svc.memory.create_case(owner,subject,data.get('title',''),goal=data.get('goal',''),message_id=original['id'],operation_id=key(data)),'case')
        receipt=mutation(svc,owner,'case-create',data,apply)
        return svc.repo.get(owner,'case',receipt['id'],include_deleted=True)

    @app.patch('/api/cases/{ident}')
    async def update_case(ident:str,req:Request):
        svc=core(req);owner=auth(req);data=await body(req);changes=data.get('changes',{})
        if set(changes)-{'title','goal','status'}: raise MissingInput('事项字段无效')
        def apply():
            old=svc.repo.get(owner,'case',ident)
            payload=dict(old,title=changes.get('title',old['title']),status=changes.get('status',old['status']),state=dict(old.get('state',{}),goal=changes.get('goal',old.get('state',{}).get('goal',''))))
            return effect_receipt(svc.repo.put(owner,'case',ident,payload,subject=old['subject_id'],expected_revision=revision(data),operation_id=key(data)),'case')
        receipt=mutation(svc,owner,'case-update:'+ident,data,apply)
        return svc.repo.get(owner,'case',receipt['id'],include_deleted=True)

    @app.post('/api/cases/{ident}/events')
    async def case_event(ident:str,req:Request):
        svc=core(req);owner=auth(req);data=await body(req)
        if data.get('kind') not in ('decided','acted','result','completed','rejected_interpretation','progress','feedback'): raise MissingInput('反馈类型无效')
        def apply():
            ca=svc.repo.get(owner,'case',ident)
            if revision(data)!=ca['revision']: raise RevisionConflict('事项已更新，请刷新后提交反馈')
            original=svc.memory.receive(owner,ca['subject_id'],data.get('content',''),source_id=key(data),channel='web-action',case_ids=[ident])
            return effect_receipt(svc.repo.put(owner,'feedback','event:'+key(data),{'kind':data['kind'],'content':original['content'],'source_refs':[{'message_id':original['id']}],'occurred_at':original['at']},subject=ca['subject_id'],case_id=ident,operation_id='event:'+key(data)),'feedback')
        receipt=mutation(svc,owner,'case-event:'+ident,data,apply)
        return svc.repo.get(owner,'feedback',receipt['id'],include_deleted=True)

    @app.get('/api/tarot/deck')
    async def deck(req:Request):
        svc=core(req);return dict(public_catalog(),preferences=svc.tarot.preferences(auth(req)))

    @app.get('/api/subjects/self/profile')
    async def profile(req:Request):
        svc=core(req);owner=auth(req);snap=svc.memory.snapshot(owner)
        candidate=next((r.get('profile',{}) for r in svc.repo.list(owner,'legacy') if r.get('source')=='archive:user'),{})
        return {'effective':snap['profile'],'legacy_candidate':candidate,'revision':snap['revision'],'requires_explicit_confirmation':bool(candidate and not snap['profile'])}

    @app.post('/api/subjects/self/profile/confirm')
    async def confirm_profile(req:Request):
        svc=core(req);owner=auth(req);data=await body(req);operation=key(data);payload=data.get('profile',{})
        if data.get('confirmed') is not True or not isinstance(payload,dict): raise MissingInput('请先核对出生资料并明确勾选保存授权')
        fields={}
        def flatten(node,prefix=''):
            for name,value in node.items():
                path=prefix+name
                if isinstance(value,dict): flatten(value,path+'.')
                else: fields[path]=value
        flatten(payload)
        supported={'name','gender','birth.solar_datetime','birth.location.lng','birth.location.lat','birth.location.city','birth.location.name','birth.timezone_offset','birth.time_unknown','birth.time_uncertainty_minutes','birth.precision','birth.interval_start','birth.interval_end'}
        fields={k:v for k,v in fields.items() if k in supported and v is not None}
        if not fields: raise MissingInput('需要实际出生资料或性别字段')
        def confirm_effect():
            if svc.repo.get_revision(owner)!=revision(data): raise RevisionConflict('资料已改变，请重新核对')
            text='请更正这条已授权的记忆：请保存我已核对并确认的出生与性别资料：\n'+'\n'.join(f'{k}：{v}' for k,v in fields.items())
            original=svc.memory.receive(owner,'self',text,source_id='profile-confirm:'+operation,channel='web-action')
            authorization=svc.memory.grant_authorization(owner,'self',original['id'],text,kinds=['profile'],operation_id='profile-consent:'+operation)
            ids=[]
            for field,value in fields.items():
                quote=f'{field}：{value}'
                active=next((f for f in svc.memory.facts(owner) if f.get('field')==field),None)
                if active:
                    result=svc.memory.correct_fact(owner,active['id'],original['id'],quote,field=field,value=value,expected_revision=active['revision'],operation_id=operation+':'+field)
                else:
                    result=svc.memory.save_fact(owner,'self',original['id'],quote,'profile',field=field,value=value,authorization_id=authorization['id'],operation_id=operation+':'+field)
                ident=result.get('id') or result.get('fact_id')
                if ident: ids.append(ident)
            return {'ids':ids,'message_id':original['id'],'revision':svc.repo.get_revision(owner),'kind':'profile','write_status':'saved'}
        receipt=svc.repo.mutation_request(owner,'profile-confirm',operation,{'profile':fields,'confirmed':True},confirm_effect)
        receipts=[]
        for ident in receipt['ids']:
            fact=svc.repo.get(owner,'fact',ident,include_deleted=True)
            receipts.append(dict(fact,write_status='saved' if fact['status']=='active' else 'deleted' if fact['status']=='deleted' else 'stopped'))
        return {'receipts':receipts,'revision':svc.repo.get_revision(owner)}

    @app.post('/api/tarot/draws')
    async def draw(req:Request):
        svc=core(req);owner=auth(req);data=await body(req);subject=data.get('subject_id','self');ident=key(data,'idempotency_key')
        svc.repo.assert_scope(owner,subject)
        case=data.get('case_id')
        original=svc.memory.receive(owner,subject,data.get('question','')+('。背景：'+data['background'] if data.get('background') else ''),source_id='draw:'+ident,channel='web-action',case_ids=[case] if case else [])
        if case:
            if svc.repo.get(owner,'case',case)['subject_id']!=subject: raise ScopeError('事项不属于当前人物')
        else: case=svc.memory.create_case(owner,subject,data.get('question','')[:120],message_id=original['id'],operation_id='drawcase:'+ident)['id']
        snap=svc.memory.snapshot(owner,subject,[case])
        frozen={'revision':snap['revision'],'dependencies':snap['versions'],'fact_ids':[f['id'] for f in snap['facts']],
                'source_refs':[{'message_id':original['id']}],'background':data.get('background',''),'question_message_id':original['id'],'case_id':case}
        return svc.tarot.create_draw(owner,subject_id=subject,case_id=case,question=data.get('question',''),spread_id=data.get('spread_id','reflect3'),
            draw_source=data.get('draw_source','auto'),reversals=data.get('reversals',True),options=data.get('options',{}),context_snapshot=frozen,
            idempotency_key=ident,explicit_new=data.get('explicit_new',False),previous_draw_id=data.get('previous_draw_id'),manual_cards=data.get('manual_cards'))

    @app.get('/api/tarot/draws')
    async def draws(req:Request,subject_id:str='self',case_id:str|None=None): return core(req).tarot.list_draws(auth(req),subject_id,case_id)

    @app.get('/api/tarot/draws/{ident}')
    async def get_draw(ident:str,req:Request): return core(req).tarot.get(auth(req),ident)

    @app.post('/api/tarot/draws/{ident}/select')
    async def select(ident:str,req:Request):
        data=await body(req);return core(req).tarot.select(auth(req),ident,data.get('back_id'),key(data,'idempotency_key'))

    @app.post('/api/tarot/draws/{ident}/reveal')
    async def reveal(ident:str,req:Request):
        svc=core(req);owner=auth(req);data=await optional_body(req)
        mutation(svc,owner,'tarot-reveal:'+ident,data,lambda:effect_receipt(svc.tarot.reveal(owner,ident,data.get('position')),'draw'))
        return svc.tarot.get(owner,ident)

    @app.post('/api/tarot/draws/{ident}/cancel')
    async def cancel_draw(ident:str,req:Request):
        svc=core(req);owner=auth(req);data=await optional_body(req)
        mutation(svc,owner,'tarot-cancel:'+ident,data,lambda:effect_receipt(svc.tarot.cancel(owner,ident),'draw'))
        return svc.tarot.get(owner,ident)

    @app.patch('/api/tarot/draws/{ident}/manual')
    async def manual(ident:str,req:Request):
        data=await body(req);return core(req).tarot.revise_manual(auth(req),ident,data.get('cards'),data.get('reason'),key(data,'idempotency_key'))

    @app.delete('/api/tarot/draws/{ident}')
    async def delete_draw(ident:str,req:Request):
        svc=core(req);owner=auth(req);data=await optional_body(req)
        receipt=mutation(svc,owner,'tarot-delete:'+ident,data,lambda:effect_receipt(svc.tarot.delete(owner,ident),'draw'))
        from ..application.tarot import purge_deleted_checkpoints
        purge_deleted_checkpoints(svc,owner,receipt)
        return receipt

    @app.get('/api/tarot/draws/{ident}/readings')
    async def readings(ident:str,req:Request): return core(req).tarot.list_readings(auth(req),ident)

    @app.post('/api/tarot/draws/{ident}/readings')
    async def reading(ident:str,req:Request):
        svc=core(req);owner=auth(req);data=await body(req);draw=svc.tarot.get_for_reading(owner,ident);request=key(data)
        from ..application.thread_queue import owner_runtime
        if owner_runtime(svc.repo.assert_scope(owner,draw['subject_id'])['settings'])=='v4':
            raise EvidenceError('v4 既有牌阵解读入口尚未接线，原牌阵已保留')
        snap=svc.memory.snapshot(owner,draw['subject_id'],[draw['case_id']])
        version=svc.tarot.begin_reading(owner,ident,model=getattr(svc.model,'model','configured'),prompt_version='core3.0',
                    context_snapshot={'revision':snap['revision'],'fact_ids':[f['id'] for f in snap['facts']],'supplement':data.get('supplement','')},idempotency_key=request)['reading']
        message='请解读这次固定牌阵。问题：'+draw['question']+('。补充背景：'+data['supplement'] if data.get('supplement') else '')
        run=svc.submit(owner=owner,subject=draw['subject_id'],message=message,conversation_id='shared',request_id='reading:'+request,
                       case_ids=[draw['case_id']],mode='tarot',depth=data.get('depth','standard'),draw_id=ident,reading_id=version['id'])
        return await stream(owner,run,version['id'],ident,request=req)

    def save_images(svc,owner,request_id,images):
        if not isinstance(images,list) or len(images)>4: raise MissingInput('每轮最多4张图片')
        results=[]
        folder=Path(os.getenv('ZHIMING_MEDIA_PATH', str(ROOT/'private/media')))/hashlib.sha256(owner.encode()).hexdigest()[:24]
        folder.mkdir(parents=True,exist_ok=True)
        for index,item in enumerate(images):
            if not isinstance(item,str): raise MissingInput('图片格式无效')
            if item.startswith('upload:'):
                svc.repo.get(owner,'upload',item);results.append(item);continue
            if not item.startswith(('data:image/jpeg;base64,','data:image/png;base64,','data:image/webp;base64,')): raise MissingInput('仅支持JPEG、PNG、WebP图片')
            try: raw=base64.b64decode(item.split(',',1)[1],validate=True)
            except ValueError: raise MissingInput('图片数据无效')
            if len(raw)>5*1024*1024: raise MissingInput('每张图片最多5MB')
            ident='upload:'+hashlib.sha256((owner+request_id+str(index)).encode()+raw).hexdigest()[:32]
            path=folder/(ident.replace(':','-')+'.jpg')
            if not path.exists():
                image=Image.open(io.BytesIO(raw))
                if image.width*image.height>20000000: raise MissingInput('图片分辨率过大')
                image.convert('RGB').save(path,format='JPEG',quality=90)
                svc.repo.put(owner,'upload',ident,{'path':str(path),'mime':'image/jpeg','content_hash':hashlib.sha256(raw).hexdigest()},operation_id=ident)
            results.append(ident)
        return results

    @app.get('/api/images/{ident}')
    async def image(ident:str,req:Request):
        row=core(req).repo.get(auth(req),'upload',ident)
        return FileResponse(row['path'],media_type=row.get('mime','image/jpeg'),headers={'Cache-Control':'private,max-age=3600'})

    @app.post('/api/chat')
    async def chat(req:Request):
        from .http_negotiation import parse_chat_accept
        from ..application.run_acceptance import run_acceptance, submission_target
        owner=auth(req);accept=parse_chat_accept(req.headers.getlist('accept'))
        svc=core();data=await body(req);request_id=data.get('retry_of') or key(data)
        if data.get('incognito') or data.get('thread_id') or 'runtime' in data:
            raise EvidenceError('请通过线程入口发送消息，运行版本由持久设置决定')
        with svc.repo.transaction(owner):
            runtime,_=submission_target(svc.repo,owner,data.get('subject_id','self'),request_id)
            representation=accept.representation(runtime)
            if representation=='json':
                if not state['dispatcher']:raise EvidenceError('v4 调度尚未启动，请保留原请求稍后再试')
                svc.runtime_assembly.require_agent()
            if data.get('images') and runtime=='v4':
                raise EvidenceError('v4 附件入口尚未接线，请保留原文件')
            core(req)
            images=save_images(svc,owner,request_id,data.get('images') or [])
            run=svc.submit(owner=owner,subject=data.get('subject_id','self'),message=data.get('message',''),conversation_id=data.get('session_id','shared'),
                request_id=request_id,case_ids=data.get('case_ids') or ([data['case_id']] if data.get('case_id') else []),depth=data.get('depth','standard'),selection=data.get('selection') or {},draw_id=data.get('draw_id'),images=images)
            if representation=='json':receipt=run_acceptance(svc.repo,owner,run['id'])
        if representation=='json':
            state['dispatcher'].wake.set()
            return JSONResponse(receipt,status_code=202,headers={'Vary':'Accept','Cache-Control':'no-store'})
        return await stream(owner,run,request=req)

    @app.get('/api/chat/{ident}')
    async def get_chat(ident:str,req:Request):
        owner=auth(req);core(req);run=lookup(owner,ident)
        final=read_result(run['result']) if run['status']=='succeeded' else {}
        return {'id':ident,'run_id':run['id'],'status':{'succeeded':'complete','queued':'running'}.get(run['status'],run['status']),
                'answer':final.get('answer',''),'meta':final if final else {'error':run['error']}}

    @app.get('/api/runs/{ident}')
    async def get_run(ident:str,req:Request):
        owner=auth(req);core(req);run=lookup(owner,ident)
        if run['status']=='succeeded':run=dict(run,result=read_result(run['result']))
        return {k:run[k] for k in ('id','operation_id','status','calls','call_limit','attempts','checkpoint','dependencies','error','result')}

    async def stop(ident:str,req:Request):
        owner=auth(req);svc=core(req);run=lookup(owner,ident)
        if run['runtime']=='v4':
            from ..application.dispatcher_cancellation import DispatcherCancellation
            assembly=getattr(svc,'runtime_assembly',None)
            DispatcherCancellation(svc.repo,assembly.signals if assembly else None).request(owner,run['id'])
            return {'ok':True,'run_id':run['id']}
        with svc.repo.transaction(owner) as conn:
            conn.execute(sql.SQL("UPDATE {} SET status='cancelled',lease_token=NULL,lease_until=NULL,error='用户已停止本轮',updated_at=now() WHERE owner=%s AND id=%s AND status IN ('queued','running')").format(svc.repo.table('core_runs')),(owner,run['id']))
        return {'ok':True,'run_id':run['id']}
    app.post('/api/chat/{ident}/cancel')(stop)
    app.post('/api/runs/{ident}/cancel')(stop)

    @app.post('/api/runs/{ident}/retry')
    async def retry(ident:str,req:Request):
        svc=core(req);owner=auth(req);run=lookup(owner,ident)
        prepared=svc.repo.prepare_retry(owner,run['id'])
        if prepared['purge_checkpoint']: svc.runtime.purge(run['id'],run.get('retry_epoch',0))
        current=prepared['run']
        if current['request'].get('reading_id'):
            svc.tarot.resume_reading(owner,current['request']['reading_id'],current['id'])
        return await stream(owner,current,current['request'].get('reading_id'),current['request'].get('draw_id'),request=req)

    @app.post('/api/runs/{ident}/resume')
    async def resume(ident:str,req:Request):
        svc=core(req);owner=auth(req);data=await body(req);old=lookup(owner,ident)
        interrupt=(old.get('result') or {}).get('meta',{}).get('interrupt')
        if not interrupt or data.get('interrupt_id')!=interrupt['id'] or data.get('state_version')!=interrupt['state_version']: raise RevisionConflict('澄清状态已改变，请刷新运行记录')
        new_id=key(data,'message_id')
        run=svc.submit(owner=owner,subject=old['subject'],message=data.get('message',''),conversation_id=old['request']['conversation_id'],
            request_id='resume:'+old['id']+':'+new_id,case_ids=old['request']['case_ids'],depth=old['request']['depth'],draw_id=old['request']['draw_id'],parent_run=old['id'])
        return await stream(owner,run,request=req)

    @app.get('/api/history')
    async def history(req:Request,session:str='shared',limit:int=60,before:str='',q:str='',subject_id:str='self'):
        svc=core(req);owner=auth(req)
        boundary=history_before_key(before) if before else None
        return history_window(svc.repo,owner,subject_id,session,limit,boundary,q)

    @app.get('/api/feishu_history')
    async def feishu_history(req:Request):
        svc=core(req);owner=auth(req)
        rows=[m for m in svc.repo.list(owner,'message') if m.get('channel')=='feishu' and not is_private(m)][-100:]
        return [svc.memory.get_source(owner,m['id'],for_context=True) for m in rows]

    @app.get('/api/sessions')
    async def sessions(req:Request): return core(req).repo.list(auth(req),'session')

    @app.post('/api/sessions')
    async def session(req:Request):
        svc=core(req);owner=auth(req);data=await body(req);ident=key(data)
        return svc.repo.put(owner,'session',ident,{'title':data.get('title','新的对话')},operation_id='session:'+ident)

    async def chart(req,system,date):
        svc=core(req);owner=auth(req);snap=svc.memory.snapshot(owner)
        result=svc.calculate_chart(owner,'self',snap,date or today(),[system])
        if not result['artifacts']: raise MissingInput('；'.join(e.get('reason','计算资料不足') for e in result['errors']))
        first=next(iter(result['artifacts'].values()))
        return dict(first['data'],core_meta={'profiles':result['profiles'],'branches':result['branches'],'warnings':first.get('warnings',[])})
    @app.get('/api/chart')
    async def bazi(req:Request,date:str=''): return await asyncio.to_thread(chart_sync,req,'bazi',date)
    def chart_sync(req,system,date): return asyncio.run(chart(req,system,date))
    @app.get('/api/chart_ziwei')
    async def ziwei(req:Request,date:str=''): return await asyncio.to_thread(chart_sync,req,'ziwei',date)
    @app.get('/api/chart_astro')
    async def astro(req:Request,date:str=''): return await asyncio.to_thread(chart_sync,req,'astro',date)

    def legacy(owner,section):
        rows=core().repo.list(owner,'legacy')
        for row in rows:
            if row.get('section')==section: return row.get('payload',row.get('value',{}))
        return {}
    @app.get('/api/archive')
    async def archive(req:Request,section:str=''):
        svc=core(req);owner=auth(req)
        if section: return legacy(owner,section)
        return {r['section']:r.get('payload',r.get('value',{})) for r in svc.repo.list(owner,'legacy') if r.get('section')}
    @app.get('/api/timeline')
    async def timeline(req:Request):
        core(req);owner=auth(req);return {'forecasts':legacy(owner,'forecast_registry'),'stats':legacy(owner,'dimension_stats')}
    @app.get('/api/graph')
    async def graph(req:Request): core(req);return legacy(auth(req),'graph')
    @app.get('/api/dict')
    async def dictionary(req:Request): core(req);return legacy(auth(req),'omen_dictionary')
    @app.get('/api/search')
    async def search(req:Request,q:str,source:str=''):
        svc=core(req);owner=auth(req)
        if not 1<=len(q)<=600: raise MissingInput('搜索词长度无效')
        return [{'ref':f['id'],'source':'memory','text':f.get('content','')} for f in svc.memory.facts(owner) if q.lower() in f.get('content','').lower()][:40]
    @app.get('/api/reports')
    async def reports(req:Request): return core(req).repo.list(auth(req),'report')
    @app.get('/api/reports/status')
    async def report_status(req:Request):
        status=core(req).outbox.status(auth(req))
        return {**status,'outbox':status,'worker':{'runtime':'core3.0'}}
    @app.get('/api/reports/schedules')
    async def report_schedules(req:Request):
        from ..application.report_schedules import ReportScheduleService
        return ReportScheduleService(core(req).repo).list(auth(req))
    @app.patch('/api/reports/schedules')
    async def update_report_schedule(req:Request):
        from ..application.report_schedules import ReportScheduleService
        svc=core(req);owner=auth(req)
        return ReportScheduleService(svc.repo).patch(owner,await body(req))
    @app.post('/api/reports/{ident}/retry')
    async def report_retry(ident:str,req:Request):
        svc=core(req);owner=auth(req);rows=svc.outbox.status(owner)['rows']
        row=next((r for r in rows if r['id']==ident),None)
        if not row: raise MissingInput('报告投递不存在')
        if row['status']=='DELIVERY_UNCERTAIN': raise RevisionConflict('投递情况尚未确认，请先核对实际回执')
        raise RevisionConflict('请从报告状态按最新授权重新准备，禁止盲目重发')
    @app.post('/api/feedback')
    async def feedback(req:Request):
        svc=core(req);owner=auth(req);data=await body(req)
        return svc.repo.put(owner,'feedback',key(data),{'forecast_id':data.get('forecast_id'),'feedback':data.get('feedback'),'source':'user'},operation_id='feedback:'+key(data))
    from .thread_routes import thread_router
    app.include_router(thread_router(core,auth,body))
    return app
