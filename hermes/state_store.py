"""Authoritative, owner-scoped state. Called only behind authenticated adapters.

The database is the authority; search and archive summaries are disposable views.
No model invocation occurs inside a transaction. Content changes require original
registered evidence, and deletion audit deliberately contains no deleted prose.
"""
import hashlib
import json
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ASSERTIONS = {'user_asserted','user_confirmed','tool_observation','assistant_interpretation',
              'hypothesis','unverified_prediction','legacy_unverified'}
FACT_KINDS = {'profile','preference','constraint','goal','event','concern','hearsay',
              'hypothesis','correction','background','tool_event','interpretation'}
USER_ASSERTIONS = {'user_asserted','user_confirmed'}
CASE_FIELDS = {'title','goal','conditions','options','excluded_options','decision','actions','progress','pending','status'}


class RevisionConflict(ValueError): pass
class ScopeError(PermissionError): pass
class EvidenceError(ValueError): pass


def now(): return datetime.now(timezone.utc).isoformat(timespec='microseconds')
def dumps(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(*parts): return hashlib.sha256(dumps(parts).encode()).hexdigest()
def ident(prefix): return prefix+'_'+uuid.uuid4().hex


def timestamp(value=None):
    if value is None: return now()
    if isinstance(value,datetime): dt=value
    else:
        try: dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        except ValueError as exc: raise ValueError('日期或时刻无效') from exc
    # Existing application dates are civil Asia/Shanghai dates.
    if dt.tzinfo is None:
        from datetime import timedelta
        dt=dt.replace(tzinfo=timezone(timedelta(hours=8)))
    return dt.astimezone(timezone.utc).isoformat(timespec='microseconds')


class StateStore:
    def __init__(self,base):
        self._transaction_local=threading.local()
        base=Path(base)
        self.path=base if base.suffix in ('.sqlite','.db','.sqlite3') else base/'state.sqlite'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS owners(id TEXT PRIMARY KEY,revision INTEGER NOT NULL DEFAULT 0,settings TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS subjects(owner TEXT NOT NULL,id TEXT NOT NULL,label TEXT NOT NULL,consent TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(owner,id));
            CREATE TABLE IF NOT EXISTS channels(channel TEXT NOT NULL,external_id TEXT NOT NULL,owner TEXT NOT NULL,subject TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(channel,external_id));
            CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,owner TEXT NOT NULL,subject TEXT NOT NULL,source TEXT NOT NULL,source_id TEXT NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,at TEXT NOT NULL,recorded_at TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,conversation_id TEXT NOT NULL,cases TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active',UNIQUE(owner,source,source_id));
            CREATE TABLE IF NOT EXISTS facts(id TEXT PRIMARY KEY,owner TEXT NOT NULL,subject TEXT NOT NULL,case_id TEXT,kind TEXT NOT NULL,content TEXT NOT NULL,source_refs TEXT NOT NULL,assertion_status TEXT NOT NULL,valid_from TEXT NOT NULL,valid_to TEXT,recorded_at TEXT NOT NULL,supersedes_id TEXT,revision INTEGER NOT NULL,consent TEXT NOT NULL,retention TEXT NOT NULL,status TEXT NOT NULL,field TEXT,value_json TEXT,request_key TEXT NOT NULL,request_hash TEXT NOT NULL,UNIQUE(owner,request_key));
            CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY,owner TEXT NOT NULL,subject TEXT NOT NULL,title TEXT NOT NULL,state TEXT NOT NULL,status TEXT NOT NULL,source_refs TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,revision INTEGER NOT NULL,request_key TEXT NOT NULL,UNIQUE(owner,request_key));
            CREATE TABLE IF NOT EXISTS case_events(id TEXT PRIMARY KEY,owner TEXT NOT NULL,subject TEXT NOT NULL,case_id TEXT NOT NULL,kind TEXT NOT NULL,content TEXT NOT NULL,source_refs TEXT NOT NULL,assertion_status TEXT NOT NULL,occurred_at TEXT NOT NULL,recorded_at TEXT NOT NULL,revision INTEGER NOT NULL,request_key TEXT NOT NULL,UNIQUE(owner,request_key));
            CREATE TABLE IF NOT EXISTS conversation_scope(owner TEXT NOT NULL,subject TEXT NOT NULL,conversation_id TEXT NOT NULL,case_ids TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(owner,subject,conversation_id));
            CREATE TABLE IF NOT EXISTS suppressions(owner TEXT NOT NULL,source TEXT NOT NULL,source_id TEXT NOT NULL,reason TEXT NOT NULL,purge_message INTEGER NOT NULL DEFAULT 0,at TEXT NOT NULL,PRIMARY KEY(owner,source,source_id));
            CREATE TABLE IF NOT EXISTS tombstones(owner TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,operation TEXT NOT NULL,revision INTEGER NOT NULL,at TEXT NOT NULL,PRIMARY KEY(owner,entity_type,entity_id));
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,owner TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,operation TEXT NOT NULL,revision INTEGER NOT NULL,at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS traces(owner TEXT NOT NULL,run_id TEXT NOT NULL,subject TEXT NOT NULL,case_id TEXT,payload TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(owner,run_id));
            CREATE TABLE IF NOT EXISTS legacy_map(owner TEXT NOT NULL,source TEXT NOT NULL,legacy_id TEXT NOT NULL,entity_type TEXT NOT NULL,new_id TEXT,status TEXT NOT NULL,PRIMARY KEY(owner,source,legacy_id,entity_type));
            CREATE INDEX IF NOT EXISTS facts_scope ON facts(owner,subject,status,case_id,valid_from);
            CREATE INDEX IF NOT EXISTS messages_scope ON messages(owner,subject,conversation_id,at);
            CREATE INDEX IF NOT EXISTS events_case ON case_events(owner,case_id,occurred_at);
            PRAGMA user_version=6;
            ''')
        try: self.path.chmod(0o600)
        except OSError: pass

    @contextmanager
    def db(self,write=False):
        local=self._transaction_local
        existing=getattr(local,'connection',None)
        if existing is not None:
            if write and not local.write:
                local.failed=True
                raise RuntimeError('不能把已有只读事务升级为写事务')
            try: yield existing
            except Exception:
                local.failed=True;raise
            return
        c=sqlite3.connect(str(self.path),timeout=20)
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA busy_timeout=20000')
        try:
            c.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            local.connection=c;local.write=write;local.failed=False
            yield c
            if local.failed:raise RuntimeError('嵌套状态操作失败，整轮事务已回滚')
            c.commit()
        except Exception:
            c.rollback(); raise
        finally:
            local.connection=None;local.write=False;local.failed=False;c.close()

    def _scope(self,c,owner,subject=None):
        row=c.execute('SELECT * FROM owners WHERE id=?',(owner,)).fetchone()
        if not row: raise ScopeError('用户身份未绑定')
        if subject is not None:
            sub=c.execute('SELECT * FROM subjects WHERE owner=? AND id=?',(owner,subject)).fetchone()
            if not sub: raise ScopeError('人物不属于当前用户')
            if sub['consent']!='granted': raise ScopeError('人物资料尚未获准使用')
        return row

    def _revision(self,c,owner,expected=None):
        current=self._scope(c,owner)['revision']
        if expected is not None and current!=expected: raise RevisionConflict('资料已发生变化，请读取最新版本后重试')
        return current

    def _bump(self,c,owner):
        c.execute('UPDATE owners SET revision=revision+1 WHERE id=?',(owner,))
        return c.execute('SELECT revision FROM owners WHERE id=?',(owner,)).fetchone()[0]

    def _audit(self,c,owner,etype,eid,op,rev):
        c.execute('INSERT INTO audit(owner,entity_type,entity_id,operation,revision,at) VALUES(?,?,?,?,?,?)',(owner,etype,eid,op,rev,now()))

    def ensure_owner(self,owner,subject='self',label='本人',settings=None):
        if not isinstance(owner,str) or not owner.strip(): raise ValueError('需要明确用户标识')
        with self.db(True) as c:
            c.execute('INSERT OR IGNORE INTO owners VALUES(?,?,?,?)',(owner,0,dumps(settings or {'auto_save_low_sensitivity':True}),now()))
            c.execute('INSERT OR IGNORE INTO subjects VALUES(?,?,?,?,?)',(owner,subject,label,'granted',now()))
            return {'owner_user_id':owner,'subject_id':subject,'revision':self._revision(c,owner)}

    def create_subject(self,owner,id,label,consent='granted'):
        if consent not in ('granted','pending','revoked'): raise ValueError('授权状态无效')
        with self.db(True) as c:
            self._scope(c,owner)
            old=c.execute('SELECT * FROM subjects WHERE owner=? AND id=?',(owner,id)).fetchone()
            if old:
                if old['label']!=label or old['consent']!=consent: raise ValueError('人物标识已使用')
                return dict(old)
            c.execute('INSERT INTO subjects VALUES(?,?,?,?,?)',(owner,id,label,consent,now()))
            rev=self._bump(c,owner)
            return {'owner_user_id':owner,'subject_id':id,'label':label,'consent':consent,'revision':rev}

    def bind_channel(self,owner,channel,external_id,subject='self'):
        with self.db(True) as c:
            self._scope(c,owner,subject)
            old=c.execute('SELECT * FROM channels WHERE channel=? AND external_id=?',(channel,str(external_id))).fetchone()
            if old:
                if old['owner']!=owner or old['subject']!=subject: raise ScopeError('该渠道身份已绑定其他用户或人物')
                return dict(old)
            c.execute('INSERT INTO channels VALUES(?,?,?,?,?)',(channel,str(external_id),owner,subject,now()))
            self._bump(c,owner)
            return {'owner':owner,'subject':subject,'channel':channel,'external_id':str(external_id)}

    def resolve_channel(self,channel,external_id):
        with self.db() as c:
            row=c.execute('SELECT * FROM channels WHERE channel=? AND external_id=?',(channel,str(external_id))).fetchone()
            if not row: raise ScopeError('当前渠道尚未绑定用户身份')
            self._scope(c,row['owner'],row['subject'])
            return dict(row)

    def revision(self,owner):
        with self.db() as c: return self._revision(c,owner)

    def update_settings(self,owner,settings,expected_revision):
        if not isinstance(settings,dict) or set(settings)-{'auto_save_low_sensitivity'} or any(not isinstance(v,bool) for v in settings.values()):
            raise ValueError('记忆设置字段无效')
        with self.db(True) as c:
            old=self._scope(c,owner)
            if expected_revision is None: raise RevisionConflict('修改设置需要当前版本')
            self._revision(c,owner,expected_revision)
            merged=json.loads(old['settings']);merged.update(settings)
            c.execute('UPDATE owners SET settings=? WHERE id=?',(dumps(merged),owner))
            rev=self._bump(c,owner)
            return {'settings':merged,'revision':rev}

    def _message(self,row):
        d=dict(row); d['case_ids']=json.loads(d.pop('cases'))
        d['owner_user_id']=d['owner']; d['subject_id']=d['subject']; d['message_id']=d['id']
        d['source_ref']={'message_id':d['id'],'source':d['source'],'id':d['source_id'],'version':d['version'],'role':d['role'],'subject_id':d['subject']}
        return d

    def import_message(self,owner,source,id,role,content,at=None,subject='self',case=None,channel=None,external_id=None,conversation_id='shared'):
        """Register an ORIGINAL message from a trusted authenticated adapter.

        A model cannot call this method. Adapters must read the actual channel
        record instead of trusting client-supplied author/content fields.
        """
        if role not in ('user','assistant','tool','legacy'): raise ValueError('来源作者类型无效')
        if not isinstance(content,str) or len(content)>200000: raise ValueError('原始消息格式无效')
        cases=[] if case is None else ([case] if isinstance(case,str) else list(case))
        with self.db(True) as c:
            self._scope(c,owner,subject)
            if channel is not None:
                binding=c.execute('SELECT * FROM channels WHERE channel=? AND external_id=?',(channel,str(external_id))).fetchone()
                if not binding or binding['owner']!=owner or binding['subject']!=subject: raise ScopeError('消息与渠道绑定身份不一致')
            for cid in cases: self._case(c,owner,cid,subject)
            prior=c.execute('SELECT * FROM messages WHERE owner=? AND source=? AND source_id=?',(owner,source,str(id))).fetchone()
            suppression=c.execute('SELECT * FROM suppressions WHERE owner=? AND source=? AND source_id=?',(owner,source,str(id))).fetchone()
            if prior:
                if prior['status']=='deleted': return self._message(prior)
                if prior['role']!=role or prior['subject']!=subject or prior['content']!=content: raise EvidenceError('同一来源标识不能替换原始消息')
                known=json.loads(prior['cases']);merged=list(dict.fromkeys(known+cases))
                if merged!=known:
                    c.execute('UPDATE messages SET cases=? WHERE id=?',(dumps(merged),prior['id']))
                    c.execute('INSERT OR REPLACE INTO conversation_scope VALUES(?,?,?,?,?)',(owner,subject,conversation_id,dumps(merged),now()))
                    self._bump(c,owner)
                    prior=c.execute('SELECT * FROM messages WHERE id=?',(prior['id'],)).fetchone()
                return self._message(prior)
            mid='msg_'+digest(owner,source,str(id))[:32]
            purged=bool(suppression and suppression['purge_message'])
            c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(mid,owner,subject,source,str(id),role,'' if purged else content,timestamp(at),now(),1,conversation_id,dumps(cases),'deleted' if purged else 'active'))
            if cases:
                c.execute('INSERT OR REPLACE INTO conversation_scope VALUES(?,?,?,?,?)',(owner,subject,conversation_id,dumps(cases),now()))
            self._bump(c,owner)
            return self._message(c.execute('SELECT * FROM messages WHERE id=?',(mid,)).fetchone())

    def get_message(self,owner,id,include_suppressed=False):
        with self.db() as c:
            self._scope(c,owner)
            row=c.execute('SELECT * FROM messages WHERE owner=? AND id=?',(owner,id)).fetchone()
            if not row: raise ScopeError('来源不属于当前用户')
            if not include_suppressed and (row['status']!='active' or self._suppressed(c,owner,row['source'],row['source_id'])):
                raise EvidenceError('来源已停止使用或删除')
            return self._message(row)

    def _suppressed(self,c,owner,source,source_id):
        return c.execute('SELECT 1 FROM suppressions WHERE owner=? AND source=? AND source_id=?',(owner,source,str(source_id))).fetchone() is not None

    def _refs(self,c,owner,subject,refs,assertion,content=None):
        if assertion not in ASSERTIONS: raise ValueError('断言类别无效')
        if not isinstance(refs,list) or not refs: raise EvidenceError('需要可核验的原始来源')
        parsed=[]
        for ref in refs:
            if not isinstance(ref,dict): raise EvidenceError('来源引用格式无效')
            if ref.get('message_id'):
                row=c.execute('SELECT * FROM messages WHERE owner=? AND id=?',(owner,ref['message_id'])).fetchone()
            else:
                row=c.execute('SELECT * FROM messages WHERE owner=? AND source=? AND source_id=?',(owner,ref.get('source'),str(ref.get('id',ref.get('source_id',''))))).fetchone()
            if not row or row['subject']!=subject: raise ScopeError('来源作者或人物范围未授权')
            if row['status']!='active' or self._suppressed(c,owner,row['source'],row['source_id']): raise EvidenceError('来源已停止使用，不能重新导入')
            if ref.get('version',row['version'])!=row['version']: raise EvidenceError('来源版本已失效')
            if assertion in USER_ASSERTIONS and row['role']!='user': raise EvidenceError('助手解释和工具记录不能升级为用户事实')
            if assertion=='tool_observation' and row['role']!='tool': raise EvidenceError('工具观察必须来自工具原始记录')
            quote=ref.get('quote')
            if not isinstance(quote,str) or not quote or quote not in row['content']: raise EvidenceError('引用必须逐字对应原始消息')
            start=ref.get('start',row['content'].find(quote)); end=ref.get('end',start+len(quote))
            if not isinstance(start,int) or not isinstance(end,int) or row['content'][start:end]!=quote: raise EvidenceError('来源文本范围不匹配')
            parsed.append({'message_id':row['id'],'source':row['source'],'id':row['source_id'],'role':row['role'],
                           'subject_id':subject,'version':row['version'],'start':start,'end':end,'quote':quote,'at':row['at']})
        if content is not None and assertion in USER_ASSERTIONS and not any(content==r['quote'] for r in parsed):
            raise EvidenceError('用户事实正文必须是已核验原话，不能保存模型改写')
        return parsed

    def _fact(self,row):
        d=dict(row);d['source_refs']=json.loads(d['source_refs']);d['value']=json.loads(d.pop('value_json')) if d.get('value_json') is not None else None
        d['owner_user_id']=d['owner'];d['subject_id']=d['subject'];return d

    def put_fact(self,owner,subject,content,source_refs,kind='preference',assertion_status='user_asserted',case_id=None,
                 valid_from=None,valid_to=None,consent='granted',retention='until_revoked',idempotency_key=None,
                 supersedes_id=None,expected_revision=None,field=None,value=None,explicit=False):
        if kind not in FACT_KINDS: raise ValueError('记忆类型无效')
        if not isinstance(content,str) or not 1<=len(content)<=3000: raise ValueError('记忆正文长度无效')
        if consent not in ('granted','pending','revoked'): raise ValueError('授权状态无效')
        start=timestamp(valid_from) if valid_from else None; end=timestamp(valid_to) if valid_to else None
        if start and end and start>=end: raise ValueError('有效时间区间无效')
        request=dumps([subject,content,source_refs,kind,assertion_status,case_id,start,end,consent,retention,supersedes_id,field,value])
        key=idempotency_key or digest(request)
        with self.db(True) as c:
            scope=self._scope(c,owner,subject)
            existing=c.execute('SELECT * FROM facts WHERE owner=? AND request_key=?',(owner,key)).fetchone()
            if existing:
                if existing['request_hash']!=digest(request): raise ValueError('幂等键已用于其他记忆变更')
                return self._fact(existing)
            self._revision(c,owner,expected_revision)
            refs=self._refs(c,owner,subject,source_refs,assertion_status,content)
            start=start or min(r['at'] for r in refs)
            if case_id: self._case(c,owner,case_id,subject)
            if assertion_status in USER_ASSERTIONS:
                quotes=' '.join(r['quote'] for r in refs)
                if assertion_status=='user_confirmed' and not explicit: raise EvidenceError('用户确认类别需要明确确认操作')
                if kind not in ('concern','hearsay','hypothesis') and re.search(r'假如|假设|如果我|举个例子|比如说|也许|可能会|[？?]',content):
                    raise EvidenceError('疑问、担忧或假设不能作为已经发生的个人事实')
                if not explicit and (subject!='self' or kind in ('profile','background') or re.search(r'出生|病历|诊断|创伤|自杀|性经历|身份证|银行卡',content)):
                    raise EvidenceError('敏感资料或第三人资料需要明确保存授权')
                if not explicit and not json.loads(scope['settings']).get('auto_save_low_sensitivity',True): raise EvidenceError('用户已关闭自动长期记忆')
            if field and assertion_status in USER_ASSERTIONS:
                source_text=' '.join(r['quote'] for r in refs)
                if isinstance(value,(dict,list)) or not any(v in source_text for v in (str(value),dumps(value))): raise EvidenceError('结构化档案值必须可回查用户原话')
            old=None
            if supersedes_id:
                if expected_revision is None: raise RevisionConflict('更正必须携带已读取的资料版本')
                old=c.execute('SELECT * FROM facts WHERE owner=? AND id=?',(owner,supersedes_id)).fetchone()
                if not old or old['subject']!=subject or old['status']!='active': raise EvidenceError('被更正事实不存在或已失效')
                if assertion_status not in USER_ASSERTIONS or not explicit or not any(re.search(r'不是|更正|纠正|改为|现在|不再|其实|修改|更新',r['quote']) for r in refs): raise EvidenceError('替换旧事实需要本次明确更正')
                if start and start<old['valid_from']: raise EvidenceError('补记旧事不能替换较新的当前状态')
                if any(any((r['source'],r['id'])==(s['source'],s['id']) for s in refs) for r in json.loads(old['source_refs'])):
                    raise EvidenceError('更正需要新的原始用户陈述，不能重用旧消息改写事实')
            start=start or min(r['at'] for r in refs)
            if end and start>=end: raise ValueError('有效时间区间无效')
            fid=ident('fact');rev=self._bump(c,owner)
            if old:
                c.execute("UPDATE facts SET status='superseded',valid_to=?,revision=? WHERE id=?",(start,rev,old['id']))
                old_refs=json.loads(old['source_refs'])
                for old_ref in old_refs:
                    self._suppress(c,owner,old_ref['source'],old_ref['id'],'superseded')
                for ca in c.execute('SELECT * FROM cases WHERE owner=? AND subject=?',(owner,subject)).fetchall():
                    case_refs=json.loads(ca['source_refs'])
                    remaining=[r for r in case_refs if not any((r['source'],r['id'])==(s['source'],s['id']) for s in old_refs)]
                    if len(remaining)!=len(case_refs):
                        c.execute('UPDATE cases SET state=?,source_refs=?,revision=?,updated_at=? WHERE id=?',
                                  (dumps({'pending':['事项背景已更正，请以最新有效记忆为准']}),dumps(case_refs),rev,now(),ca['id']))
                self._audit(c,owner,'fact',old['id'],'superseded',rev)
            status='active' if consent=='granted' else 'pending' if consent=='pending' else 'stopped'
            c.execute('INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (fid,owner,subject,case_id,kind,content,dumps(refs),assertion_status,start,end,now(),supersedes_id,rev,consent,retention,status,field,dumps(value) if value is not None else None,key,digest(request)))
            self._audit(c,owner,'fact',fid,'created',rev)
            return self._fact(c.execute('SELECT * FROM facts WHERE id=?',(fid,)).fetchone())

    def get_fact(self,owner,id):
        with self.db() as c:
            self._scope(c,owner)
            row=c.execute('SELECT * FROM facts WHERE owner=? AND id=?',(owner,id)).fetchone()
            if not row: raise ScopeError('记忆不属于当前用户')
            return self._fact(row)

    def _facts(self,c,owner,subject,case=None,at=None,include_inactive=False):
        when=timestamp(at)
        rows=c.execute('SELECT * FROM facts WHERE owner=? AND subject=? ORDER BY recorded_at,id',(owner,subject)).fetchall()
        result=[]
        for row in rows:
            if case is not None and row['case_id'] not in (None,case): continue
            if not include_inactive:
                statuses=('active','superseded') if at else ('active',)
                if row['status'] not in statuses or row['consent']!='granted': continue
                if row['valid_from']>when or (row['valid_to'] and row['valid_to']<=when): continue
                blocked=False
                for ref in json.loads(row['source_refs']):
                    suppression=c.execute('SELECT reason FROM suppressions WHERE owner=? AND source=? AND source_id=?',(owner,ref['source'],ref['id'])).fetchone()
                    if suppression and not (at and suppression['reason']=='superseded' and row['status']=='superseded'):
                        blocked=True;break
                if blocked: continue
            result.append(self._fact(row))
        return result

    def list_facts(self,owner,subject='self',case=None,at=None,include_inactive=False):
        with self.db() as c:
            self._scope(c,owner,subject)
            if case: self._case(c,owner,case,subject)
            return self._facts(c,owner,subject,case,at,include_inactive)

    def _suppress(self,c,owner,source,source_id,reason,purge=False):
        c.execute('INSERT INTO suppressions VALUES(?,?,?,?,?,?) ON CONFLICT(owner,source,source_id) DO UPDATE SET reason=excluded.reason,purge_message=MAX(purge_message,excluded.purge_message),at=excluded.at',
                  (owner,source,str(source_id),reason,int(purge),now()))
        if purge: c.execute("UPDATE messages SET content='',status='deleted' WHERE owner=? AND source=? AND source_id=?",(owner,source,str(source_id)))

    def suppress_source(self,owner,source,id,reason='legacy_stopped',purge_message=False):
        with self.db(True) as c:
            self._scope(c,owner)
            old=c.execute('SELECT * FROM suppressions WHERE owner=? AND source=? AND source_id=?',(owner,source,str(id))).fetchone()
            if not old or (purge_message and not old['purge_message']):
                self._suppress(c,owner,source,id,reason,purge_message);rev=self._bump(c,owner)
                for fact in c.execute('SELECT * FROM facts WHERE owner=?',(owner,)).fetchall():
                    refs=json.loads(fact['source_refs'])
                    if any((r['source'],r['id'])==(source,str(id)) for r in refs):
                        status='deleted' if purge_message else 'stopped'
                        clean=[{k:v for k,v in r.items() if k!='quote'} for r in refs] if purge_message else refs
                        c.execute('UPDATE facts SET status=?,content=?,source_refs=?,value_json=?,revision=? WHERE id=?',
                                  (status,'' if purge_message else fact['content'],dumps(clean),None if purge_message else fact['value_json'],rev,fact['id']))
                        c.execute('INSERT OR REPLACE INTO tombstones VALUES(?,?,?,?,?,?)',(owner,'fact',fact['id'],status,rev,now()))
                        self._audit(c,owner,'fact',fact['id'],status,rev)
                for ca in c.execute('SELECT * FROM cases WHERE owner=?',(owner,)).fetchall():
                    if any((r['source'],r['id'])==(source,str(id)) for r in json.loads(ca['source_refs'])):
                        c.execute('UPDATE cases SET title=?,state=?,source_refs=?,revision=?,updated_at=? WHERE id=?',
                                  ('待重新确认的事项' if purge_message else ca['title'],dumps({'pending':['旧来源已停止使用']}),'[]' if purge_message else ca['source_refs'],rev,now(),ca['id']))
                for event in c.execute('SELECT * FROM case_events WHERE owner=?',(owner,)).fetchall():
                    if any((r['source'],r['id'])==(source,str(id)) for r in json.loads(event['source_refs'])):
                        c.execute('DELETE FROM case_events WHERE id=?',(event['id'],))

    def _retire_fact(self,owner,id,expected_revision,delete=False,scope='fact'):
        if scope not in ('fact','source'): raise ValueError('删除范围无效')
        with self.db(True) as c:
            self._scope(c,owner)
            row=c.execute('SELECT * FROM facts WHERE owner=? AND id=?',(owner,id)).fetchone()
            if not row: raise ScopeError('记忆不属于当前用户')
            target='deleted' if delete else 'stopped'
            prior_refs=json.loads(row['source_refs'])
            needs_purge=delete and scope=='source' and any(not c.execute('SELECT 1 FROM suppressions WHERE owner=? AND source=? AND source_id=? AND purge_message=1',(owner,r['source'],r['id'])).fetchone() for r in prior_refs)
            if row['status']==target and not needs_purge: return self._fact(row)
            if expected_revision is None: raise RevisionConflict('停止使用或删除需要当前版本')
            self._revision(c,owner,expected_revision)
            refs=json.loads(row['source_refs']);rev=self._bump(c,owner)
            for ref in refs: self._suppress(c,owner,ref['source'],ref['id'],target,delete and scope=='source')
            # Purge all derived copies backed by a forgotten source, including
            # old revisions and case events; audit retains identifiers only.
            for fact in c.execute('SELECT * FROM facts WHERE owner=?',(owner,)).fetchall():
                fr=json.loads(fact['source_refs'])
                if fact['id']==id or any(any((r['source'],r['id'])==(s['source'],s['id']) for s in refs) for r in fr):
                    clean=[{k:v for k,v in r.items() if k not in ('quote',)} for r in fr] if delete else fr
                    c.execute('UPDATE facts SET status=?,content=?,value_json=?,source_refs=?,revision=? WHERE id=?',
                              (target,'' if delete else fact['content'],None if delete else fact['value_json'],dumps(clean),rev,fact['id']))
                    c.execute('INSERT OR REPLACE INTO tombstones VALUES(?,?,?,?,?,?)',(owner,'fact',fact['id'],target,rev,now()))
            for event in c.execute('SELECT * FROM case_events WHERE owner=?',(owner,)).fetchall():
                er=json.loads(event['source_refs'])
                if any(any((r['source'],r['id'])==(s['source'],s['id']) for s in refs) for r in er):
                    c.execute('DELETE FROM case_events WHERE id=?',(event['id'],))
            # Case snapshots can contain a derived paraphrase; invalidate them
            # rather than retaining a potentially forgotten claim in another layer.
            for ca in c.execute('SELECT * FROM cases WHERE owner=?',(owner,)).fetchall():
                cr=json.loads(ca['source_refs'])
                if any(any((r['source'],r['id'])==(s['source'],s['id']) for s in refs) for r in cr):
                    c.execute('UPDATE cases SET title=?,state=?,source_refs=?,revision=?,updated_at=? WHERE id=?',('待重新确认的事项' if delete else ca['title'],dumps({'pending':['资料已停止使用，请重新确认事项背景']}),'[]' if delete else ca['source_refs'],rev,now(),ca['id']))
            self._audit(c,owner,'fact',id,target,rev)
            return self._fact(c.execute('SELECT * FROM facts WHERE id=?',(id,)).fetchone())

    def stop_fact(self,owner,id,expected_revision,scope='fact'): return self._retire_fact(owner,id,expected_revision,False,scope)
    def delete_fact(self,owner,id,expected_revision,scope='fact'): return self._retire_fact(owner,id,expected_revision,True,scope)

    def _case(self,c,owner,id,subject=None):
        row=c.execute('SELECT * FROM cases WHERE owner=? AND id=?',(owner,id)).fetchone()
        if not row or (subject is not None and row['subject']!=subject): raise ScopeError('事项不属于当前人物')
        return row

    def _case_dict(self,row):
        d=dict(row);d['state']=json.loads(d['state']);d['source_refs']=json.loads(d['source_refs'])
        d['owner_user_id']=d['owner'];d['subject_id']=d['subject'];return d

    def create_case(self,owner,subject,title,source_refs=None,conversation_id='shared',case_id=None,idempotency_key=None,goal=''):
        if not isinstance(title,str) or not 1<=len(title)<=120: raise ValueError('事项名称长度无效')
        key=idempotency_key or digest(subject,title,source_refs or [])
        with self.db(True) as c:
            self._scope(c,owner,subject)
            row=c.execute('SELECT * FROM cases WHERE owner=? AND request_key=?',(owner,key)).fetchone()
            if row:
                if row['title']!=title or row['subject']!=subject: raise ValueError('幂等键已用于其他事项')
                return self._case_dict(row)
            refs=self._refs(c,owner,subject,source_refs,'user_asserted') if source_refs else []
            if goal and not any(goal in r['quote'] for r in refs): raise EvidenceError('事项目标需要用户原始陈述')
            cid=case_id or ident('case');rev=self._bump(c,owner);time=now()
            c.execute('INSERT INTO cases VALUES(?,?,?,?,?,?,?,?,?,?,?)',(cid,owner,subject,title,dumps({'goal':goal,'pending':[]}), 'open',dumps(refs),time,time,rev,key))
            c.execute('INSERT OR REPLACE INTO conversation_scope VALUES(?,?,?,?,?)',(owner,subject,conversation_id,dumps([cid]),time))
            self._audit(c,owner,'case',cid,'created',rev)
            return self._case_dict(c.execute('SELECT * FROM cases WHERE id=?',(cid,)).fetchone())

    def update_case(self,owner,case_id,changes,source_refs,expected_revision,explicit=False):
        if not isinstance(changes,dict) or not changes or set(changes)-CASE_FIELDS: raise ValueError('事项变更字段无效')
        if 'title' in changes and (not isinstance(changes['title'],str) or not 1<=len(changes['title'])<=120): raise ValueError('事项名称长度无效')
        with self.db(True) as c:
            old=self._case(c,owner,case_id);self._scope(c,owner,old['subject']);self._revision(c,owner,expected_revision)
            if expected_revision is None: raise RevisionConflict('事项变更需要当前版本')
            refs=self._refs(c,owner,old['subject'],source_refs,'user_asserted')
            if not explicit:
                text=' '.join(r['quote'] for r in refs)
                def strings(v):
                    if isinstance(v,str): return [v]
                    if isinstance(v,list): return [s for x in v for s in strings(x)]
                    if isinstance(v,dict): return [s for x in v.values() for s in strings(x)]
                    return []
                if any(s not in text for k,v in changes.items() if k!='status' for s in strings(v)): raise EvidenceError('事项事实必须来自用户原话；模型不能推断已决定或已执行')
            status=changes.get('status',old['status'])
            if status not in ('open','closed','paused'): raise ValueError('事项状态无效')
            state=json.loads(old['state']);state.update({k:v for k,v in changes.items() if k not in ('status','title')})
            rev=self._bump(c,owner)
            c.execute('UPDATE cases SET title=?,state=?,status=?,source_refs=?,revision=?,updated_at=? WHERE id=?',(changes.get('title',old['title']),dumps(state),status,dumps(json.loads(old['source_refs'])+refs),rev,now(),case_id))
            self._audit(c,owner,'case',case_id,'updated',rev)
            return self._case_dict(c.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone())

    def add_case_event(self,owner,case_id,kind,content,source_refs,*,idempotency_key=None,expected_revision=None,occurred_at=None,assertion_status='user_asserted'):
        if kind not in ('discussed','decided','action_planned','action_started','completed','feedback','draw','closed','reopened','interpretation'): raise ValueError('事项事件类型无效')
        if kind in ('decided','action_started','completed','feedback') and assertion_status not in USER_ASSERTIONS: raise EvidenceError('建议或工具解释不能作为用户已执行的事件')
        key=idempotency_key or digest(case_id,kind,content,source_refs,occurred_at)
        with self.db(True) as c:
            ca=self._case(c,owner,case_id);self._scope(c,owner,ca['subject'])
            existing=c.execute('SELECT * FROM case_events WHERE owner=? AND request_key=?',(owner,key)).fetchone()
            if existing:
                if existing['case_id']!=case_id or existing['kind']!=kind or existing['content']!=content: raise ValueError('幂等键已用于其他事项事件')
                return dict(existing,source_refs=json.loads(existing['source_refs']))
            self._revision(c,owner,expected_revision)
            refs=self._refs(c,owner,ca['subject'],source_refs,assertion_status,content)
            eid=ident('event');rev=self._bump(c,owner)
            c.execute('INSERT INTO case_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(eid,owner,ca['subject'],case_id,kind,content,dumps(refs),assertion_status,timestamp(occurred_at) if occurred_at else min(r['at'] for r in refs),now(),rev,key))
            self._audit(c,owner,'case_event',eid,'created',rev)
            return dict(c.execute('SELECT * FROM case_events WHERE id=?',(eid,)).fetchone(),source_refs=refs)

    def get_case(self,owner,id):
        with self.db() as c:
            row=self._case(c,owner,id);self._scope(c,owner,row['subject']);result=self._case_dict(row)
            result['events']=[dict(r,source_refs=json.loads(r['source_refs'])) for r in c.execute('SELECT * FROM case_events WHERE owner=? AND case_id=? ORDER BY occurred_at,recorded_at',(owner,id))]
            return result

    def list_cases(self,owner,subject='self',include_closed=False):
        with self.db() as c:
            self._scope(c,owner,subject)
            return [self._case_dict(r) for r in c.execute('SELECT * FROM cases WHERE owner=? AND subject=?'+('' if include_closed else " AND status='open'")+' ORDER BY updated_at DESC,id',(owner,subject))]

    def resolve_cases(self,owner,subject,message,conversation_id='shared',case_ids=None):
        with self.db() as c:
            self._scope(c,owner,subject)
            cases=[dict(r) for r in c.execute('SELECT * FROM cases WHERE owner=? AND subject=? AND status!=?',(owner,subject,'deleted'))]
            available={r['id']:r for r in cases}
            chosen=[];reason='no_reference';ambiguous=False
            if case_ids:
                chosen=[case_ids] if isinstance(case_ids,str) else list(case_ids)
                for cid in chosen: self._case(c,owner,cid,subject)
                reason='explicit_ids'
            else:
                chosen=[r['id'] for r in cases if r['title'] and r['title'] in message]
                if chosen: reason='explicit_title'
                elif re.search(r'这件事|刚才|继续|后来|第[一二三四五12345]张|我.*选了|那件事|上次|之前',message):
                    recent=c.execute('SELECT case_ids FROM conversation_scope WHERE owner=? AND subject=? AND conversation_id=?',(owner,subject,conversation_id)).fetchone()
                    previous=[cid for cid in json.loads(recent[0]) if cid in available] if recent else []
                    if len(previous)==1 and not (re.search(r'之前那|更早|另一个',message) and len(cases)>1):
                        chosen=previous;reason='conversation_reference'
                    elif len(cases)==1: chosen=[cases[0]['id']];reason='only_case_reference'
                    else: ambiguous=True;reason='ambiguous_reference'
            return {'case_id':chosen[0] if len(chosen)==1 else None,'case_ids':chosen,'reason':reason,
                    'needs_clarification':ambiguous,'candidates':[{'id':r['id'],'title':r['title']} for r in cases] if ambiguous else []}

    def _profile(self,facts):
        result={};conflicts={}
        for fact in facts:
            if not fact['field'] or fact['assertion_status'] not in USER_ASSERTIONS or fact['kind'] not in ('profile','preference','constraint','correction'): continue
            name=fact['field']
            if name in result and result[name]!=fact['value']: conflicts[name]=True
            else: result[name]=fact['value']
        # Competing active assertions are not last-write-wins. Ask the caller to
        # resolve a conflict instead of silently replacing a birth date or name.
        for key in conflicts: result.pop(key,None)
        return result, list(conflicts)

    def profile(self,owner,subject='self',at=None):
        with self.db() as c:
            self._scope(c,owner,subject)
            facts=self._facts(c,owner,subject,at=at);profile,conflicts=self._profile(facts)
            return {'values':profile,'conflicts':conflicts,'source_fact_ids':[f['id'] for f in facts if f['field'] and f['assertion_status'] in USER_ASSERTIONS],'revision':self._revision(c,owner)}

    def snapshot(self,owner,subject='self',case=None,at=None):
        with self.db() as c:
            self._scope(c,owner,subject)
            if case: self._case(c,owner,case,subject)
            facts=self._facts(c,owner,subject,case,at);profile,conflicts=self._profile(facts)
            cases=[self._case_dict(r) for r in c.execute('SELECT * FROM cases WHERE owner=? AND subject=?'+(' AND id=?' if case else " AND status='open'")+' ORDER BY updated_at DESC',(owner,subject,case) if case else (owner,subject))]
            for ca in cases:
                ca['source_refs']=[r for r in ca['source_refs'] if not self._suppressed(c,owner,r['source'],r['id'])]
                if at and ca['updated_at']>timestamp(at):
                    ca['state']={'pending':['此事项没有该历史时刻的状态快照，请参考当时的来源事件']}
                    ca['historical_state_unavailable']=True
                ca['events']=[]
                for event in c.execute('SELECT * FROM case_events WHERE owner=? AND case_id=? AND occurred_at<=? ORDER BY occurred_at,recorded_at',(owner,ca['id'],timestamp(at))):
                    event_refs=json.loads(event['source_refs'])
                    if any(self._suppressed(c,owner,r['source'],r['id']) for r in event_refs): continue
                    ca['events'].append(dict(event,source_refs=event_refs))
            suppressed=[dict(r) for r in c.execute('SELECT source,source_id,reason,purge_message FROM suppressions WHERE owner=?',(owner,))]
            return {'owner_user_id':owner,'subject_id':subject,'subject':dict(c.execute('SELECT * FROM subjects WHERE owner=? AND id=?',(owner,subject)).fetchone()),
                    'revision':self._revision(c,owner),'facts':facts,'cases':cases,'profile':profile,'profile_conflicts':conflicts,
                    'suppressed_sources':suppressed,
                    'invalidated_derived_sources':['archive:user','archive:conversation_state','archive:calibration','legacy_unverified','old_reports_without_lineage'] if suppressed else [],
                    'settings':json.loads(self._scope(c,owner)['settings']),'as_of':timestamp(at)}

    def record_trace(self,owner,run_id,data,subject='self',case=None,retention_days=None):
        # Prune this owner's metadata on writes; no trace bodies enter logs.
        import os
        from datetime import timedelta
        configured=retention_days if retention_days is not None else os.environ.get('ZHIMING_TRACE_RETENTION_DAYS','30')
        if isinstance(configured,bool) or not re.fullmatch(r'[0-9]+',str(configured)) or not 1<=int(configured)<=3650:
            raise ValueError('执行记录保留天数必须在 1 至 3650 之间')
        recorded_at=now()
        cutoff=(datetime.fromisoformat(recorded_at)-timedelta(days=int(configured))).isoformat(timespec='microseconds')
        allowed={'revision','recall_ids','injected_ids','excluded','budget','write_status','validation','status','latency_ms','token_usage'}
        def clean(value,depth=0):
            if depth>5: return None
            if isinstance(value,dict):
                return {str(k)[:80]:clean(v,depth+1) for k,v in value.items()
                        if not re.search(r'body|content|prompt|answer|text|quote|secret|password|credential|token_key|api_key|authorization|thinking|reasoning|chain',str(k),re.I)}
            if isinstance(value,list): return [clean(x,depth+1) for x in value[:200]]
            if isinstance(value,(int,float,bool)) or value is None: return value
            # Trace strings are bounded codes/identifiers, never prose bodies.
            return str(value)[:160]
        payload={k:clean(v) for k,v in data.items() if k in allowed}
        with self.db(True) as c:
            self._scope(c,owner,subject)
            if case: self._case(c,owner,case,subject)
            payload.setdefault('revision',self._revision(c,owner))
            c.execute('DELETE FROM traces WHERE owner=? AND created_at<?',(owner,cutoff))
            c.execute('INSERT OR REPLACE INTO traces VALUES(?,?,?,?,?,?)',(owner,run_id,subject,case,dumps(payload),recorded_at))
        return {'run_id':run_id,**payload}

    def get_trace(self,owner,run_id):
        with self.db() as c:
            self._scope(c,owner)
            row=c.execute('SELECT * FROM traces WHERE owner=? AND run_id=?',(owner,run_id)).fetchone()
            if not row: raise ScopeError('执行记录不属于当前用户')
            return dict(row,payload=json.loads(row['payload']))

    def map_legacy(self,owner,source,legacy_id,entity_type,new_id=None,status='imported'):
        with self.db(True) as c:
            self._scope(c,owner)
            c.execute('INSERT OR IGNORE INTO legacy_map VALUES(?,?,?,?,?,?)',(owner,source,str(legacy_id),entity_type,new_id,status))

    def legacy_mapping(self,owner,source,legacy_id,entity_type):
        with self.db() as c:
            self._scope(c,owner)
            row=c.execute('SELECT * FROM legacy_map WHERE owner=? AND source=? AND legacy_id=? AND entity_type=?',(owner,source,str(legacy_id),entity_type)).fetchone()
            return dict(row) if row else None
