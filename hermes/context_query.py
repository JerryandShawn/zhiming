"""Bound-channel access to shared state. Never accepts arbitrary author/role writes."""
import argparse,json,os,sqlite3,uuid
from datetime import datetime,timezone
from pathlib import Path
from archive_store import read_json
from state_store import StateStore,ScopeError,EvidenceError,RevisionConflict
from domain_context import profile_archive,store_candidate,memory_view
from context_builder import ContextBuilder
from context_engine import terms,choose_date


class StateSearch:
    """Owner-scoped lexical fallback; callers may inject their scoped semantic index."""
    def __init__(self,state,owner,subject): self.state,self.owner,self.subject=state,owner,subject
    def search(self,query,limit=10):
        wanted=terms(query);result=[]
        with self.state.db() as c:
            self.state._scope(c,self.owner,self.subject)
            rows=c.execute("SELECT * FROM messages WHERE owner=? AND subject=? AND role='user' AND status='active' ORDER BY at DESC LIMIT 20000",(self.owner,self.subject))
            for row in rows:
                if self.state._suppressed(c,self.owner,row['source'],row['source_id']):continue
                score=len(wanted & terms(row['content']))
                if not score:continue
                result.append({'id':'source:'+row['id'],'source':'history.'+row['source'],'record_id':row['source_id'],
                               'source_id':row['source']+':'+row['source_id'],'owner_user_id':self.owner,'subject_id':self.subject,
                               'text':row['content'],'data':{'role':'user','content':row['content'],'at':row['at']},'score':score})
        return sorted(result,key=lambda x:x['score'],reverse=True)[:limit]


