"""Durable web conversations, image references and attributable memory."""
import base64
import hashlib
import io
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from archive_store import read_json, transaction

TZ=timezone(timedelta(hours=8))
def now():return datetime.now(TZ).isoformat(timespec='seconds')

class ConversationStore:
    def __init__(self,base):
        self.base=Path(base);self.base.mkdir(parents=True,exist_ok=True)
        self.path=self.base/'web.db'
        with self.db() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,title TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS turns(id TEXT PRIMARY KEY,session_id TEXT,message TEXT,images TEXT,selection TEXT,
              answer TEXT DEFAULT '',status TEXT,created_at TEXT,updated_at TEXT,meta TEXT DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,text TEXT,quote TEXT,category TEXT,source_turn TEXT,
              created_at TEXT,status TEXT DEFAULT 'active',supersedes TEXT);
            CREATE TABLE IF NOT EXISTS memory_audit(id INTEGER PRIMARY KEY, memory_id TEXT,before_json TEXT,at TEXT);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
            CREATE INDEX IF NOT EXISTS turn_session ON turns(session_id,created_at);
            ''')
            c.execute('INSERT OR IGNORE INTO sessions VALUES(?,?,?)',('shared','与明镜对话',now()))
            if not c.execute("SELECT 1 FROM settings WHERE key='legacy_imported'").fetchone():
                entries=read_json(self.base/'webchat.json',[])
                pending=None
                for n,m in enumerate(entries):
                    if m.get('role')=='user':
                        ident='legacy-'+str(n)
                        c.execute('INSERT OR IGNORE INTO turns(id,session_id,message,images,selection,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                          (ident,'shared',str(m.get('content','')),'[]','{}','imported',m.get('at',now()),m.get('at',now())))
                        pending=ident
                    elif m.get('role')=='assistant' and pending:
                        c.execute("UPDATE turns SET answer=?,status='complete' WHERE id=?",(str(m.get('content','')),pending));pending=None
                    elif m.get('role')=='assistant':
                        c.execute('INSERT OR IGNORE INTO turns(id,session_id,message,images,selection,answer,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                          ('legacy-'+str(n),'shared','','[]','{}',str(m.get('content','')),'complete',m.get('at',now()),m.get('at',now())))
                c.execute("INSERT INTO settings VALUES('legacy_imported','1')")

    @contextmanager
    def db(self):
        c=sqlite3.connect(str(self.path),timeout=15)
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA journal_mode=DELETE')
        try:
            with c:yield c
        finally:c.close()

    def sessions(self):
        with self.db() as c:
            return [dict(r) for r in c.execute('SELECT s.*,COALESCE(MAX(t.updated_at),s.created_at) AS updated_at,COUNT(t.id) AS turns FROM sessions s LEFT JOIN turns t ON t.session_id=s.id GROUP BY s.id ORDER BY updated_at DESC')]

    def new_session(self,title='新的对话'):
        ident=uuid.uuid4().hex
        with self.db() as c:c.execute('INSERT INTO sessions VALUES(?,?,?)',(ident,title[:60],now()))
        return {'id':ident,'title':title[:60]}

    def begin(self,ident,session,message,images,selection):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',ident):raise ValueError('请求标识无效')
        with self.db() as c:
            row=c.execute('SELECT * FROM turns WHERE id=?',(ident,)).fetchone()
            if row:
                if row['message']!=message or row['session_id']!=session or json.loads(row['images'])!=images or json.loads(row['selection'])!=selection:raise ValueError('请求标识已用于其他消息')
                return dict(row),False
            if not c.execute('SELECT 1 FROM sessions WHERE id=?',(session,)).fetchone():raise ValueError('会话不存在')
            c.execute('INSERT INTO turns(id,session_id,message,images,selection,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                      (ident,session,message,json.dumps(images),json.dumps(selection,ensure_ascii=False),'running',now(),now()))
            c.execute("UPDATE sessions SET title=? WHERE id=? AND title='新的对话'",(message[:24],session))
            return dict(c.execute('SELECT * FROM turns WHERE id=?',(ident,)).fetchone()),True

    def finish(self,ident,answer,status,meta=None):
        with self.db() as c:c.execute('UPDATE turns SET answer=?,status=?,meta=?,updated_at=? WHERE id=?',
                 (answer,status,json.dumps(meta or {},ensure_ascii=False),now(),ident))

    def get_turn(self,ident):
        with self.db() as c:
            row=c.execute('SELECT * FROM turns WHERE id=?',(ident,)).fetchone()
            return dict(row) if row else None

    def history(self,session=None,limit=100,exclude=None):
        query='SELECT * FROM turns WHERE id!=?';args=[exclude or '']
        if session:query+=' AND session_id=?';args.append(session)
        query+=' ORDER BY created_at DESC,rowid DESC LIMIT ?';args.append(limit)
        with self.db() as c:rows=list(c.execute(query,args))
        messages=[]
        for row in reversed(rows):
            base={'at':row['created_at'],'source':'web','turn_id':row['id'],'session_id':row['session_id']}
            if row['message']:messages.append(dict(base,role='user',content=row['message'],image_ids=json.loads(row['images']),status=row['status']))
            if row['answer']:messages.append(dict(base,role='assistant',content=row['answer'],status=row['status'],context_meta=json.loads(row['meta'])))
        return messages

    def save_images(self,urls):
        from PIL import Image,ImageOps
        folder=self.base/'images';folder.mkdir(exist_ok=True)
        ids=[]
        for url in urls:
            if not isinstance(url,str) or len(url)>8000000:raise ValueError('图片超过大小限制')
            if not re.match(r'^data:image/(png|jpeg|webp);base64,',url):raise ValueError('图片格式不支持')
            data=base64.b64decode(url.split(',',1)[1],validate=True)
            with Image.open(io.BytesIO(data)) as im:
                if im.width*im.height>24000000:raise ValueError('图片像素过大')
                im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((1600,1600))
                out=io.BytesIO();im.save(out,format='JPEG',quality=87)
            data=out.getvalue();ident=hashlib.sha256(data).hexdigest()
            target=folder/(ident+'.jpg')
            if not target.exists():
                temp=folder/(ident+'.'+uuid.uuid4().hex+'.tmp');temp.write_bytes(data);os.chmod(temp,0o600);os.replace(temp,target)
            ids.append(ident)
        return ids

    def image_path(self,ident):
        if not re.fullmatch('[a-f0-9]{64}',ident):raise ValueError('图片标识无效')
        path=self.base/'images'/(ident+'.jpg')
        if not path.is_file():raise FileNotFoundError('图片不存在')
        return path

    def image_block(self,ident):
        return {'type':'image','source':{'type':'base64','media_type':'image/jpeg',
                 'data':base64.b64encode(self.image_path(ident).read_bytes()).decode()}}

    def memories(self,include_inactive=False):
        with self.db() as c:
            return [dict(r) for r in c.execute('SELECT * FROM memories '+('' if include_inactive else "WHERE status='active' ")+'ORDER BY created_at DESC,rowid DESC')]

    def remember(self,turn_id,quote,category='背景',supersedes=None):
        turn=self.get_turn(turn_id)
        return self._remember(turn,quote,category,supersedes)

    def remember_feishu(self,message_id,quote,category='背景',supersedes=None):
        path=os.environ.get('HERMES_DB','/root/.hermes/state.db')
        c=sqlite3.connect(f'file:{path}?mode=ro',uri=True)
        try:
            row=c.execute("SELECT m.content FROM messages m JOIN sessions s ON s.id=m.session_id WHERE m.id=? AND m.role='user' AND m.active=1 AND s.source='feishu' AND s.chat_type='dm'",(message_id,)).fetchone()
        finally:c.close()
        if not row:raise ValueError('未找到对应飞书用户原话')
        return self._remember({'id':'feishu-'+str(message_id),'message':str(row[0])},quote,category,supersedes)

    def _remember(self,turn,quote,category,supersedes):
        quote=str(quote).strip()
        if not turn or not 4<=len(quote)<=600 or quote not in turn['message']:
            raise ValueError('记忆必须逐字引用用户本轮陈述，不能由模型编写事实')
        if re.search(r'假如|假设|如果我|也许|可能会|比如说|举个例子|[？?]',quote):
            raise ValueError('假设或疑问不能作为长期事实保存')
        if re.search(r'假如|假设|举个例子',turn['message']):raise ValueError('本轮含假设场景，请由用户明确确认后再保存记忆')
        if category not in ('背景','偏好','更正','目标','事件'):raise ValueError('记忆类型无效')
        if supersedes and (category!='更正' or not re.search(r'不是|更正|纠正|改为|现在|不再|其实',turn['message'])):
            raise ValueError('替换旧记忆需要用户本轮明确更正；不确定时保留原记录')
        turn_id=turn['id']
        ident=hashlib.sha256((turn_id+quote).encode()).hexdigest()[:24]
        with self.db() as c:
            if supersedes:
                old=c.execute("SELECT * FROM memories WHERE id=? AND status='active'",(supersedes,)).fetchone()
                if not old:raise ValueError('被更正记忆不存在')
                c.execute('INSERT INTO memory_audit(memory_id,before_json,at) VALUES(?,?,?)',(supersedes,json.dumps(dict(old),ensure_ascii=False),now()))
                c.execute("UPDATE memories SET status='superseded' WHERE id=?",(supersedes,))
            c.execute('INSERT OR IGNORE INTO memories VALUES(?,?,?,?,?,?,?,?)',
                      (ident,quote,quote,category,turn_id,now(),'active',supersedes))
        self.sync_memories()
        return {'id':ident,'text':quote,'category':category,'source':'用户原话'}

    def audit(self,ident):
        with self.db() as c:return [{'at':r['at'],'before':json.loads(r['before_json'])} for r in c.execute('SELECT * FROM memory_audit WHERE memory_id=? ORDER BY id DESC',(ident,))]

    def recover_interrupted(self):
        with self.db() as c:c.execute("UPDATE turns SET status='interrupted',meta=?,updated_at=? WHERE status='running'",(json.dumps({'error':'服务重启打断了本轮，问题与图片已保留'}),now()))

    def edit_memory(self,ident,text=None,status=None):
        with self.db() as c:
            row=c.execute('SELECT * FROM memories WHERE id=?',(ident,)).fetchone()
            if not row:raise ValueError('记忆不存在')
            c.execute('INSERT INTO memory_audit(memory_id,before_json,at) VALUES(?,?,?)',(ident,json.dumps(dict(row),ensure_ascii=False),now()))
            if text is not None:
                if not 1<=len(text.strip())<=600:raise ValueError('记忆需为1至600字')
                c.execute('UPDATE memories SET text=? WHERE id=?',(text.strip(),ident))
            if status:
                if status not in ('active','hidden'):raise ValueError('状态无效')
                c.execute('UPDATE memories SET status=? WHERE id=?',(status,ident))
        self.sync_memories()

    def sync_memories(self):
        # Read while holding the archive lock, so concurrent edits cannot publish an older snapshot.
        def update(arc):arc.setdefault('conversation_state',{})['user_facts']=self.memories()
        transaction(self.base/'archive.json',update,{})

    def reconcile(self):
        transaction(self.base/'webchat.json',lambda data:data.__setitem__(slice(None),self.history(limit=100000)),[])
        def update(arc):
            rows=self.history(limit=100000)
            for m in rows:
                if m['role']!='assistant' or m['status']!='complete':continue
                turn=self.get_turn(m['turn_id'])
                if turn['id'].startswith('legacy-'):continue
                date=m['at'][:10];days=arc.setdefault('daily_log',[])
                day=next((d for d in days if d.get('date')==date),None)
                if day is None:day={'date':date,'questions':[]};days.append(day)
                questions=day.setdefault('questions',[])
                if not any(q.get('turn_id')==turn['id'] for q in questions):
                    questions.append({'turn_id':turn['id'],'q':turn['message'],'answer_summary':turn['answer'][:1800],
                                      'verified':None,'source':'web','at':turn['created_at']})
        transaction(self.base/'archive.json',update,{})
