#!/usr/bin/env python3
"""明镜台后端：与 Hermes 共享 archive.json 大脑。"""
import json, os, sqlite3, subprocess, datetime, sys, asyncio, logging, uuid, hashlib, hmac
from contextlib import asynccontextmanager
from starlette.concurrency import run_in_threadpool
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE = os.environ.get("ZHIMING_BASE", os.path.expanduser("~/.hermes/zhiming"))
SKILL = os.environ.get("ZHIMING_SKILL", os.path.expanduser("~/.hermes/skills/zhiming"))
sys.path.insert(0, SKILL if os.path.isdir(SKILL) else os.path.join(os.path.dirname(__file__), "hermes"))
from archive_store import read_json, transaction
from context_engine import build_context, choose_date
from chart_context import bundle
from conversation_store import ConversationStore
from semantic_index import SemanticIndex, catalog
from chat_agent import ChatAgent
from report_pipeline import Pipeline
from domain_api import services as domain_services
from domain_context import profile_archive, StaleContext
ARCHIVE = f"{BASE}/archive.json"
WEBLOG = f"{BASE}/webchat.json"          # 网站对话流水（与 Hermes 会话并行）
HERMES_DB = os.environ.get("HERMES_DB", "/root/.hermes/state.db")  # Hermes 会话库（只读）
TOKEN = os.environ.get("MINGJING_TOKEN", "")
KIMI_KEY = os.environ.get("KIMI_API_KEY") or os.environ.get("MOONSHOT_API_KEY", "")
KIMI_BASE = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1").rstrip("/")
KIMI_MODEL = os.environ.get("KIMI_MODEL", "kimi-k3")

store = ConversationStore(BASE)
search_index = SemanticIndex(BASE)
active_turns = {}
index_refresh_lock = asyncio.Lock()
PRIMARY_OWNER=os.environ.get('MINGJING_OWNER_ID','primary')
owner_cache={}

def owner_services(owner):
    if owner==PRIMARY_OWNER:return store,search_index,ARCHIVE
    key=(BASE,owner)
    if key not in owner_cache:
        folder=os.path.join(BASE,'accounts',hashlib.sha256(owner.encode()).hexdigest()[:24])
        owner_cache[key]=(ConversationStore(folder),SemanticIndex(folder),os.path.join(folder,'archive.json'))
    return owner_cache[key]

def make_agent(owner,conversation,index,archive,subject='self',cases=None,draw=None,full=False):
    agent=ChatAgent(conversation,index,archive,lambda session,exclude:agent_history(session,exclude,owner,subject),KIMI_KEY,KIMI_BASE,KIMI_MODEL,web_prompt())
    agent.state_store=domain_services(BASE)[0];agent.state_store.ensure_owner(owner)
    agent.owner_id=owner;agent.subject_id=subject;agent.case_ids=cases;agent.draw=draw;agent.tarot_full=full;agent.legacy_owner=owner==PRIMARY_OWNER
    agent.on_retire=lambda ident:purge_state(owner,*domain_services(BASE),[ident])
    return agent

def scoped_archive(owner,subject='self'):
    state,_=domain_services(BASE);state.ensure_owner(owner)
    return profile_archive(state,owner,subject,load_archive() if owner==PRIMARY_OWNER else {})

def owner_catalog(owner):
    state,_=domain_services(BASE);state.ensure_owner(owner);snap=state.snapshot(owner)
    revoked={r['source']+':'+r['source_id'] for r in snap['suppressed_sources']}
    history=[m for m in agent_history(None,None,owner,'self') if m.get('role')=='user' and m.get('source','web')+':'+str(m.get('turn_id') or m.get('message_id') or m.get('id'))+':user' not in revoked]
    docs=catalog({'conversation_state':{'user_facts':snap['facts']}},history)
    return [dict(d,owner_user_id=owner,subject_id='self') for d in docs]

async def refresh_index(owner=None):
    owner=owner or PRIMARY_OWNER
    async with index_refresh_lock:
        try:
            data=await run_in_threadpool(owner_catalog,owner)
            await run_in_threadpool(owner_services(owner)[1].sync,data)
        except Exception:
            logging.exception("Index refresh failed")
            search_index.status={"mode":"unavailable","documents":0}