class ChannelContext:
    def __init__(self,base,hermes_db=None,index=None):
        self.base=Path(base);self.state=StateStore(base)
        self.hermes_db=Path(hermes_db or os.environ.get('HERMES_DB','/root/.hermes/state.db'));self.index=index

    def identity(self,channel,external_id):
        if not channel or not external_id:raise ScopeError('需要已绑定的 channel 和 external_id，不能猜测用户身份')
        return self.state.resolve_channel(channel,str(external_id))

    def _hermes_rows(self,channel,external_id,binding_kind='user',message_id=None):
        if binding_kind not in ('user','chat'):raise ValueError('绑定方式仅支持 user 或 chat')
        if not self.hermes_db.is_file():raise EvidenceError('Hermes 原始消息库不可用')
        c=sqlite3.connect(self.hermes_db.resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
        try:
            sc={r[1] for r in c.execute('PRAGMA table_info(sessions)')};mc={r[1] for r in c.execute('PRAGMA table_info(messages)')}
            if not {'id','source','user_id','chat_id','chat_type'}<=sc or not {'id','session_id','role','content','timestamp','active'}<=mc:
                raise EvidenceError('Hermes 缺少可核验身份字段，拒绝按全库私聊猜测归属')
            field='user_id' if binding_kind=='user' else 'chat_id'
            if binding_kind=='chat':
                authors={str(r[0] or '').strip() for r in c.execute("SELECT DISTINCT user_id FROM sessions WHERE source=? AND chat_type='dm' AND chat_id=?",(channel,str(external_id)))}
                if len(authors)!=1 or '' in authors:raise ScopeError('该私聊绑定无法唯一确认原始作者')
            query="SELECT m.id,m.role,m.content,m.timestamp,s.id AS session_id,s.user_id,s.chat_id FROM messages m JOIN sessions s ON s.id=m.session_id WHERE s.source=? AND s.chat_type='dm' AND s."+field+"=? AND m.active=1 AND m.role IN ('user','assistant')"
            args=[channel,str(external_id)]
            if message_id is not None:query+=' AND m.id=?';args.append(message_id)
            rows=[dict(r) for r in c.execute(query+' ORDER BY m.timestamp,m.id',args)]
            if any(not str(r['user_id'] or '').strip() for r in rows):raise EvidenceError('渠道记录缺少用户标识，不能确认作者')
            if binding_kind=='chat' and len({r['user_id'] for r in rows})>1:raise ScopeError('该私聊标识对应多个作者，需要修复渠道绑定')
            return rows
        finally:c.close()

    def remember_hermes(self,message_id,quote,channel,external_id,category='偏好',supersedes=None,field=None,value=None,binding_kind='user',expected_revision=None):
        binding=self.identity(channel,external_id)
        if channel in ('web','report','cron'):raise ScopeError('此操作只接收 Hermes 渠道真实用户原话')
        rows=self._hermes_rows(channel,external_id,binding_kind,message_id)
        if len(rows)!=1 or rows[0]['role']!='user':raise EvidenceError('未找到属于该绑定身份的有效用户消息')
        row=rows[0];stamp=row['timestamp']
        if isinstance(stamp,(int,float)):stamp=datetime.fromtimestamp(stamp,timezone.utc)
        with self.state.db(True) as c:
            prior_message=c.execute('SELECT id FROM messages WHERE owner=? AND source=? AND source_id=?',(binding['owner'],channel,str(row['id'])+':user')).fetchone()
            prior=c.execute('SELECT * FROM facts WHERE owner=? AND request_key=?',(binding['owner'],'candidate:'+prior_message['id']+':'+quote)).fetchone() if prior_message else None
            kind={'偏好':'preference','约束':'constraint','背景':'background','更正':'correction','目标':'goal','事件':'event','出生资料':'profile'}.get(category)
            if prior and prior['content']==quote and prior['kind']==kind and prior['supersedes_id']==supersedes and prior['field']==field and (json.loads(prior['value_json']) if prior['value_json'] is not None else None)==value:
                result=dict(memory_view(self.state._fact(prior)),write_status='saved' if prior['status']=='active' else 'inactive')
            else:
                if supersedes:
                    if expected_revision is None:raise RevisionConflict('渠道更正需要读取上下文时取得的 --revision')
                    self.state._revision(c,binding['owner'],expected_revision)
                original=self.state.import_message(binding['owner'],channel,str(row['id'])+':user','user',str(row['content']),stamp,
                         subject=binding['subject'],channel=channel,external_id=external_id,conversation_id=str(row['session_id']))
                result=store_candidate(self.state,binding['owner'],binding['subject'],original,quote,category,supersedes,field=field,value=value,
                                       expected_revision=self.state.revision(binding['owner']) if supersedes else None)
        return dict(result,owner_user_id=binding['owner'],subject_id=binding['subject'],revision=self.state.revision(binding['owner']))

    def sync_hermes(self,channel,external_id,binding_kind='user'):
        binding=self.identity(channel,external_id);count=0
        for row in self._hermes_rows(channel,external_id,binding_kind):
            if not isinstance(row['content'],str) or not row['content'].strip():continue
            stamp=row['timestamp']
            if isinstance(stamp,(int,float)):stamp=datetime.fromtimestamp(stamp,timezone.utc)
            self.state.import_message(binding['owner'],channel,str(row['id'])+':'+row['role'],row['role'],row['content'],stamp,
                    subject=binding['subject'],channel=channel,external_id=external_id,conversation_id=str(row['session_id']))
            count+=1
        return count

    def history(self,owner,subject):
        with self.state.db() as c:
            self.state._scope(c,owner,subject);result=[]
            for row in c.execute("SELECT * FROM messages WHERE owner=? AND subject=? AND status='active' AND role IN ('user','assistant') ORDER BY at,recorded_at",(owner,subject)):
                if self.state._suppressed(c,owner,row['source'],row['source_id']):continue
                original=row['source_id'];suffix=':'+row['role'];tid=original[:-len(suffix)] if original.endswith(suffix) else original
                result.append({'role':row['role'],'content':row['content'],'source':row['source'],'source_id':row['source']+':'+original,
                               'turn_id':tid,'at':row['at'],'status':'complete','owner_user_id':owner,'subject_id':subject,'session_id':row['conversation_id']})
            return result

    def archive(self,owner,subject):
        # Unscoped old data is never guessed to belong to an arbitrary binding.
        legacy=read_json(self.base/'archive.json',{}) if os.environ.get('ZHIMING_LEGACY_OWNER')==owner else {}
        if self.state.snapshot(owner,subject).get('invalidated_derived_sources'):
            legacy={k:v for k,v in legacy.items() if k not in ('user','conversation_state','calibration','reports','daily_log')}
        return profile_archive(self.state,owner,subject,legacy)

    def prepare(self,message,channel,external_id,case_ids=None,conversation='shared',with_charts=False,date=None,sync=False,binding_kind='user',run_id=None):
        binding=self.identity(channel,external_id);owner,subject=binding['owner'],binding['subject']
        if sync:self.sync_hermes(channel,external_id,binding_kind)
        revision=self.state.revision(owner)
        builder=ContextBuilder(self.state,self.index or StateSearch(self.state,owner,subject));run_id=run_id or 'channel-'+uuid.uuid4().hex
        context,messages,evidence,meta=builder.build(owner,subject,message,self.history(owner,subject),case_ids,conversation,run_id=run_id)
        archive=self.archive(owner,subject);charts={}
        if with_charts:
            from chart_context import bundle
            date=choose_date(message,{'date':date} if date else {});charts=bundle(archive,date)
            for engine,entry in charts.items():
                ref=f'chart:{engine}:{date}';entry['ref']=ref;evidence[ref]=entry
        if self.state.revision(owner)!=revision or meta['revision']!=revision:raise RevisionConflict('准备期间资料发生变化，请重取上下文后再生成')
        return {'owner_user_id':owner,'subject_id':subject,'revision':revision,'run_id':run_id,'context':context,'messages':messages,
                'evidence':evidence,'meta':meta,'archive':archive,'charts':charts,'date':date}

    def validate_response(self,document,channel,external_id,run_id,dates,message='三盘联动回答'):
        from guidance import validate_document
        binding=self.identity(channel,external_id);owner,subject=binding['owner'],binding['subject']
        trace=self.state.get_trace(owner,run_id)
        if trace['subject']!=subject:raise ScopeError('上下文执行记录属于其他人物')
        revision=trace['payload']['revision']
        if self.state.revision(owner)!=revision:raise RevisionConflict('回答使用的资料已经变化，请刷新上下文')
        from domain_context import registered_evidence
        content=validate_document(document,self.archive(owner,subject),dates,message,registered_evidence(self.state,owner,subject,trace))
        if self.state.revision(owner)!=revision:raise RevisionConflict('校验期间资料已变化，请重新生成回答')
        return {'content':content,'owner_user_id':owner,'subject_id':subject,'revision':revision,'validated':True}


def main():
    p=argparse.ArgumentParser(description='显式渠道绑定的共享上下文与真实原话记忆')
    p.add_argument('--base',default=os.environ.get('ZHIMING_BASE',os.path.expanduser('~/.hermes/zhiming')))
    p.add_argument('--channel',default=os.environ.get('ZHIMING_CHANNEL'));p.add_argument('--external-id',default=os.environ.get('ZHIMING_EXTERNAL_ID'))
    p.add_argument('--binding-kind',choices=['user','chat'],default='user')
    p.add_argument('--query');p.add_argument('--remember-message-id');p.add_argument('--quote');p.add_argument('--category',default='偏好')
    p.add_argument('--validate',help='按当前绑定身份和共享档案验证结构化回答文件')
    p.add_argument('--run-id');p.add_argument('--dates');p.add_argument('--message',default='三盘联动回答')
    p.add_argument('--supersedes');p.add_argument('--field');p.add_argument('--value');p.add_argument('--case',action='append')
    p.add_argument('--revision',type=int,help='更正时携带准备上下文所得 revision')
    p.add_argument('--conversation',default='shared');p.add_argument('--sync-hermes',action='store_true')
    a=p.parse_args();adapter=ChannelContext(a.base)
    if a.validate:
        if not a.run_id:p.error('--validate 必须携带 --run-id')
        result=adapter.validate_response(json.loads(Path(a.validate).read_text(encoding='utf-8')),a.channel,a.external_id,a.run_id,
                                         a.dates.split(',') if a.dates else [choose_date(a.message)],a.message)
    elif a.query:result=adapter.prepare(a.query,a.channel,a.external_id,a.case,a.conversation,sync=a.sync_hermes,binding_kind=a.binding_kind)
    elif a.remember_message_id and a.quote:
        try:value=json.loads(a.value) if a.value is not None else None
        except (ValueError,TypeError):value=a.value
        result=adapter.remember_hermes(a.remember_message_id,a.quote,a.channel,a.external_id,a.category,a.supersedes,a.field,value,a.binding_kind,a.revision)
    else:p.error('需要 --query 或 --remember-message-id 与 --quote')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
