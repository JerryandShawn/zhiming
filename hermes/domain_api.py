"""Authenticated state/case/tarot routes mounted into the existing FastAPI app."""
import asyncio,json,uuid,hashlib,os,sqlite3
from contextlib import closing
from pathlib import Path
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import StreamingResponse
from state_store import StateStore,RevisionConflict,EvidenceError
from tarot_store import TarotDrawService
from tarot_deck import public_catalog
from domain_context import memory_view,StaleContext

_services={}
def services(base):
    key=str(Path(base).resolve())
    if key not in _services:_services[key]=(StateStore(base),TarotDrawService(base))
    return _services[key]

def register(app,m):
    router=APIRouter()
    def scope(req,subject='self'):
        owner=m.auth(req);state,tarot=services(m.BASE);state.ensure_owner(owner)
        snap=state.snapshot(owner,subject)
        return owner,state,tarot,snap
    def revision(body):
        value=body.get('expected_revision')
        if type(value) is not int:raise HTTPException(409,'请刷新当前资料版本后重试')
        return value
    async def body(req):
        data=await req.json()
        if not isinstance(data,dict) or len(json.dumps(data))>60000:raise HTTPException(400,'请求无效或过长')
        return data
    def original(state,owner,subject,key,text,case=None):
        if not isinstance(text,str) or not text.strip() or len(text)>16000:raise ValueError('内容不能为空或过长')
        return state.import_message(owner,'web-action',key,'user',text.strip(),subject=subject,case=case)
    def refs(row):return [{'message_id':row['id'],'quote':row['content']}]
    def stable_key(data,prefix,ident):
        return prefix+':'+str(data.get('request_id') or hashlib.sha256(json.dumps([ident,data],ensure_ascii=False,sort_keys=True).encode()).hexdigest())
    def purge(owner,state,tarot,ids):
        # Readers always apply suppression, including during/after cleanup failure.
        snap=state.snapshot(owner)
        sources=[r['source']+':'+r['source_id'] for r in snap['suppressed_sources']]
        tarot.purge_context(owner,ids,sources)
        _,idx,_=m.owner_services(owner)
        with closing(sqlite3.connect(str(idx.path))) as c,c:
            c.execute('PRAGMA secure_delete=ON');c.execute('DELETE FROM documents')
        conversation,_,_=m.owner_services(owner)
        with conversation.db() as c:
            # Older saved facts/mirror audit must not re-import revoked material.
            for fact_id in ids:
                mapped=c.execute('SELECT id FROM memories WHERE id=?',(fact_id,)).fetchone()
                if mapped:c.execute("UPDATE memories SET text='',quote='',status='deleted' WHERE id=?",(fact_id,))
            for src in snap['suppressed_sources']:
                if src['source']=='web' and src['purge_message']:
                    turn=src['source_id'].removesuffix(':user')
                    c.execute("UPDATE turns SET message='',answer='',meta='{}',images='[]' WHERE id=?",(turn,))
            for row in c.execute('SELECT id,meta FROM turns').fetchall():
                meta=json.loads(row['meta'] or '{}');lineage=meta.get('meta',{}).get('injected_ids',[])
                if set(ids)&{str(i).removeprefix('fact:') for i in lineage}:
                    c.execute("UPDATE turns SET answer='',meta='{}' WHERE id=?",(row['id'],))
            c.execute('DELETE FROM memory_audit')
        from archive_store import transaction
        transaction(conversation.base/'webchat.json',lambda data:data.__setitem__(slice(None),conversation.history(limit=100000)),[])
        return snap
    m.purge_state=purge

    @router.get('/api/state')
    async def get_state(req:Request,subject_id:str='self'):
        owner,state,tarot,snap=scope(req,subject_id)
        with state.db() as c:bindings=[dict(r) for r in c.execute('SELECT channel,external_id,subject FROM channels WHERE owner=?',(owner,))]
        return dict(snap,settings=dict(snap['settings'],tarot=tarot.preferences(owner)),bindings=bindings)

    @router.patch('/api/state/settings')
    async def settings(req:Request):
        owner,state,_,_=scope(req);data=await body(req)
        return state.update_settings(owner,data.get('settings',{}),revision(data))

    @router.get('/api/memories')
    async def memories(req:Request,subject_id:str='self'):
        owner,state,_,snap=scope(req,subject_id)
        return [dict(memory_view(f),context_revision=snap['revision']) for f in state.list_facts(owner,subject_id,include_inactive=True)]

    @router.get('/api/memories/{ident}/source')
    async def source(ident:str,req:Request):
        owner,state,_,_=scope(req);fact=state.get_fact(owner,ident);result=[]
        for ref in fact['source_refs']:
            # Viewing an owner's retained original is distinct from authorizing
            # it as current context evidence. Source-scope purges return no text.
            try:row=state.get_message(owner,ref['message_id'],include_suppressed=True)
            except (PermissionError,ValueError):continue
            if row['content']:result.append(dict(ref,content=row['content'],usable_for_context=fact['status']=='active'))
        return {'sources':result,'source_available':bool(result)}

    @router.get('/api/memories/{ident}/audit')
    async def audit(ident:str,req:Request):
        owner,state,_,_=scope(req);state.get_fact(owner,ident)
        with state.db() as c:return [dict(r) for r in c.execute('SELECT operation,revision,at FROM audit WHERE owner=? AND entity_id=? ORDER BY id DESC',(owner,ident))]

    @router.patch('/api/memories/{ident}')
    async def edit(ident:str,req:Request):
        owner,state,tarot,_=scope(req);data=await body(req);fact=state.get_fact(owner,ident);rev=revision(data)
        if data.get('status')=='hidden':
            result=state.stop_fact(owner,ident,rev);purge(owner,state,tarot,[ident]);return result
        if data.get('status')=='active' and fact['status']!='active':raise HTTPException(409,'已停止使用的来源不会自动恢复，请用新原话重新确认')
        text=data.get('text')
        if not isinstance(text,str) or not text.strip():raise ValueError('更正内容不能为空')
        if fact.get('field') and 'value' not in data:raise ValueError('档案更正需同时提供可核对的新字段值')
        if fact.get('field') and str(data['value']) not in text:raise ValueError('新字段值必须出现在确认原话中')
        key=stable_key(data,'memory-edit',ident)
        with state.db() as c:prior=c.execute('SELECT id FROM facts WHERE owner=? AND request_key=?',(owner,key)).fetchone()
        if prior:
            old=state.get_fact(owner,prior['id'])
            if old['content']!='更正：'+text or old['status']!='active':raise HTTPException(409,'该更正后来已变化，请刷新核对')
            return dict(memory_view(old),ok=True,context_revision=state.revision(owner))
        with state.db(True) as c:
            state._revision(c,owner,rev)
            row=original(state,owner,fact['subject'],key,'更正：'+text,fact.get('case_id'))
            result=state.put_fact(owner,fact['subject'],row['content'],refs(row),kind='correction',field=fact.get('field'),value=data.get('value',fact.get('value')),case_id=fact.get('case_id'),supersedes_id=ident,expected_revision=state.revision(owner),explicit=True,idempotency_key=row['source_id'])
        purge(owner,state,tarot,[ident]);return dict(memory_view(result),ok=True,context_revision=state.revision(owner))

    @router.delete('/api/memories/{ident}')
    async def delete(ident:str,req:Request,scope_name:str='fact',scope:str='fact',expected_revision:int|None=None):
        owner,state,tarot,_=scope_fn(req);rev=expected_revision
        if rev is None:
            data=await body(req) if req.headers.get('content-length','0')!='0' else {}
            rev=revision(data)
        result=state.delete_fact(owner,ident,rev,scope=scope);purge(owner,state,tarot,[ident]);return result
    scope_fn=scope

    @router.get('/api/cases')
    async def cases(req:Request,subject_id:str='self'):
        owner,state,_,snap=scope(req,subject_id)
        return [dict(c,context_revision=snap['revision']) for c in state.list_cases(owner,subject_id,include_closed=True)]

    @router.post('/api/cases')
    async def create_case(req:Request):
        data=await body(req);subject=data.get('subject_id','self');owner,state,_,_=scope(req,subject)
        title=str(data.get('title',''));goal=str(data.get('goal',''));key=str(data.get('request_id') or uuid.uuid4().hex)
        row=original(state,owner,subject,'case-create:'+key,title+('。目标：'+goal if goal else ''))
        return state.create_case(owner,subject,title,refs(row),idempotency_key=key,goal=goal)

    @router.patch('/api/cases/{ident}')
    async def update_case(ident:str,req:Request):
        owner,state,_,_=scope(req);data=await body(req);ca=state.get_case(owner,ident);changes=data.get('changes',{})
        key=stable_key(data,'case-edit',ident)
        with state.db() as c:prior=c.execute("SELECT id,content FROM messages WHERE owner=? AND source='web-action' AND source_id=?",(owner,key)).fetchone()
        if prior:
            if prior['content']!=json.dumps(changes,ensure_ascii=False) or not any(r['message_id']==prior['id'] for r in ca['source_refs']):raise HTTPException(409,'该事项更正已失效，请刷新核对')
            return ca
        with state.db(True) as c:
            state._revision(c,owner,revision(data))
            row=original(state,owner,ca['subject'],key,json.dumps(changes,ensure_ascii=False),ident)
            return state.update_case(owner,ident,changes,refs(row),state.revision(owner),explicit=True)

    @router.post('/api/cases/{ident}/events')
    async def event(ident:str,req:Request):
        owner,state,_,_=scope(req);data=await body(req);ca=state.get_case(owner,ident);key=str(data.get('request_id') or uuid.uuid4().hex)
        kind={'acted':'action_started','result':'feedback','rejected_interpretation':'feedback','progress':'discussed'}.get(data.get('kind'),data.get('kind'))
        with state.db() as c:prior=c.execute('SELECT * FROM case_events WHERE owner=? AND request_key=?',(owner,key)).fetchone()
        if prior:
            if prior['case_id']!=ident or prior['kind']!=kind or prior['content']!=data.get('content'):raise ValueError('同一反馈请求不能更换内容或事项')
            return dict(prior,source_refs=json.loads(prior['source_refs']))
        with state.db(True) as c:
            state._revision(c,owner,revision(data))
            row=original(state,owner,ca['subject'],'case-event:'+key,data.get('content',''),ident)
            return state.add_case_event(owner,ident,kind,row['content'],refs(row),idempotency_key=key,expected_revision=state.revision(owner))

    @router.get('/api/tarot/deck')
    async def deck(req:Request):
        owner,_,tarot,_=scope(req);return dict(public_catalog(),preferences=tarot.preferences(owner))

    @router.post('/api/tarot/draws')
    async def draw(req:Request):
        data=await body(req);subject=data.get('subject_id','self');owner,state,tarot,snap=scope(req,subject)
        key=str(data.get('idempotency_key',''));old=tarot.request_result(owner,'create',key)
        client_payload={k:data.get(k,d) for k,d in {'question':'','background':'','subject_id':'self','case_id':None,'spread_id':'reflect3','draw_source':'auto','reversals':True,'options':{},'explicit_new':False,'previous_draw_id':None,'manual_cards':None}.items()}
        fingerprint=hashlib.sha256(json.dumps(client_payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        if old:
            if old['draw']['context_snapshot'].get('client_request_hash')!=fingerprint:raise ValueError('同一请求不能用于另一问题、牌阵、人物或选项')
            return old
        question=data.get('question','');background=data.get('background','');case=data.get('case_id')
        options=data.get('options',{})
        if not isinstance(options,dict):raise ValueError('选项须为对象')
        option_text=''.join('\n'+k+'：'+str(options[k]) for k in ('A','B') if options.get(k))
        row=original(state,owner,subject,'tarot-question:'+key,question+('。补充背景：'+background if background else '')+option_text,case)
        if case:state.resolve_cases(owner,subject,question,case_ids=[case])
        else:
            resolution=state.resolve_cases(owner,subject,question)
            case=resolution.get('case_id')
            if not case:case=state.create_case(owner,subject,str(question)[:80],refs(row),idempotency_key='tarot-case:'+hashlib.sha256(str(question).encode()).hexdigest())['id']
        snap=state.snapshot(owner,subject,case)
        frozen={'revision':snap['revision'],'fact_ids':[f['id'] for f in snap['facts']],'source_refs':refs(row),'background':background,'question_message_id':row['id'],'case_id':case,'client_request_hash':fingerprint}
        return tarot.create_draw(owner,subject_id=subject,case_id=case,question=question,spread_id=data.get('spread_id','reflect3'),draw_source=data.get('draw_source','auto'),reversals=data.get('reversals',True),options=data.get('options',{}),context_snapshot=frozen,idempotency_key=key,explicit_new=data.get('explicit_new',False),previous_draw_id=data.get('previous_draw_id'),manual_cards=data.get('manual_cards'))

    @router.get('/api/tarot/draws')
    async def draws(req:Request,subject_id:str='self',case_id:str|None=None):
        owner,state,tarot,_=scope(req,subject_id)
        if case_id:state.resolve_cases(owner,subject_id,'',case_ids=[case_id])
        return tarot.list_draws(owner,subject_id,case_id)

    @router.get('/api/tarot/draws/{ident}')
    async def get_draw(ident:str,req:Request):
        owner,_,tarot,_=scope(req);return tarot.get(owner,ident)

    @router.post('/api/tarot/draws/{ident}/select')
    async def select(ident:str,req:Request):
        owner,_,tarot,_=scope(req);data=await body(req);return tarot.select(owner,ident,data.get('back_id'),data.get('idempotency_key'))

    @router.post('/api/tarot/draws/{ident}/reveal')
    async def reveal(ident:str,req:Request):
        owner,_,tarot,_=scope(req);data=await body(req);return tarot.reveal(owner,ident,data.get('position'))

    @router.post('/api/tarot/draws/{ident}/cancel')
    async def cancel(ident:str,req:Request):
        owner,_,tarot,_=scope(req);return tarot.cancel(owner,ident)

    @router.patch('/api/tarot/draws/{ident}/manual')
    async def manual(ident:str,req:Request):
        owner,_,tarot,_=scope(req);data=await body(req);return tarot.revise_manual(owner,ident,data.get('cards'),data.get('reason'),data.get('idempotency_key'))

    @router.delete('/api/tarot/draws/{ident}')
    async def delete_draw(ident:str,req:Request):
        owner,state,tarot,_=scope(req);draw=tarot.get(owner,ident)
        with tarot.db() as c:related=[r[0] for r in c.execute('SELECT id FROM tarot_draws WHERE owner=? AND revision_root=?',(owner,draw['revision_root']))]
        readings=[v for i in related for v in tarot.list_readings(owner,i)]
        conversation,_,_=m.owner_services(owner)
        for version in readings:
            turn_id='tarot-reading-'+version['id']
            for role in ('user','assistant'):state.suppress_source(owner,'web',turn_id+':'+role,reason='deleted_tarot',purge_message=True)
            with conversation.db() as c:c.execute("UPDATE turns SET message='',answer='',meta='{}',images='[]' WHERE id=?",(turn_id,))
        for ref in draw['context_snapshot'].get('source_refs',[]):
            row=state.get_message(owner,ref['message_id']);state.suppress_source(owner,row['source'],row['source_id'],reason='deleted_tarot',purge_message=True)
        result=tarot.delete(owner,ident);purge(owner,state,tarot,[]);return result

    @router.get('/api/tarot/draws/{ident}/readings')
    async def readings(ident:str,req:Request):
        owner,_,tarot,_=scope(req);versions=tarot.list_readings(owner,ident)
        with tarot.db() as c:
            keys={r['reading_id']:r['request_key'] for r in c.execute("SELECT reading_id,request_key FROM tarot_requests WHERE owner=? AND draw_id=? AND operation='reading'",(owner,ident))}
        return [dict(v,request_id=keys.get(v['id'])) for v in versions]

    @router.post('/api/tarot/draws/{ident}/readings')
    async def reading(ident:str,req:Request):
        owner,state,tarot,_=scope(req);data=await body(req);draw=tarot.get_for_reading(owner,ident)
        key=str(data.get('request_id') or uuid.uuid4().hex);old=tarot.request_result(owner,'reading',key)
        if old:
            if old['reading']['draw_id']!=ident:raise ValueError('请求标识属于另一牌阵')
            if old['reading']['context_snapshot'].get('supplement','')!=str(data.get('supplement',''))[:16000]:raise ValueError('同一解读请求不能用于不同补充信息')
            record=old['reading'];created=False
        else:
            snap=state.snapshot(owner,draw['subject_id'],draw['case_id'])
            request_snapshot={'revision':snap['revision'],'fact_ids':[f['id'] for f in snap['facts']],'supplement':str(data.get('supplement',''))[:16000]}
            started=tarot.begin_reading(owner,ident,model=m.KIMI_MODEL or 'unconfigured',prompt_version='zhiming-v6',context_snapshot=request_snapshot,idempotency_key=key);record=started['reading'];created=started['created']
        if not created and record['status']=='running':raise HTTPException(409,'解读仍在处理中，请稍后恢复原牌阵')
        queue=asyncio.Queue()
        async def emit(event):await queue.put(event)
        async def execute():
            turn_id=None;conversation=None
            try:
                conversation,index,archive=m.owner_services(owner)
                supplement=record['context_snapshot'].get('supplement','')
                text='请解读这次已冻结的塔罗牌阵。问题：'+draw['question']+('。本轮补充：'+supplement if supplement else '')
                turn_id='tarot-reading-'+record['id']
                turn,_=conversation.begin(turn_id,'shared',text,[],{})
                agent=m.make_agent(owner,conversation,index,archive,draw['subject_id'],[draw['case_id']],draw,True)
                final=await asyncio.wait_for(agent.run(turn,emit),900)
                with state.db(True) as c:
                    state._revision(c,owner,final['meta']['revision'])
                    saved=tarot.finish_reading(owner,record['id'],result=final,validation=final['validation'])
                    if saved['status']!='success':raise RuntimeError(saved.get('error') or '解读已取消')
                    conversation.finish(turn_id,final['answer'],'complete',final)
                await emit({'type':'result','result':final,'reading_id':record['id'],'draw_id':ident})
            except Exception as exc:
                error=str(exc) if isinstance(exc,(RuntimeError,ValueError)) else '解释暂未完成，原牌阵已保留，可沿用它重试'
                tarot.finish_reading(owner,record['id'],error=error)
                if turn_id and conversation:conversation.finish(turn_id,'','failed',{'error':error})
                await emit({'type':'error','message':error,'reading_id':record['id'],'draw_id':ident})
            finally:await queue.put(None)
        if created:asyncio.create_task(execute())
        else:
            await queue.put({'type':'result','result':record['result'],'reading_id':record['id'],'draw_id':ident} if record['status']=='success' else {'type':'error','message':record['error']});await queue.put(None)
        async def stream():
            yield 'data: '+json.dumps({'type':'started','reading_id':record['id'],'draw_id':ident})+'\n\n'
            while True:
                try:event=await asyncio.wait_for(queue.get(),10)
                except asyncio.TimeoutError:yield ': heartbeat\n\n';continue
                if event is None:break
                yield 'data: '+json.dumps(event,ensure_ascii=False)+'\n\n'
            yield 'data: [DONE]\n\n'
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    app.include_router(router)
    @app.exception_handler(RevisionConflict)
    async def conflict(req,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':str(exc)},status_code=409)
    @app.exception_handler(PermissionError)
    async def forbidden(req,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'记录不存在或无权访问'},status_code=404)
    @app.exception_handler(KeyError)
    async def missing(req,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'记录不存在或无权访问'},status_code=404)
    @app.exception_handler(ValueError)
    async def invalid(req,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':str(exc)},status_code=400)