@asynccontextmanager
async def lifespan(app):
    await run_in_threadpool(store.recover_interrupted)
    state,tarot=domain_services(BASE)
    with state.db() as c:owners=[r[0] for r in c.execute('SELECT id FROM owners')]
    for owner in owners:await run_in_threadpool(tarot.recover_running,owner,0)
    async def maintain():
        while True:
            await refresh_index()
            try:await run_in_threadpool(store.reconcile)
            except Exception:logging.exception("Conversation mirror recovery failed")
            await asyncio.sleep(180)
    task=asyncio.create_task(maintain())
    yield
    task.cancel()
    for running in list(active_turns.values()):running.cancel()
    await asyncio.gather(task,*list(active_turns.values()),return_exceptions=True)

app = FastAPI(title="明镜台",lifespan=lifespan)
app.mount('/static',StaticFiles(directory=os.path.join(os.path.dirname(__file__),'static')),name='static')

# ---------- 基础设施 ----------

def auth(req: Request):
    configured=json.loads(os.environ.get('ZHIMING_TOKEN_OWNERS','{}'))
    if not TOKEN and not configured:
        raise HTTPException(503, "网站口令未配置")
    t = req.headers.get("X-Token")
    if TOKEN and t and hmac.compare_digest(t,TOKEN):return PRIMARY_OWNER
    for key,owner in configured.items():
        if t and hmac.compare_digest(t,key):return str(owner)
    raise HTTPException(401, "bad token")

def legacy_auth(req):
    if auth(req)!=PRIMARY_OWNER:raise HTTPException(403,'此历史归档未绑定到当前账号')

def load_archive():
    return read_json(ARCHIVE, {})

