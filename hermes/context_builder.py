"""Owner-scoped live state + bounded, source-aware per-run context.

Token estimates are conservative UTF-8 estimates, never presented as provider usage.
"""
import json,os,re,time
from context_engine import terms,dump

class ContextOverflow(ValueError):pass

def estimated_tokens(value):
    text=value if isinstance(value,str) else dump(value)
    return (len(text.encode('utf-8'))+1)//2

def source_id(message):
    ident=str(message.get('turn_id') or message.get('message_id') or message.get('id') or '')
    return message.get('source','web')+':'+ident+':'+message.get('role','user')

class ContextBuilder:
    def __init__(self,state,index=None,limit=None):
        self.state=state;self.index=index
        self.limit=int(limit or os.environ.get('ZHIMING_CONTEXT_TOKENS','64000'))

    def build(self,owner,subject,message,history,case_ids=None,conversation='shared',reserved=None,run_id=None):
        start=time.monotonic();resolution=self.state.resolve_cases(owner,subject,message,conversation_id=conversation,case_ids=case_ids)
        case=resolution.get('case_id');snapshot=self.state.snapshot(owner,subject,case)
        revision=snapshot['revision'];suppressed={r['source']+':'+str(r['source_id']) for r in snapshot.get('suppressed_sources',[])}
        effective={f['id']:f for f in snapshot.get('facts',[]) if f.get('status')=='active' and f.get('consent')=='granted'}
        retired={f['id'] for f in self.state.list_facts(owner,subject,include_inactive=True) if f['id'] not in effective}
        reserve=estimated_tokens(reserved or '')+int(os.environ.get('ZHIMING_REPLY_RESERVE','18000'))
        available=self.limit-reserve
        if available<1000:raise ContextOverflow('本轮指令与回答预留超过上下文预算，请调大配置或缩小工具范围；关键资料未被静默删除')
        # snapshot sanitizes case sources/events against corrections and revocations.
        with self.state.db():
            cases=[]
            for cid in resolution.get('case_ids',[]):
                current=self.state.snapshot(owner,subject,cid)
                if current['revision']!=revision:raise ContextOverflow('读取事项期间资料已变化，请重试完整上下文')
                cases.extend(current['cases'])
        query_terms=terms(message+' '+dump(cases))
        facts=[];optional=[];excluded=[]
        for fact in snapshot.get('facts',[]):
            if fact.get('assertion_status') not in ('user_asserted','user_confirmed','tool_observation'):continue
            critical=fact.get('kind') in ('constraint','preference','correction','profile','goal') or fact.get('case_id') in resolution.get('case_ids',[]) or bool(fact.get('supersedes_id'))
            if critical:facts.append(fact)
            elif query_terms & terms(fact.get('content','')):optional.append(fact)
        pinned={'revision':revision,'subject_id':subject,'case_resolution':resolution,'cases':cases,
                'effective_facts':[dict(f,ref='fact:'+f['id']) for f in facts],'profile':snapshot.get('profile',{}),
                'rules':'只有有效的用户陈述/确认是现实依据；历史助手解释、报告与牌意不升级为事实。当前更正和否定约束优先。'}
        used=estimated_tokens(pinned)+estimated_tokens(message)
        if used>available:raise ContextOverflow('关键约束与当前事项超过本轮预算，已保留全部来源，请缩小当前事项范围；未发送不完整上下文')
        injected=[f['id'] for f in facts];evidence={}
        for f in facts+optional:
            if f in optional:
                cost=estimated_tokens(f)
                if used+cost>available//2:
                    excluded.append({'id':f['id'],'reason':'optional_budget'});continue
                pinned['effective_facts'].append(dict(f,ref='fact:'+f['id']));used+=cost;injected.append(f['id'])
            evidence['fact:'+f['id']]={'source':'memory','record_id':f['id'],'data':f,'revision':revision}
        valid_history=[]
        for m in history:
            sid=source_id(m)
            if sid in suppressed or m.get('owner_user_id',owner)!=owner or m.get('subject_id',subject)!=subject:
                excluded.append({'id':sid,'reason':'suppressed_or_scope'});continue
            if m.get('role')=='assistant' and suppressed:
                lineage=m.get('context_meta',{}).get('meta',{}).get('injected_ids')
                paired=sid.removesuffix(':assistant')+':user'
                if paired in suppressed or lineage is None or any(i in retired or i.removeprefix('fact:') in retired for i in lineage):
                    excluded.append({'id':sid,'reason':'derived_source_revoked_or_untracked'});continue
            if m.get('status') in ('failed','cancelled','interrupted','running'):continue
            valid_history.append(m)
        # Resolve deictic follow-ups with the last real user utterances and case title.
        recent_users=[m for m in valid_history[-12:] if m.get('role')=='user'][-3:]
        query=message+' '+ ' '.join(str(c.get('title','')) for c in cases)
        if len(message)<45 or re.search(r'上次|后来|这件|那件|第三张|之前|他|她',message):
            query+=' '+' '.join(str(m.get('content',''))[:500] for m in recent_users)
        recalled=[];retrieval='not_needed'
        if self.index:
            try:recalled=self.index.search(query[:1800],30);retrieval=getattr(self.index,'status',{}).get('mode','hybrid')
            except Exception:retrieval='unavailable'
        selected=[]
        for doc in recalled:
            data=doc.get('data',{});sid=doc.get('source_id') or source_id(dict(data,source=doc.get('source','').removeprefix('history.'),turn_id=doc.get('record_id')))
            if doc.get('owner_user_id')!=owner or doc.get('subject_id')!=subject or sid in suppressed:
                excluded.append({'id':doc['id'],'reason':'scope_or_revoked'});continue
            # Derived predictions are searchable in their own UI, not evidence of reality.
            if doc.get('source') in ('user','conversation_state','calibration','reports','forecast_registry','omen_dictionary','daily_log') or data.get('assertion_status')=='legacy_unverified' or data.get('role')=='assistant':
                excluded.append({'id':doc['id'],'reason':'derived_not_fact'});continue
            doc_case=doc.get('case_id') or data.get('case_id')
            if doc_case and case and doc_case not in resolution.get('case_ids',[]):continue
            cost=estimated_tokens(doc)
            if used+cost>available*3//4:excluded.append({'id':doc['id'],'reason':'retrieval_budget'});continue
            # Resolve memory hits back through the authoritative database.
            if doc.get('source')=='memory':
                active=effective.get(str(doc['record_id']))
                if not active or active.get('assertion_status') not in ('user_asserted','user_confirmed','tool_observation'):continue
                doc=dict(doc,data=active)
            elif doc.get('source','').startswith('history.'):
                src=doc['source'].removeprefix('history.')
                ident=doc['source_id'].removeprefix(src+':') if doc.get('source_id') else str(doc['record_id'])+':'+data.get('role','user')
                with self.state.db() as c:row=c.execute('SELECT id FROM messages WHERE owner=? AND subject=? AND source=? AND source_id=?',(owner,subject,src,ident)).fetchone()
                if not row:continue
                try:original=self.state.get_message(owner,row['id'])
                except (ValueError,PermissionError):continue
                if original['role']!='user':continue
                doc=dict(doc,data=dict(data,source_ref=original['source_ref']))
            selected.append(doc);evidence[doc['id']]=doc;injected.append(doc['id']);used+=cost
            if len(selected)>=10:break
        pinned['retrieved']=selected
        messages=[]
        for m in reversed(valid_history[-50:]):
            text=str(m.get('content',''))
            # Older verbose assistant prose is dropped as a whole, never made a fact.
            if m.get('role')=='assistant' and len(text)>3000:continue
            cost=estimated_tokens(text)
            if used+cost>available:excluded.append({'id':source_id(m),'reason':'recent_budget'});continue
            messages.append({'role':m['role'],'content':[{'type':'text','text':f"[{m.get('source','web')} {m.get('at','')}] {text}"}]});used+=cost
        messages.reverse()
        meta={'version':'6.0','owner_user_id':owner,'subject_id':subject,'case_id':case,'case_ids':resolution.get('case_ids',[]),
              'revision':revision,'retrieval':retrieval,'history_messages':len(messages),
              'budget':{'limit_tokens_configured':self.limit,'reserved_tokens_estimated':reserve,'input_tokens_estimated':used,'estimate_method':'UTF8_bytes/2; provider usage is separate'},
              'recall_ids':[d['id'] for d in recalled],'injected_ids':injected,'excluded':excluded,'latency_ms':round((time.monotonic()-start)*1000)}
        if run_id:self.state.record_trace(owner,run_id,meta,subject=subject,case=case)
        return pinned,messages,evidence,meta

    def guard(self,system,messages,tools):
        count=estimated_tokens(system)+estimated_tokens(messages)+estimated_tokens(tools)
        reserve=int(os.environ.get('ZHIMING_REPLY_RESERVE','18000'))
        if count+reserve>self.limit:raise ContextOverflow('本轮实际工具上下文超过配置预算，问题与已取依据已保存，请缩小范围后继续')
        return count
