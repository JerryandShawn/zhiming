"""Single original-source fact writer; correction intent never grants consent."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Any
from psycopg import sql
from psycopg.types.json import Jsonb
from mingjing_core.domain.contracts import EvidenceError, Fact, RevisionConflict, ScopeError, SourceRef
from mingjing_core.repositories.postgres import fingerprint, new_id

OPTOUT = re.compile(r'(?:不要|不用|不许|禁止|不允许|别|不想|不愿|不需要).{0,12}(?:保存|存储|记录|记住|留存|归档|存记忆|加入.{0,3}记忆)|(?:不得|不能)(?:保存|存储|记录|留存)|(?:不保存|不存储|不记录|不留存)')
SAVE_AUTH = re.compile(r'(?:请|同意|允许|授权|确认|可以).{0,10}(?:保存|存储|记录|记住|留存|归档)|^(?:记住|保存|记录)(?:我|这|以下)')
SECRET = re.compile(r'密码|密钥|API.?KEY|身份证|银行卡|口令',re.I)
SENSITIVE = re.compile(r'出生|病历|诊断|确诊|创伤|自杀|性经历|性取向|精神|抑郁|怀孕|疾病|癌症|收入|存款|债务')
HYPOTHESIS = re.compile(r'假如|假设|如果|要是|举个例子|比如说|也许|可能会|[？?]')
CORRECTION = re.compile(r'更正|纠正|改为|现在|不再|其实|不是|修改|更新')
FACT_KINDS={'preference','constraint','profile','background','goal','event','concern','hearsay','hypothesis','correction'}
CATEGORIES={'偏好':'preference','约束':'constraint','出生资料':'profile','资料':'profile','背景':'background','目标':'goal','事件':'event','更正':'correction'}


class MemoryService:
    def __init__(self, repository, *, on_revoke=None):
        self.repo=repository
        self.on_revoke=on_revoke

    def receive(self,owner,subject='self',content=None,*,message=None,channel='web',source_id=None,external_id=None,
                conversation_id='default',case_ids=None,role='user',at=None,operation_id=None):
        content=content if content is not None else message
        if not isinstance(content,str) or len(content)>200000 or role not in ('user','assistant','tool','legacy'):raise ValueError('Invalid original source')
        if not source_id:raise ValueError('Stable authenticated source ID required')
        self.repo.assert_scope(owner,subject)
        if external_id is not None:
            binding=self.repo.resolve_channel(channel,str(external_id))
            if binding['owner']!=owner or binding['subject']!=subject:raise ScopeError('Source author binding mismatch')
        elif channel not in ('web','migration','web-action','synthetic','tarot','scheduled_report'):
            raise ScopeError('Channel original requires explicit identity binding')
        for cid in case_ids or []:
            if self.repo.get(owner,'case',cid)['subject_id']!=subject:raise ScopeError('Source case belongs to another subject')
        ident='msg_'+fingerprint([owner,channel,str(source_id),role])[:32]
        with self.repo.transaction(owner):
            if self.repo.is_revoked(owner,'message',ident):raise EvidenceError('Deleted original cannot be reimported')
            try:old=self.repo.get(owner,'message',ident,include_deleted=True)
            except ScopeError:old=None
            if old:
                if (old.get('content'),old['subject_id'],old.get('role'))!=(content,subject,role):raise EvidenceError('Original source identity cannot replace content or author')
                cases=list(dict.fromkeys(old.get('case_ids',[])+(case_ids or [])))
                if cases!=old.get('case_ids',[]):
                    # Additional case linkage does not change the original message version.
                    with self.repo.transaction(owner) as c:
                        c.execute(sql.SQL("UPDATE {} SET data=jsonb_set(data,'{{case_ids}}',%s),updated_at=now() WHERE owner=%s AND kind='message' AND id=%s").format(self.repo.table('core_entities')), (Jsonb(cases),owner,ident))
                    old['case_ids']=cases
                return old
            stamp=at.isoformat() if isinstance(at,datetime) else str(at or datetime.now(timezone.utc).isoformat())
            return self.repo.put(owner,'message',ident,{'content':content,'role':role,'channel':channel,'source_id':str(source_id),'external_id':external_id,'conversation_id':conversation_id,'case_ids':case_ids or [],'at':stamp},subject=subject,expected_revision=0,operation_id=operation_id)

    def get_source(self,owner,message_id,*,for_context=False):
        row=self.repo.get(owner,'message',message_id,include_deleted=True)
        if row['status']=='deleted':return dict(row,content='')
        if for_context:
            spans=[r['metadata'] for r in self.repo.revocations(owner) if r['kind']=='source_span' and r['metadata'].get('message_id')==message_id]
            text=row.get('content','')
            for span in sorted(spans,key=lambda r:r['start'],reverse=True):text=text[:span['start']]+'[该资料已撤销]'+text[span['end']:]
            row=dict(row,content=text)
        return row

    def sources(self,owner,subject='self',case_ids=None):
        rows=self.repo.list(owner,'message',subject=subject)
        selected=set(case_ids or [])
        facts=self.facts(owner,subject,list(selected));result=[]
        for row in rows:
            cases=set(row.get('case_ids',[]))
            if cases and not selected.intersection(cases):continue
            source=self.get_source(owner,row['id'],for_context=True)
            if cases-selected:
                # A message shared by A and C must not import C's unselected
                # clauses through recent history when only A was requested.
                quotes=[fact.get('content','') for fact in facts if any(ref.get('message_id')==row['id'] for ref in fact.get('source_refs',[])) and fact.get('content') in source.get('content','')]
                if not quotes:continue
                source=dict(source,content='\n'.join(dict.fromkeys(quotes)),context_projection='selected_fact_quotes')
            result.append(source)
        return result

    def grant_authorization(self,owner,subject,message_id,quote,*,kinds=None,case_id=None,operation_id=None):
        source=self.get_source(owner,message_id)
        if source['subject_id']!=subject or source.get('role')!='user' or quote not in source.get('content',''):raise ScopeError('Authorization requires this subject original user quote')
        if OPTOUT.search(source['content']) or not SAVE_AUTH.search(quote):raise EvidenceError('Explicit save authorization is absent')
        ident='consent_'+fingerprint([owner,message_id,quote,kinds,case_id])[:32]
        return self.repo.put(owner,'consent',ident,{'message_id':message_id,'source_revision':source['revision'],'kinds':kinds or ['background','profile','goal','event','preference','constraint','correction'],'case_id':case_id,'scope_start':source['content'].find(quote),'scope_end':source['content'].find(quote)+len(quote)},subject=subject,case_id=case_id,operation_id=operation_id or 'consent:'+ident,expected_revision=0)

    def _authorized(self,owner,subject,source,kind,authorization_id,case_id,quote):
        text=source['content'];start=text.find(quote);end=start+len(quote)
        if authorization_id:
            auth=self.repo.get(owner,'consent',authorization_id)
            if auth['subject_id']!=subject or auth.get('message_id')!=source['id'] or auth.get('source_revision')!=source['revision'] or kind not in auth.get('kinds',[]) or auth.get('case_id') not in (None,case_id) or not auth.get('scope_start',0)<=start<end<=auth.get('scope_end',0):raise EvidenceError('Save authorization does not cover this source/type/person/range')
            return True
        # Direct explicit saving in this very source is still checked by program, not model flags.
        clause_start=max(text.rfind('。',0,start),text.rfind('\n',0,start))+1
        return bool(SAVE_AUTH.search(text[clause_start:end]))

    def save_fact(self,owner,subject,message_id,quote,kind='preference',*,category=None,case_id=None,field=None,value=None,
                  authorization_id=None,operation_id=None,expected_revision=None,assertion_status='user_asserted',valid_from=None,valid_to=None):
        kind=CATEGORIES.get(category,kind) if category else kind
        if kind not in FACT_KINDS:raise ValueError('Invalid fact kind')
        with self.repo.transaction(owner):
            source=self.get_source(owner,message_id)
            if source['subject_id']!=subject or source['status']!='active':raise ScopeError('Original does not belong to current subject or is withdrawn')
            if case_id is not None and case_id not in source.get('case_ids',[]):raise ScopeError('Fact case is not linked to current original source')
            if source.get('role')!='user' and assertion_status!='legacy_unverified':raise EvidenceError('Assistant or tool output cannot become user facts')
            content=source.get('content','')
            if not isinstance(quote,str) or not 1<=len(quote)<=3000 or quote not in content:raise EvidenceError('Fact must exactly quote an original user range')
            if OPTOUT.search(content):return {'write_status':'rejected','reason':'本轮明确要求不保存长期记忆'}
            if SECRET.search(quote):return {'write_status':'rejected','reason':'凭据与标识不保存为聊天记忆'}
            start=content.find(quote);end=start+len(quote)
            clause_start=max(content.rfind('。',0,start),content.rfind('\n',0,start))+1
            if kind not in ('concern','hearsay','hypothesis') and HYPOTHESIS.search(content[clause_start:end]):return {'write_status':'rejected','reason':'假设或疑问不作为现实事实'}
            for revocation in self.repo.revocations(owner):
                span=revocation['metadata']
                if revocation['kind']=='source_span' and span.get('message_id')==message_id and max(start,span['start'])<min(end,span['end']):raise EvidenceError('Withdrawn source range cannot be reimported')
            if subject=='self' and re.search(r'(?:朋友|同事|他|她|家人)(?:的|是|出生|生日|喜欢|职业)',quote):return {'write_status':'pending_confirmation','reason':'先明确第三人范围与保存授权'}
            authorized=self._authorized(owner,subject,source,kind,authorization_id,case_id,quote)
            settings=self.repo.assert_scope(owner,subject)['settings']
            sensitive=subject!='self' or kind not in ('preference','constraint') or bool(field) or bool(SENSITIVE.search(quote))
            if assertion_status!='legacy_unverified' and (sensitive or not settings.get('auto_save_low_sensitivity',True)) and not authorized:return {'write_status':'pending_confirmation','reason':'需要明确保存授权，未写入长期事实'}
            if field and value is not None and str(value) not in quote and str(value).lower() not in quote.lower():raise EvidenceError('Structured field value is not in original quote')
            if field and not re.fullmatch(r'(?:name|gender|birth\.(?:solar_datetime|location\.(?:lng|lat|city|name)|timezone_offset|time_unknown|time_uncertainty_minutes|precision|interval_start|interval_end))',field):raise ValueError('Unsupported profile field')
            for cid in [case_id] if case_id else []:
                if self.repo.get(owner,'case',cid)['subject_id']!=subject:raise ScopeError('Fact case belongs to another subject')
            ident='fact_'+fingerprint([owner,message_id,start,end,kind,case_id,field,value])[:32]
            data={'kind':kind,'content':quote,'source_refs':[SourceRef(message_id=message_id,version=source['revision'],start=start,end=end,quote=quote).model_dump()],
                  'assertion_status':assertion_status,'consent':'pending' if assertion_status=='legacy_unverified' else 'granted','status':'pending' if assertion_status=='legacy_unverified' else 'active',
                  'field':field,'value':value,'valid_from':valid_from or source.get('at'),'valid_to':valid_to,'retention':'until_revoked'}
            result=self.repo.put(owner,'fact',ident,data,subject=subject,case_id=case_id,expected_revision=0,operation_id=operation_id or 'fact:'+ident)
            return dict(result,fact_id=result['id'],write_status='saved' if result['status']=='active' else 'pending_confirmation')

    def store_candidate(self,owner,subject,message_id,quote,category='偏好',**kwargs):
        return self.save_fact(owner,subject,message_id,quote,category=category,**kwargs)

    def auto_preferences(self,owner,subject,message_id,case_id=None):
        source=self.get_source(owner,message_id);text=source.get('content','');changes=[]
        if OPTOUT.search(text):return changes
        for match in re.finditer(r'我(?:喜欢|更喜欢|偏好|不喜欢|不接受|不能上)[^。！？?\n]{2,100}',text):
            quote=match.group();kind='constraint' if re.search(r'不能|不接受',quote) else 'preference'
            result=self.save_fact(owner,subject,message_id,quote,kind,case_id=case_id)
            if result.get('write_status')=='saved':changes.append(result)
        return changes

    def correct_fact(self,owner,fact_id,message_id,quote,*,expected_revision,field=None,value=None,operation_id=None):
        with self.repo.transaction(owner) as c:
            if operation_id:
                prior=c.execute(sql.SQL('SELECT kind,result_id FROM {} WHERE owner=%s AND operation_id=%s').format(self.repo.table('core_operations')),(owner,operation_id)).fetchone()
                if prior:
                    result=self.repo.get(owner,'fact',prior['result_id'],include_deleted=True)
                    if prior['kind']!='fact' or result.get('supersedes_id')!=fact_id or result.get('content')!=quote or not any(ref.get('message_id')==message_id for ref in result.get('source_refs',[])):raise EvidenceError('Correction operation reused with different target/source')
                    return dict(result,fact_id=result['id'],write_status='saved' if result['status']=='active' else 'pending_confirmation')
            old=self.repo.get(owner,'fact',fact_id)
            if old['revision']!=expected_revision:raise RevisionConflict('Fact changed before correction')
            source=self.get_source(owner,message_id)
            if old['case_id'] is not None and old['case_id'] not in source.get('case_ids',[]):raise ScopeError('Correction target case is not selected by current source')
            if source['id'] in [r['message_id'] for r in old.get('source_refs',[])]:raise EvidenceError('Correction needs new original user source')
            source=self.get_source(owner,message_id)
            if not CORRECTION.search(quote) and not (source.get('channel')=='web-action' and re.match(r'请更正这条已授权的记忆[:：]',source.get('content',''))):raise EvidenceError('Current original does not express correction')
            # A correction may continue an existing authorization for that same fact, but not authorize extra sensitive facts.
            if source.get('role')!='user' or source['subject_id']!=old['subject_id'] or quote not in source.get('content',''):raise ScopeError('Correction source does not belong to the fact subject')
            if old.get('consent')!='granted' or old['status']!='active':raise EvidenceError('Correction target is not an active authorized fact')
            auth_id='consent_'+fingerprint([owner,fact_id,message_id,quote])[:32]
            start=source['content'].find(quote)
            self.repo.put(owner,'consent',auth_id,{'message_id':message_id,'source_revision':source['revision'],'kinds':['correction'],'case_id':old['case_id'],'scope_start':start,'scope_end':start+len(quote),'correction_fact_id':fact_id},subject=old['subject_id'],case_id=old['case_id'],expected_revision=0,operation_id='correction-consent:'+auth_id)
            result=self.save_fact(owner,old['subject_id'],message_id,quote,'correction',case_id=old['case_id'],field=field or old.get('field'),value=value if value is not None else old.get('value'),authorization_id=auth_id,operation_id=operation_id)
            if result.get('write_status')!='saved':return result
            self.repo.update(owner,'fact',result['id'],{'supersedes_id':old['id']},expected_revision=result['revision'])
            self.repo.update(owner,'fact',old['id'],{'status':'superseded','valid_to':source.get('at')},expected_revision=old['revision'])
            self._withdraw_spans(c,owner,old,'superseded')
            self.repo.invalidate_derived(owner,[old['id']],[],recomputable=True)
            if self.on_revoke:self.on_revoke(owner,[old['id']],[])
            return dict(self.repo.get(owner,'fact',result['id']),write_status='saved',fact_id=result['id'])

    def apply_proposal(self,owner,source_id,proposal,operation_id):
        source=self.get_source(owner,source_id)
        allowed={'quote','category','kind','case_id','field','value','supersedes'}
        if set(proposal)-allowed:raise ValueError('Unsupported memory proposal fields')
        quote=proposal.get('quote','')
        if proposal.get('supersedes'):
            old=self.repo.get(owner,'fact',proposal['supersedes'])
            if old['subject_id']!=source['subject_id']:raise ScopeError('Correction target belongs to another subject')
            return self.correct_fact(owner,old['id'],source_id,quote,expected_revision=old['revision'],field=proposal.get('field'),value=proposal.get('value'),operation_id=operation_id)
        return self.save_fact(owner,source['subject_id'],source_id,quote,proposal.get('kind','preference'),category=proposal.get('category'),case_id=proposal.get('case_id'),field=proposal.get('field'),value=proposal.get('value'),operation_id=operation_id)

    def retire_from_message(self,owner,fact_id,source_id,operation_id):
        source=self.get_source(owner,source_id);fact=self.repo.get(owner,'fact',fact_id,include_deleted=True)
        text=source.get('content','')
        if source['subject_id']!=fact['subject_id'] or source.get('role')!='user':raise ScopeError('Withdrawal source must belong to target subject')
        if fact['case_id'] is not None and fact['case_id'] not in source.get('case_ids',[]):raise ScopeError('Withdrawal target case is not selected by current source')
        marker=re.search(r'删除|忘记|停止(?:使用)?|别再(?:用|记)|不要再(?:用|记)',text)
        if not marker:raise EvidenceError('Original user did not request withdrawal')
        if fact['status'] in ('deleted','stopped'):
            return dict(fact,write_status='deleted' if fact['status']=='deleted' else 'stopped')
        # A guessed fact ID is insufficient. Reference must include current text or an unambiguous sole retained fact.
        candidates=[f for f in self.facts(owner,source['subject_id'],include_inactive=False) if f.get('content') and (f['content'] in text or any(part in text for part in re.split(r'[，。,:：]',f['content']) if len(part)>=4))]
        if candidates and {f['id'] for f in candidates}!={fact_id} or not candidates and len(self.facts(owner,source['subject_id']))!=1:raise EvidenceError('Withdrawal target is not unique; ask for the fact to remove')
        return self.retire_fact(owner,fact_id,expected_revision=fact['revision'],operation='delete' if re.search(r'删除|忘记',text) else 'stop',scope='source' if re.search(r'原话|整条消息|所有来源',text) else 'fact')

    def import_message(self,owner,source,id,role,content,at=None,subject='self',case=None,channel=None,external_id=None,conversation_id='default'):
        return self.receive(owner,subject,content,channel=channel or source,source_id=str(id),external_id=external_id,conversation_id=conversation_id,case_ids=[] if case is None else [case] if isinstance(case,str) else case,role=role,at=at)

    def get_message(self,owner,id,include_suppressed=False):
        result=self.get_source(owner,id,for_context=not include_suppressed)
        if result['status']=='deleted' and not include_suppressed:raise EvidenceError('Original was deleted')
        return result

    def is_suppressed(self,owner,channel,source_id,role='user'):
        ident='msg_'+fingerprint([owner,channel,str(source_id),role])[:32]
        return self.repo.is_revoked(owner,'message',ident)

    def resolve_channel(self,channel,external_id):return self.repo.resolve_channel(channel,external_id)

    def _withdraw_spans(self,c,owner,fact,operation):
        for ref in fact.get('source_refs',[]):
            span_id=fingerprint([ref['message_id'],ref['start'],ref['end']])
            self.repo.revoke(c,owner,'source_span',span_id,operation,{k:ref[k] for k in ('message_id','start','end')})

    def retire_fact(self,owner,fact_id,*,expected_revision,operation='delete',scope='fact'):
        if operation not in ('delete','stop') or scope not in ('fact','source'):raise ValueError('Invalid withdrawal operation/scope')
        with self.repo.transaction(owner) as c:
            old=self.repo.get(owner,'fact',fact_id,include_deleted=True)
            if old['status'] in ('deleted','stopped'):return dict(old,write_status='deleted' if old['status']=='deleted' else 'stopped')
            if old['revision']!=expected_revision:raise RevisionConflict('Fact changed before withdrawal')
            sources=[r['message_id'] for r in old.get('source_refs',[])]
            facts=[old]
            if scope=='source':
                facts=[f for f in self.repo.list(owner,'fact',include_deleted=True) if any(r['message_id'] in sources for r in f.get('source_refs',[]))]
                for source_id in sources:
                    source=self.repo.get(owner,'message',source_id,include_deleted=True)
                    self.repo.delete(owner,'message',source_id,expected_revision=source['revision'])
            affected=[]
            for fact in facts:
                if fact['status']=='deleted':continue
                self._withdraw_spans(c,owner,fact,'deleted' if operation=='delete' else 'stopped')
                if operation=='delete':self.repo.delete(owner,'fact',fact['id'],expected_revision=fact['revision'])
                else:
                    self.repo.update(owner,'fact',fact['id'],{'status':'stopped','consent':'revoked'},expected_revision=fact['revision'])
                    self.repo.revoke(c,owner,'fact',fact['id'],'stopped')
                affected.append(fact['id'])
            self.repo.invalidate_derived(owner,affected,sources if scope=='source' else [])
            if scope=='source':
                for upload in self.repo.list(owner,'upload',include_deleted=True):
                    if upload.get('message_id') in sources and upload['status']!='deleted':self.repo.delete(owner,'upload',upload['id'],expected_revision=upload['revision'])
            if self.on_revoke:self.on_revoke(owner,affected,sources if scope=='source' else [])
            return dict(self.repo.get(owner,'fact',fact_id,include_deleted=True),write_status='deleted' if operation=='delete' else 'stopped',affected_fact_ids=affected)

    def facts(self,owner,subject='self',case_ids=None,*,include_inactive=False):
        rows=self.repo.list(owner,'fact',subject=subject,case_ids=case_ids,include_deleted=include_inactive)
        when=datetime.now(timezone.utc)
        def effective(fact):
            if fact['status']!='active' or fact.get('consent')!='granted' or fact.get('assertion_status')=='legacy_unverified':return False
            for key in ('valid_from','valid_to'):
                value=fact.get(key)
                if value:
                    at=datetime.fromisoformat(str(value).replace('Z','+00:00'))
                    if at.tzinfo is None:at=at.replace(tzinfo=timezone.utc)
                    if key=='valid_from' and at>when or key=='valid_to' and at<=when:return False
            return True
        return rows if include_inactive else [row for row in rows if effective(row)]

    def create_case(self,owner,subject,title,*,goal='',message_id=None,operation_id=None,case_id=None,conversation_id='default'):
        if not isinstance(title,str) or not 1<=len(title)<=120:raise ValueError('Case title must contain 1..120 characters')
        refs=[]
        if message_id:
            source=self.get_source(owner,message_id)
            if source['subject_id']!=subject or source.get('role')!='user' or goal and goal not in source['content']:raise EvidenceError('Case goal/source mismatch')
            refs=[{'message_id':message_id,'version':source['revision']}]
        elif goal:raise EvidenceError('Case goal requires original user source')
        ident=case_id or ('case_'+fingerprint([owner,operation_id])[:32] if operation_id else new_id('case'))
        return self.repo.put(owner,'case',ident,{'title':title,'state':{'goal':goal,'pending':[]},'source_refs':refs,'conversation_id':conversation_id,'status':'open'},subject=subject,expected_revision=0,operation_id=operation_id)

    def resolve_cases(self,owner,subject,message,conversation_id='default',case_ids=None):
        cases=self.repo.list(owner,'case',subject=subject)
        chosen=list(dict.fromkeys(case_ids or []));ambiguous=False;reason='explicit_ids' if chosen else 'no_reference'
        if chosen:
            if len(chosen)>8:raise ValueError('At most eight cases per request')
            for cid in chosen:
                if self.repo.get(owner,'case',cid)['subject_id']!=subject:raise ScopeError('Case outside subject')
        else:
            chosen=[c['id'] for c in cases if c.get('title') and c['title'] in message]
            if chosen:reason='explicit_title'
            elif re.search(r'上次|继续|后来|这件事|那件事|第三张|第[一二三四五12345]张',message):
                history=[m for m in self.repo.list(owner,'message',subject=subject) if m.get('conversation_id')==conversation_id and m.get('case_ids')]
                previous=history[-1]['case_ids'] if history else []
                if len(previous)==1:chosen=previous;reason='conversation_reference'
                elif len(cases)==1:chosen=[cases[0]['id']];reason='only_case'
                else:ambiguous=True;reason='ambiguous_reference'
        return {'case_ids':chosen,'case_id':chosen[0] if len(chosen)==1 else None,'needs_clarification':ambiguous,'reason':reason,'candidates':[{'id':c['id'],'title':c.get('title')} for c in cases] if ambiguous else []}

    def snapshot(self,owner,subject='self',case_ids=None,*,conversation_id=None,history_limit=32):
        with self.repo.transaction(owner):
            settings=self.repo.assert_scope(owner,subject)['settings'];case_ids=list(dict.fromkeys(case_ids or []))
            versions=self.repo.versions(owner,subject,case_ids)
            facts=self.facts(owner,subject,case_ids);profile={};conflicts=[]
            for fact in facts:
                versions['fact:'+fact['id']]=fact['revision']
                field=fact.get('field')
                if field:
                    if field in profile and profile[field]!=fact.get('value'):conflicts.append(field)
                    else:profile[field]=fact.get('value')
            for field in conflicts:profile.pop(field,None)
            sources=self.sources(owner,subject,case_ids)
            if conversation_id:sources=[s for s in sources if s.get('conversation_id')==conversation_id]
            history=sources[-max(0,history_limit):] if history_limit else []
            for source in history:versions['message:'+source['id']]=source['revision']
            return {'owner_user_id':owner,'subject_id':subject,'case_ids':case_ids,'revision':self.repo.get_revision(owner),'versions':versions,'facts':facts,'effective_facts':facts,'sources':history,'history':history,'profile':profile,'profile_conflicts':sorted(set(conflicts)),'cases':[self.repo.get(owner,'case',cid) for cid in case_ids],'settings':settings}

    def update_settings(self,owner,settings,*,expected_revision):
        if set(settings)-{'auto_save_low_sensitivity'} or any(not isinstance(v,bool) for v in settings.values()):raise ValueError('Unsupported memory settings')
        with self.repo.transaction(owner) as c:
            if self.repo.get_revision(owner)!=expected_revision:raise RevisionConflict('Settings state changed')
            old=self.repo.assert_scope(owner)['settings'];old.update(settings)
            c.execute(sql.SQL('UPDATE {} SET settings=%s WHERE id=%s').format(self.repo.table('core_owners')), (Jsonb(old),owner))
            self.repo.bump_revision(c,owner,owner_scope=True)
            return {'settings':old,'revision':self.repo.get_revision(owner)}