def run_bazi(args):
    out = subprocess.run(["python3", f"{SKILL}/bazi.py"] + args,
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise HTTPException(500, out.stderr[-500:])
    return json.loads(out.stdout)

def load_weblog():
    return store.history(limit=100000)

def web_prompt():
    with open(os.path.join(os.path.dirname(__file__), "zhiming-web.md"), encoding="utf-8") as f:return f.read()

# ---------- 只读接口 ----------

@app.get("/api/archive")
async def api_archive(req: Request, section: str = ""):
    legacy_auth(req)
    arc = scoped_archive(auth(req))
    return arc.get(section, {}) if section else arc

async def computed_chart(req, engine, date):
    owner=auth(req)
    try:
        target = choose_date("", {"date":date} if date else {})
    except (ValueError, TypeError):
        raise HTTPException(400, "日期须为 YYYY-MM-DD")
    charts = await run_in_threadpool(bundle, scoped_archive(owner), target)
    entry = charts[engine]
    if entry["status"] != "ok":
        raise HTTPException(422, entry.get("reason", "排盘失败"))
    return entry["data"]

@app.get("/api/chart")
async def api_chart(req: Request, date: str = ""):
    return await computed_chart(req, "bazi", date)

@app.get("/api/chart_ziwei")
async def api_chart_ziwei(req: Request, date: str = ""):
    return await computed_chart(req, "ziwei", date)

@app.get("/api/chart_astro")
async def api_chart_astro(req: Request, date: str = ""):
    return await computed_chart(req, "astro", date)

@app.get("/api/health")
async def api_health(req: Request):
    auth(req)
    return {"ok":True,"context_version":"6.0","timezone":"Asia/Shanghai",
            "daily_schedule":"07:00","model":KIMI_MODEL,"retrieval":search_index.status}

@app.get("/api/timeline")
async def api_timeline(req: Request):
    legacy_auth(req)
    arc = load_archive()
    return {"forecasts": arc.get("forecast_registry", []),
            "stats": arc.get("dimension_stats", {})}

@app.get("/api/graph")
async def api_graph(req: Request):
    legacy_auth(req)
    return load_archive().get("graph", {})

LOCAL_TZ = datetime.timezone(datetime.timedelta(hours=8))  # Asia/Shanghai

def load_feishu_log(limit=100,owner=None,subject='self'):
    """读取明确绑定的飞书用户私聊；现有绑定表不支持猜测 chat_id 类型。"""
    try:
        if not owner or not os.path.exists(HERMES_DB) or int(limit)<=0:
            return []
        from context_query import ChannelContext
        state,_=domain_services(BASE)
        with state.db() as sc:
            bindings=[r[0] for r in sc.execute("SELECT external_id FROM channels WHERE owner=? AND subject=? AND channel='feishu'",(owner,subject))]
            purged={r[0] for r in sc.execute("SELECT source_id FROM suppressions WHERE owner=? AND source='feishu' AND purge_message=1",(owner,))}
        if not bindings:return []
        bridge=ChannelContext(BASE,HERMES_DB);rows=[]
        for external_id in bindings:
            binding=bridge.identity('feishu',external_id)
            if binding['owner']!=owner or binding['subject']!=subject:return []
            # Default web access treats bindings only as user IDs. Supporting
            # chat IDs requires an explicit typed binding, absent in this schema.
            rows.extend(bridge._hermes_rows('feishu',external_id,binding_kind='user'))
        rows=[row for row in rows if isinstance(row['content'],str) and row['content'].strip()
              and str(row['id'])+':'+row['role'] not in purged]
        rows.sort(key=lambda row:(float(row['timestamp']),str(row['id'])))
        return [{"role":row['role'],"content":row['content'],"id":"fs-"+str(row['id']),"message_id":row['id'],
                 "source":"feishu","source_id":"feishu:"+str(row['id'])+":"+row['role'],
                 "owner_user_id":owner,"subject_id":subject,"session_id":str(row['session_id']),
                 "at":datetime.datetime.fromtimestamp(float(row['timestamp']),LOCAL_TZ).isoformat(timespec="seconds")}
                for row in rows[-min(int(limit),100000):]]
    except Exception:
        return []

def _parse_at(s):
    """weblog 的 at 是本地 ISO（无偏移），飞书的 at 带 +08:00；统一解析为带时区的本地时间。"""
    try:
        dt = datetime.datetime.fromisoformat(str(s))
    except Exception:
        return datetime.datetime.min.replace(tzinfo=LOCAL_TZ)
    return dt if dt.tzinfo else dt.replace(tzinfo=LOCAL_TZ)

def all_history(owner=None,subject='self'):
    owner=owner or PRIMARY_OWNER
    msgs=owner_services(owner)[0].history(limit=100000)+[dict(m,source="feishu") for m in load_feishu_log(50000,owner,subject)]
    msgs.sort(key=lambda m:_parse_at(m.get("at")))
    return msgs

def agent_history(session,exclude,owner=None,subject='self'):
    owner=owner or PRIMARY_OWNER
    msgs=owner_services(owner)[0].history(session,limit=100000,exclude=exclude)
    msgs=[m for m in msgs if (json.loads(owner_services(owner)[0].get_turn(m['turn_id'])['selection']).get('subject_id','self')==subject)]
    if session in (None,"shared"):msgs += [dict(m,source="feishu") for m in load_feishu_log(50000,owner,subject)]
    msgs.sort(key=lambda m:_parse_at(m.get("at")))
    return msgs

def merged_history(limit=100):return all_history()[-limit:]

def history_cursor(message):
    stamp=_parse_at(message.get('at')).timestamp()
    ident=str(message.get('turn_id') or message.get('id') or '')
    return f"{stamp:020.6f}|{message.get('source','')}|{ident}|{0 if message.get('role')=='user' else 1}"

@app.get("/api/history")
async def api_history(req: Request, session: str = "shared", limit: int = 60, before: str = "", q: str = ""):
    owner=auth(req)
    msgs=await run_in_threadpool(agent_history,session,None,owner)
    msgs=[dict(m,cursor=history_cursor(m)) for m in msgs]
    msgs.sort(key=lambda m:m['cursor'])
    if before:msgs=[m for m in msgs if (m['cursor']<before if '|' in before else str(m.get('at',''))<before)]
    if q:msgs=[m for m in msgs if q.lower() in str(m.get("content","")).lower()]
    return msgs[-max(1,min(limit,500)):]

@app.get('/api/sessions')
async def api_sessions(req: Request):
    owner=auth(req);return owner_services(owner)[0].sessions()

@app.post('/api/sessions')
async def new_session(req: Request):
    owner=auth(req);body=await req.json();return owner_services(owner)[0].new_session(str(body.get('title','新的对话')))

@app.get('/api/images/{ident}')
async def get_image(ident: str,req: Request):
    owner=auth(req)
    try:path=owner_services(owner)[0].image_path(ident)
    except (ValueError,FileNotFoundError):raise HTTPException(404,'图片不存在')
    return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, max-age=3600'})

@app.get('/api/legacy/memories')
async def memories(req: Request):
    legacy_auth(req);raise HTTPException(410,'旧记忆入口已停用')

@app.patch('/api/legacy/memories/{ident}')
async def edit_memory(ident: str,req: Request):
    legacy_auth(req);raise HTTPException(410,'旧事实写入已停用，请使用当前记忆入口')
    try:await run_in_threadpool(store.edit_memory,ident,body.get('text'),body.get('status'))
    except ValueError as exc:raise HTTPException(400,str(exc))
    await refresh_index()
    return {'ok':True}

@app.get('/api/legacy/memories/{ident}/audit')
async def memory_audit(ident: str,req: Request):
    legacy_auth(req);return []

@app.get('/api/reports/status')
async def report_status(req: Request):
    legacy_auth(req)
    result=Pipeline(BASE).status()
    result['worker']=read_json(os.path.join(BASE,'report-worker-health.json'),{})
    return result

@app.post('/api/reports/{ident}/retry')
async def report_retry(ident: str,req: Request):
    legacy_auth(req)
    try:Pipeline(BASE).retry(ident)
    except ValueError as exc:raise HTTPException(400,str(exc))
    return {'ok':True}

@app.get('/api/search')
async def search(req: Request,q: str,source: str = ''):
    owner=auth(req)
    if not 1<=len(q)<=600:raise HTTPException(400,'检索词长度无效')
    try:
        from context_builder import ContextBuilder
        state,_=domain_services(BASE);state.ensure_owner(owner)
        _,_,refs,_=await run_in_threadpool(ContextBuilder(state,owner_services(owner)[1]).build,owner,'self',q,agent_history(None,None,owner))
        return list(refs.values())
    except Exception:raise HTTPException(503,'检索索引正在准备，请稍后重试')

@app.get("/api/feishu_history")   # 飞书私聊会话记录（只读，跨 session 合并最近 100 条）
async def api_feishu_history(req: Request):
    owner=auth(req)
    return load_feishu_log(100,owner)

# ---------- 写回接口 ----------

@app.post("/api/feedback")
async def api_feedback(req: Request):
    legacy_auth(req)
    body = await req.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "请求须为对象")
    fid, fb = body.get("forecast_id"), body.get("feedback")
    if fb not in ("accurate", "partial", "off"):
        raise HTTPException(400, "feedback 非法")
    def update(arc):
        record = next((f for f in arc.get("forecast_registry",[]) if f.get("id")==fid), None)
        if record is None:
            raise HTTPException(404, "未找到预测记录")
        record.update(feedback=fb, status="verified", feedback_at=datetime.datetime.now(LOCAL_TZ).isoformat())
        arc.setdefault("calibration",{}).setdefault("feedback_log",[]).append(
            {"forecast_id":fid,"feedback":fb,"source":"user","at":record["feedback_at"]})
    await run_in_threadpool(transaction, ARCHIVE, update, {})
    return {"ok": True}

