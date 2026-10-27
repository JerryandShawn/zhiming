"""Single original-source fact writer; correction intent never grants consent."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Any
from psycopg import sql
from psycopg.types.json import Jsonb
from mingjing_core.domain.contracts import EvidenceError, Fact, RevisionConflict, ScopeError, SourceRef
from mingjing_core.repositories.postgres import fingerprint, new_id
from mingjing_core.repositories.foundation import thread_history
from mingjing_core.memory.policy import authorization_clause, has_optout, hypothetical, mask_quoted, third_party
from mingjing_core.memory.projections import redact_ranges
from mingjing_core.memory.threads import message_fields, project_sources, record_assistant
from mingjing_core.timekit.clock import get_clock
from mingjing_core.timekit.timestamps import history_instant

OPTOUT = re.compile(r'(?:不要|不用|不许|禁止|不允许|别|不想|不愿|不需要).{0,12}(?:保存|存储|记录|记住|留存|归档|存记忆|加入.{0,3}记忆)|(?:不得|不能)(?:保存|存储|记录|留存)|(?:不保存|不存储|不记录|不留存)')
SAVE_AUTH = re.compile(r'(?:请(?:你|帮我|替我|为我)?|(?:我)?(?:同意|允许|授权)(?:你|系统)?|(?:我)?(?:确认|可以))\s*(?:保存|存储|记录|记住|留存|归档)(?![的过了])|(?:^|[，,:：。；;\n])\s*(?:记住|保存|记录)(?:我|这|以下)')
SECRET = re.compile(r'密码|密钥|API.?KEY|身份证|银行卡|口令',re.I)
SENSITIVE = re.compile(r'出生|病历|诊断|确诊|创伤|自杀|性经历|性取向|精神|抑郁|怀孕|疾病|癌症|收入|存款|债务')
HYPOTHESIS = re.compile(r'假如|假设|如果|要是|举个例子|比如说|也许|可能会|[？?]')
CORRECTION = re.compile(r'更正|纠正|改为|现在|不再|其实|不是|修改|更新')
FACT_KINDS={'preference','constraint','profile','background','goal','event','concern','hearsay','hypothesis','correction'}
CATEGORIES={'偏好':'preference','约束':'constraint','出生资料':'profile','资料':'profile','背景':'background','目标':'goal','事件':'event','更正':'correction'}
CURRENT_CHANNELS={'web','web-action','synthetic','tarot'}


def fact_kind(kind='preference',category=None):
    if category is not None:
        if not isinstance(category,str):raise ValueError('Invalid fact category')
        if category in CATEGORIES:kind=CATEGORIES[category]
        elif category in FACT_KINDS:kind=category
        else:raise ValueError('Invalid fact category')
    if kind not in FACT_KINDS:raise ValueError('Invalid fact kind')
    return kind


def explicit_save_authorization(text):
    """A current save instruction grants consent; references to saved state do not."""
    if has_optout(text):return False
    command_text=mask_quoted(text)
    for match in SAVE_AUTH.finditer(command_text):
        start=max(command_text.rfind(mark,0,match.start()) for mark in ('。','！','!','？','?','；',';','\n'))+1
        ends=[command_text.find(mark,match.end()) for mark in ('。','！','!','？','?','；',';','\n')]
        end=min([position+1 for position in ends if position>=0] or [len(command_text)])
        clause=command_text[start:end]
        if re.search(r'是否|能否|可否|可以吗|吗[？?]?|[？?]|假如|假设|如果',clause):continue
        if re.search(r'(?:已|已经|曾|此前|之前|先前|上次|不|未|没|并非|不是)\s*$',command_text[start:match.start()]):continue
        if re.search(r'(?:说|说过|提到|问|写着|原话是|引用|解释)[：:，,\s]*$',command_text[start:match.start()]):continue
        return True
    return False


class MemoryService:
    def __init__(self, repository, *, on_revoke=None):
        self.repo=repository
        self.on_revoke=on_revoke

    def _third_party_authorized(self,owner,subject,source,kind,authorization_id,case_id,quote):
        return False

    def _fact_id(self,owner,message_id,start,end,kind,case_id,field,value,authorization_id):
        return 'fact_'+fingerprint([owner,message_id,start,end,kind,case_id,field,value])[:32]

    def receive(self,owner,subject='self',content=None,*,message=None,channel='web',source_id=None,external_id=None,
                conversation_id='default',case_ids=None,role='user',at=None,operation_id=None,origin='current_user'):
        content=content if content is not None else message
        if not isinstance(content,str) or len(content)>200000 or role not in ('user','assistant','tool','legacy'):raise ValueError('Invalid original source')
        if not source_id:raise ValueError('Stable authenticated source ID required')
        if origin not in ('current_user','migration','system','unknown'):raise ValueError('Invalid program source origin')
        self.repo.assert_scope(owner,subject)
        if external_id is not None:
            binding=self.repo.resolve_channel(channel,str(external_id))
            if binding['owner']!=owner or binding['subject']!=subject:raise ScopeError('Source author binding mismatch')
        elif channel not in ('web','migration','web-action','synthetic','tarot','scheduled_report'):
            raise ScopeError('Channel original requires explicit identity binding')
        for cid in case_ids or []:
            if self.repo.get(owner,'case',cid)['subject_id']!=subject:raise ScopeError('Source case belongs to another subject')
        ident='msg_'+fingerprint([owner,channel,str(source_id),role])[:32]
        source_origin=('migration' if channel=='migration' or role=='legacy' else
                       'system' if role!='user' or channel=='scheduled_report' else origin)
        policy={'origin':source_origin,'run_context':source_origin=='current_user' and
                role=='user' and (channel in CURRENT_CHANNELS or external_id is not None)}
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
            stamp=at.isoformat() if isinstance(at,datetime) else str(at or get_clock().now().isoformat())
            effective=stamp
            if history_instant(stamp) is None:
                # Legacy unknown text stays original; PostgreSQL transaction time
                # is the same created_at fallback used by the history API.
                with self.repo.transaction(owner) as connection:
                    effective=connection.execute("SELECT now() AS at").fetchone()['at']
            fields=message_fields(subject,effective,conversation_id)
            return self.repo.put(owner,'message',ident,dict(fields,content=content,role=role,channel=channel,source_id=str(source_id),external_id=external_id,conversation_id=conversation_id,case_ids=case_ids or [],at=stamp,policy=policy),subject=subject,expected_revision=0,operation_id=operation_id)

    def record_assistant_message(self,owner,subject,thread_id,text,*,run_id,kind='chat',used_fact_ids=(),channel,at=None,**lineage):
        return record_assistant(self,owner,subject,thread_id,text,run_id=run_id,kind=kind,
                                used_fact_ids=used_fact_ids,channel=channel,at=at,**lineage)

    def get_source(self,owner,message_id,*,for_context=False):
        row=self.repo.get(owner,'message',message_id,include_deleted=True)
        if row['status']=='deleted':return dict(row,content='')
        if for_context:
            spans=[r['metadata'] for r in self.repo.revocations(owner) if r['kind']=='source_span' and r['metadata'].get('message_id')==message_id]
            text=redact_ranges(row.get('content',''),spans)
            row=dict(row,content=text)
        return row

    def sources(self,owner,subject='self',case_ids=None,*,thread_id=None,limit=None):
        rows=(thread_history(self.repo,owner,subject,thread_id,case_ids,limit or 30)[::-1] if thread_id else
              self.repo.list(owner,'message',subject=subject))
        selected=set(case_ids or [])
        return project_sources(self,owner,rows,self.facts(owner,subject,list(selected)),selected)

    def grant_authorization(self,owner,subject,message_id,quote,*,kinds=None,case_id=None,operation_id=None):
        source=self.get_source(owner,message_id)
        from mingjing_core.memory.private import require_persistent_source
        require_persistent_source(source)
        if source['subject_id']!=subject or source.get('role')!='user' or quote not in source.get('content',''):raise ScopeError('Authorization requires this subject original user quote')
        if has_optout(source['content']) or not explicit_save_authorization(quote):raise EvidenceError('Explicit save authorization is absent')
        ident='consent_'+fingerprint([owner,message_id,quote,kinds,case_id])[:32]
        return self.repo.put(owner,'consent',ident,{'message_id':message_id,'source_revision':source['revision'],'kinds':kinds or ['background','profile','goal','event','preference','constraint','correction'],'case_id':case_id,'scope_start':source['content'].find(quote),'scope_end':source['content'].find(quote)+len(quote)},subject=subject,case_id=case_id,operation_id=operation_id or 'consent:'+ident,expected_revision=0)

    def _authorized(self,owner,subject,source,kind,authorization_id,case_id,quote):
        text=source['content'];start=text.find(quote);end=start+len(quote)
        if authorization_id:
            auth=self.repo.get(owner,'consent',authorization_id)
            if auth['subject_id']!=subject or auth.get('message_id')!=source['id'] or auth.get('source_revision')!=source['revision'] or kind not in auth.get('kinds',[]) or auth.get('case_id') not in (None,case_id) or not auth.get('scope_start',0)<=start<end<=auth.get('scope_end',0):raise EvidenceError('Save authorization does not cover this source/type/person/range')
            return True
        # Direct explicit saving in this very source is still checked by program, not model flags.
        return explicit_save_authorization(authorization_clause(text,start,end))

    def current_source_context(self,owner,subject,message_id,proposals,case_ids=None):
        """Quote current user context without making, confirming or storing facts."""
        empty={'facts':[],'versions':{}}
        self.repo.assert_scope(owner,subject)
        selected=list(dict.fromkeys(case_ids or []))
        for case in selected:
            if self.repo.get(owner,'case',case)['subject_id']!=subject:raise ScopeError('Current source case belongs to another subject')
        if not isinstance(proposals,list) or len(proposals)>12:raise EvidenceError('Invalid current source proposals')
        with self.repo.transaction(owner):
            source=self.get_source(owner,message_id)
            from mingjing_core.memory.private import is_private
            if is_private(source):return empty
            if source['subject_id']!=subject:raise ScopeError('Current source belongs to another subject')
            policy=source.get('policy',{})
            if (source['status']!='active' or source.get('role')!='user' or not isinstance(policy,dict) or
                    policy.get('run_context') is not True or policy.get('origin')!='current_user' or
                    self.repo.is_revoked(owner,'message',message_id)):return empty
            text=source.get('content','');facts=[]
            spans=[row['metadata'] for row in self.repo.revocations(owner) if row['kind']=='source_span' and row['metadata'].get('message_id')==message_id]
            saved=[ref for fact in self.facts(owner,subject,selected) for ref in fact.get('source_refs',[])
                   if ref.get('message_id')==message_id and ref.get('version')==source['revision']]
            for proposal in proposals:
                if not isinstance(proposal,dict) or set(proposal)-{'quote','category','kind','case_id','field','value','supersedes'}:raise EvidenceError('Unsupported current source proposal')
                quote=proposal.get('quote','');case=proposal.get('case_id')
                if not isinstance(quote,str) or not 1<=len(quote)<=3000 or quote not in text:raise EvidenceError('Current context must exactly quote this original user source')
                if case is not None and (case not in selected or case not in source.get('case_ids',[])):raise ScopeError('Current context case is outside the selected source')
                kind=fact_kind(proposal.get('kind','preference'),proposal.get('category'))
                if kind in ('profile','correction') or proposal.get('field') is not None or proposal.get('value') is not None or proposal.get('supersedes') or SECRET.search(quote):continue
                if subject=='self' and third_party(quote):continue
                start=text.find(quote);end=start+len(quote)
                if kind not in ('concern','hearsay','hypothesis') and hypothetical(text,start,end):continue
                if any(max(start,span['start'])<min(end,span['end']) for span in spans):continue
                if any(ref.get('start',-1)<=start<end<=ref.get('end',-1) for ref in saved):continue
                ident='current_source_'+fingerprint([owner,message_id,start,end,kind,case,None,None])[:32]
                if any(fact['id']==ident for fact in facts):continue
                facts.append({'id':ident,'owner':owner,'owner_user_id':owner,'subject':subject,'subject_id':subject,
                    'case_id':case,'kind':kind,'content':quote,'source_refs':[SourceRef(message_id=message_id,version=source['revision'],start=start,end=end,quote=quote).model_dump()],
                    'status':'current_source','assertion_status':'current_source','consent':'current_round','retention':'current_round',
                    'context_only':True,'field':None,'value':None,'revision':source['revision']})
            return {'facts':facts,'versions':{'message:'+message_id:source['revision']}}

    def save_fact(self,owner,subject,message_id,quote,kind='preference',*,category=None,case_id=None,field=None,value=None,
                  authorization_id=None,operation_id=None,expected_revision=None,assertion_status='user_asserted',valid_from=None,valid_to=None):
        kind=fact_kind(kind,category)
        with self.repo.transaction(owner):
            source=self.get_source(owner,message_id)
            from mingjing_core.memory.private import require_persistent_source
            require_persistent_source(source)
            if source['subject_id']!=subject or source['status']!='active':raise ScopeError('Original does not belong to current subject or is withdrawn')
            if case_id is not None and case_id not in source.get('case_ids',[]):raise ScopeError('Fact case is not linked to current original source')
            if source.get('role')!='user' and not (source.get('role')=='legacy' and assertion_status=='legacy_unverified'):raise EvidenceError('Assistant or tool output cannot become user facts')
            content=source.get('content','')
            if not isinstance(quote,str) or not 1<=len(quote)<=3000 or quote not in content:raise EvidenceError('Fact must exactly quote an original user range')
            if has_optout(content):return {'write_status':'rejected','reason':'本轮明确要求不保存长期记忆'}
            if source.get('policy',{}).get('origin')=='system':return {'write_status':'rejected','reason':'系统任务不是用户原话，未写入长期事实'}
            if SECRET.search(quote):return {'write_status':'rejected','reason':'凭据与标识不保存为聊天记忆'}
            start=content.find(quote);end=start+len(quote)
            if kind not in ('concern','hearsay','hypothesis') and hypothetical(content,start,end):return {'write_status':'rejected','reason':'假设或疑问不作为现实事实'}
            for revocation in self.repo.revocations(owner):
                span=revocation['metadata']
                if revocation['kind']=='source_span' and span.get('message_id')==message_id and max(start,span['start'])<min(end,span['end']):raise EvidenceError('Withdrawn source range cannot be reimported')
            if subject=='self' and third_party(quote) and not self._third_party_authorized(owner,subject,source,kind,authorization_id,case_id,quote):return {'write_status':'pending_confirmation','reason':'先明确第三人范围与保存授权'}
            authorized=self._authorized(owner,subject,source,kind,authorization_id,case_id,quote)
            settings=self.repo.assert_scope(owner,subject)['settings']
            sensitive=subject!='self' or kind not in ('preference','constraint') or bool(field) or bool(SENSITIVE.search(quote))
            if assertion_status!='legacy_unverified' and (sensitive or not settings.get('auto_save_low_sensitivity',True)) and not authorized:return {'write_status':'pending_confirmation','reason':'需要明确保存授权，未写入长期事实'}
            if field and value is not None and str(value) not in quote and str(value).lower() not in quote.lower():raise EvidenceError('Structured field value is not in original quote')
            if field and not re.fullmatch(r'(?:name|gender|birth\.(?:solar_datetime|location\.(?:lng|lat|city|name)|timezone_offset|time_unknown|time_uncertainty_minutes|precision|interval_start|interval_end))',field):raise ValueError('Unsupported profile field')
            for cid in [case_id] if case_id else []:
                if self.repo.get(owner,'case',cid)['subject_id']!=subject:raise ScopeError('Fact case belongs to another subject')
            ident=self._fact_id(owner,message_id,start,end,kind,case_id,field,value,authorization_id)
            data={'kind':kind,'content':quote,'source_refs':[SourceRef(message_id=message_id,version=source['revision'],start=start,end=end,quote=quote).model_dump()],
                  'assertion_status':assertion_status,'consent':'pending' if assertion_status=='legacy_unverified' else 'granted','status':'pending' if assertion_status=='legacy_unverified' else 'active',
                  'field':field,'value':value,'valid_from':valid_from or source.get('at'),'valid_to':valid_to,'retention':'until_revoked'}
            result=self.repo.put(owner,'fact',ident,data,subject=subject,case_id=case_id,expected_revision=0,operation_id=operation_id or 'fact:'+ident)
            return dict(result,fact_id=result['id'],write_status='saved' if result['status']=='active' else 'pending_confirmation')

    def store_candidate(self,owner,subject,message_id,quote,category='偏好',**kwargs):
        return self.save_fact(owner,subject,message_id,quote,category=category,**kwargs)

    def auto_preferences(self,owner,subject,message_id,case_id=None):
        source=self.get_source(owner,message_id);text=source.get('content','');changes=[]
        if has_optout(text):return changes
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
        from mingjing_core.memory.private import require_persistent_source
        require_persistent_source(source)
        text=source.get('content','')
        if source['subject_id']!=fact['subject_id'] or source.get('role')!='user':raise ScopeError('Withdrawal source must belong to target subject')
        if fact['case_id'] is not None and fact['case_id'] not in source.get('case_ids',[]):raise ScopeError('Withdrawal target case is not selected by current source')
        from mingjing_core.memory.forget_intent import forget_topic, withdrawal_denied
        if withdrawal_denied(text):
            raise EvidenceError("需要当前用户明确的肯定撤销请求")
        if forget_topic(text) is not None:
            from mingjing_core.application.memory2_withdrawals import MemoryWithdrawalService
            receipt = MemoryWithdrawalService(self).forget_from_message(
                owner, source['subject_id'], fact_id, message_id=source_id, operation_id=operation_id
            )
            return dict(
                self.repo.get(owner, 'fact', fact_id, include_deleted=True),
                write_status=receipt['write_status'], affected_fact_ids=receipt['affected_ids']
            )
        marker=re.search(r'删除|忘记|停止(?:使用)?|别再(?:用|记)|不要再(?:用|记)',mask_quoted(text))
        if not marker:raise EvidenceError('Original user did not request withdrawal')
        if fact['status'] in ('deleted','stopped'):
            return dict(fact,write_status='deleted' if fact['status']=='deleted' else 'stopped')
        # A guessed fact ID is insufficient. Reference must include current text or an unambiguous sole retained fact.
        from mingjing_core.application.memory2_forget_candidates import forget_candidates
        eligible=forget_candidates(self,owner,source['subject_id'],source.get('case_ids',[]))
        candidates=[f for f in eligible if f.get('content') and (f['content'] in text or any(part in text for part in re.split(r'[，。,:：]',f['content']) if len(part)>=4))]
        if candidates and {f['id'] for f in candidates}!={fact_id} or not candidates and len(eligible)!=1:raise EvidenceError('Withdrawal target is not unique; ask for the fact to remove')
        return self.retire_fact(owner,fact_id,expected_revision=fact['revision'],operation='delete' if re.search(r'删除|忘记',text) else 'stop',scope='source' if re.search(r'原话|整条消息|所有来源',text) else 'fact')

    def import_message(self,owner,source,id,role,content,at=None,subject='self',case=None,channel=None,external_id=None,conversation_id='default',origin='migration'):
        return self.receive(owner,subject,content,channel=channel or source,source_id=str(id),external_id=external_id,conversation_id=conversation_id,case_ids=[] if case is None else [case] if isinstance(case,str) else case,role=role,at=at,origin=origin)

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
            self.repo.revoke(c,owner,'source_span',span_id,operation,dict({k:ref[k] for k in ('message_id','start','end')},fact_ids=[fact['id']]))

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
            from mingjing_core.application.memory2_forget_candidates import merged_descendants
            facts=merged_descendants(self,owner,facts)
            affected=[]
            for fact in facts:
                if fact['status']=='deleted':continue
                self._withdraw_spans(c,owner,fact,'deleted' if operation=='delete' else 'stopped')
                if operation=='delete':self.repo.delete(owner,'fact',fact['id'],expected_revision=fact['revision'])
                else:
                    self.repo.update(owner,'fact',fact['id'],{'status':'stopped','consent':'revoked'},expected_revision=fact['revision'])
                    self.repo.revoke(c,owner,'fact',fact['id'],'stopped')
                affected.append(fact['id'])
            from mingjing_core.application.memory2_forget_chain import detach_withdrawn_chain
            detach_withdrawn_chain(self,owner,facts)
            self.repo.invalidate_derived(owner,affected,sources if scope=='source' else [])
            if scope=='source':
                for upload in self.repo.list(owner,'upload',include_deleted=True):
                    if upload.get('message_id') in sources and upload['status']!='deleted':self.repo.delete(owner,'upload',upload['id'],expected_revision=upload['revision'])
            if self.on_revoke:self.on_revoke(owner,affected,sources if scope=='source' else [])
            return dict(self.repo.get(owner,'fact',fact_id,include_deleted=True),write_status='deleted' if operation=='delete' else 'stopped',affected_fact_ids=affected)

    def facts(self,owner,subject='self',case_ids=None,*,include_inactive=False):
        from mingjing_core.application.memory2_read_authority import consent_verifier
        with self.repo.transaction(owner):
            rows=self.repo.list(owner,'fact',subject=subject,case_ids=case_ids,include_deleted=include_inactive)
            when=get_clock().now()
            consent_valid=consent_verifier(self,owner,subject)
            def effective(fact):
                if fact['status']!='active' or fact.get('consent')!='granted' or fact.get('assertion_status')=='legacy_unverified':return False
                if not consent_valid(fact):return False
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
            from mingjing_core.memory.private import require_persistent_source
            require_persistent_source(source)
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

    def snapshot(self,owner,subject='self',case_ids=None,*,conversation_id=None,history_limit=30):
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
            sources=self.sources(owner,subject,case_ids,thread_id='life:'+subject,limit=max(1,history_limit))
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