# ---------- 对话（SSE） ----------

@app.post("/api/chat")
async def api_chat(req: Request):
    owner=auth(req);body=await req.json();conversation,index,archive=owner_services(owner)
    if not isinstance(body,dict):raise HTTPException(400,'请求须为对象')
    message=body.get('message','');images=body.get('images') or [];selection=body.get('selection') or {}
    if not isinstance(message,str) or not 1<=len(message.strip())<=16000:raise HTTPException(400,'消息需为1至16000字')
    message=message.strip()
    if not isinstance(images,list) or len(images)>4:raise HTTPException(400,'最多4张图片')
    if not isinstance(selection,dict) or len(json.dumps(selection))>1000:raise HTTPException(400,'选择参数无效')
    selection={k:v for k,v in selection.items() if k in ('system','key','date','focus') and isinstance(v,str)}
    subject=body.get('subject_id','self');state,tarot=domain_services(BASE);state.ensure_owner(owner);state.snapshot(owner,subject)
    cases=body.get('case_ids')
    if cases is not None:
        if not isinstance(cases,list) or len(cases)>8 or any(not isinstance(cid,str) or not cid for cid in cases):raise HTTPException(400,'事项列表须为最多8个有效事项ID')
        cases=list(dict.fromkeys(cases))
    else:cases=[body['case_id']] if body.get('case_id') else None
    draw=None
    if cases:state.resolve_cases(owner,subject,message,case_ids=cases)
    if body.get('draw_id'):draw=tarot.get_for_reading(owner,body['draw_id']);cases=[draw['case_id']]
    if subject!='self':selection['subject_id']=subject
    if cases:
        selection['case_ids']=cases
        if len(cases)==1:selection['case_id']=cases[0]
    if draw:selection['draw_id']=draw['id']
    session=str(body.get('session_id','shared'));ident=str(body.get('request_id') or uuid.uuid4().hex)
    try:
        if selection.get('date'):choose_date('',selection)
        image_ids=await run_in_threadpool(conversation.save_images,images)
        retry=body.get('retry_of')
        if retry and not image_ids:
            old=conversation.get_turn(str(retry))
            if old and old['session_id']==session:image_ids=json.loads(old['images'])
        turn,created=await run_in_threadpool(conversation.begin,ident,session,message,image_ids,selection)
    except (ValueError,OSError) as exc:raise HTTPException(400,str(exc))
    if not created and turn['status']=='running':raise HTTPException(409,'这条消息仍在处理中，可稍后刷新历史')
    if not created and turn['status']!='complete':raise HTTPException(409,'该次请求已结束，请使用重试按钮')
    queue=asyncio.Queue()
    async def emit(event):await queue.put(event)
    async def execute():
        try:
            for attempt in range(2):
                agent=make_agent(owner,conversation,index,archive,subject,cases,draw)
                try:final=await asyncio.wait_for(agent.run(turn,emit),timeout=900);break
                except StaleContext:
                    if attempt:raise
                    await emit({'type':'status','text':'资料已更新，正在重新读取当前版本'})
            with state.db(True) as c:
                if final.get('meta',{}).get('revision') is not None:state._revision(c,owner,final['meta']['revision'])
                conversation.finish(ident,final['answer'],'complete',final)
            await emit({'type':'result','result':final,'turn_id':ident})
            try:await run_in_threadpool(transaction,os.path.join(str(conversation.base),'webchat.json'),lambda data:data.__setitem__(slice(None),conversation.history(limit=100000)),[])
            except Exception:logging.exception('Mirror deferred to recovery')
            await refresh_index(owner)
        except asyncio.CancelledError:
            await run_in_threadpool(conversation.finish,ident,'','cancelled',{})
            await emit({'type':'error','message':'已停止，本轮问题已保留'})
            raise
        except Exception as exc:
            logging.exception('Agent failed')
            error=str(exc) if isinstance(exc,RuntimeError) else '本轮暂未完成，请重试；原问题和图片已保留'
            await run_in_threadpool(conversation.finish,ident,'','failed',{'error':error})
            await emit({'type':'error','message':error})
        finally:
            await queue.put(None);active_turns.pop((owner,ident),None)
    if created:active_turns[(owner,ident)]=asyncio.create_task(execute())
    else:
        await queue.put({'type':'result','result':json.loads(turn['meta']),'turn_id':ident})
        await queue.put(None)
    async def stream():
        yield 'data: '+json.dumps({'type':'started','turn_id':ident,'image_ids':image_ids})+'\n\n'
        while True:
            try:event=await asyncio.wait_for(queue.get(),timeout=10)
            except asyncio.TimeoutError:
                yield ': heartbeat\n\n';continue
            if event is None:break
            yield 'data: '+json.dumps(event,ensure_ascii=False)+'\n\n'
        yield 'data: [DONE]\n\n'
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.post('/api/chat/{ident}/cancel')
async def cancel_chat(ident: str,req: Request):
    owner=auth(req)
    if (owner,ident) in active_turns:active_turns[(owner,ident)].cancel()
    return {'ok':True}

@app.get('/api/chat/{ident}')
async def get_chat(ident: str,req: Request):
    owner=auth(req);turn=owner_services(owner)[0].get_turn(ident)
    if not turn:raise HTTPException(404,'记录不存在')
    return {'id':ident,'status':turn['status'],'answer':turn['answer'],'meta':json.loads(turn['meta'])}

# ---------- 静态页 ----------
import domain_api
domain_api.register(app,sys.modules[__name__])

@app.get("/")
async def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static/index.html"))
