"""Adapters for live authoritative facts, profile overlays and source registration."""
import json,re,uuid
from pathlib import Path
from state_store import StateStore,RevisionConflict,EvidenceError

class StaleContext(RuntimeError):pass

def profile_archive(state,owner,subject='self',legacy=None):
    # Legacy data is usable only for the explicitly configured original owner.
    arc=json.loads(json.dumps(legacy or {}));user={}
    if subject=='self':user=arc.get('user',{})
    profile=state.profile(owner,subject);flat=profile.get('values',{})
    # Revoked fields must not fall back to an old archive profile.
    for fact in state.list_facts(owner,subject,include_inactive=True):
        if not fact.get('field') or fact.get('status')=='active':continue
        bits=fact['field'].removeprefix('user.').split('.');target=user
        for key in bits[:-1]:target=target.get(key,{}) if isinstance(target,dict) else {}
        if isinstance(target,dict):target.pop(bits[-1],None)
    if state.snapshot(owner,subject).get('invalidated_derived_sources'):
        for section in ('calibration','daily_log','conversation_state'):arc.pop(section,None)
        user={}
    for field,value in flat.items():
        target=user;bits=field.split('.')
        if bits[0]=='user':bits=bits[1:]
        if not bits:continue
        for key in bits[:-1]:target=target.setdefault(key,{})
        target[bits[-1]]=value
    arc['user']=user
    if profile.get('conflicts'):arc['user'].setdefault('birth',{})['time_unknown']=True
    arc['conversation_state']={'user_facts':state.list_facts(owner,subject)}
    arc['state_revision']=state.revision(owner)
    return arc

def memory_view(fact):
    refs=fact.get('source_refs',[])
    return dict(fact,text=fact.get('content',''),quote=next((r.get('quote','') for r in refs if r.get('quote')),fact.get('content','')),
                category={'preference':'偏好','constraint':'约束','profile':'资料','goal':'目标','correction':'更正','event':'事件'}.get(fact.get('kind'),'背景'),
                created_at=fact.get('recorded_at',''),source_turn=refs[0].get('message_id','') if refs else '',
                status=fact.get('status','active'))

def register_history(state,owner,subject,history,conversation='shared'):
    for m in history:
        if m.get('owner_user_id',owner)!=owner or m.get('subject_id',subject)!=subject:continue
        ident=str(m.get('turn_id') or m.get('message_id') or m.get('id',''))+':'+m.get('role','user')
        if not ident.strip(':'):continue
        try:state.import_message(owner,m.get('source','web'),ident,m.get('role','user'),str(m.get('content','')),
                at=m.get('at'),subject=subject,conversation_id=conversation)
        except EvidenceError:continue # a revoked original cannot be silently resurrected

def register_turn(state,owner,subject,turn,case=None):
    return state.import_message(owner,'web',turn['id']+':user','user',turn['message'],
                at=turn.get('created_at'),subject=subject,case=case,conversation_id=turn['session_id'])

def store_candidate(state,owner,subject,message_row,quote,category='偏好',supersedes=None,case=None,field=None,value=None,expected_revision=None):
    source=message_row['content']
    if not isinstance(quote,str) or not quote.strip() or quote not in source:raise ValueError('记忆必须逐字引用本轮原话')
    if re.search(r'(?:不要|不用|别|不许).{0,8}(?:保存|记录|记住|存记忆)',source):raise ValueError('本轮明确要求不保存记忆')
    if re.search(r'假设|假如|如果我|举个例子|可能会|[？?]',source):raise ValueError('本轮假设或疑问不自动保存为事实')
    kind={'偏好':'preference','约束':'constraint','背景':'background','更正':'correction','目标':'goal','事件':'event','出生资料':'profile'}.get(category)
    if not kind:raise ValueError('记忆类别无效')
    explicit=bool(re.search(r'请记住|记住|确认|更正|纠正|改为|其实|不是|不再',source))
    if not explicit and not state.snapshot(owner,subject).get('settings',{}).get('auto_save_low_sensitivity',True):
        return {'write_status':'pending_confirmation','status':'pending','reason':'自动保存已关闭，尚未写入长期事实'}
    # Automatic retention covers low-risk preferences/constraints only.
    if not explicit and kind not in ('preference','constraint'):
        return {'write_status':'pending_confirmation','status':'pending','reason':'需要明确保存授权，尚未写入长期事实'}
    if re.search(r'密码|密钥|身份证|银行卡',quote):raise ValueError('凭据与标识不作为聊天记忆保存')
    if subject=='self' and re.search(r'(?:朋友|同事|他|她|家人)(?:的|是|出生|生日|喜欢|职业)',quote):
        return {'write_status':'pending_confirmation','status':'pending','reason':'这段涉及其他人物，需要先明确人物与保存授权，未混入本人事实'}
    if kind=='background' and re.search(r'我(?:担心|害怕|焦虑|怕)',quote):kind='concern'
    fact=state.put_fact(owner,subject,quote,[{'message_id':message_row['id'],'quote':quote}],kind=kind,
        case_id=case,field=field,value=value,supersedes_id=supersedes,
        expected_revision=expected_revision if supersedes else None,explicit=explicit,
        idempotency_key='candidate:'+message_row['id']+':'+quote)
    return dict(memory_view(fact),write_status='saved' if fact.get('status')=='active' and fact.get('consent')=='granted' else 'inactive')

def auto_preferences(state,owner,subject,message_row,case=None):
    text=message_row['content'];changes=[]
    if re.search(r'假设|假如|如果|第三人|(?:不要|不用|别).{0,8}(?:保存|记录|记住)',text):return changes
    for match in re.finditer(r'我(?:喜欢|更喜欢|偏好|不喜欢|不接受|不能上)[^。！？?\n]{2,100}',text):
        quote=match.group();category='约束' if re.search(r'不能|不接受',quote) else '偏好'
        try:
            result=store_candidate(state,owner,subject,message_row,quote,category,case=case)
            if result.get('write_status')=='saved':changes.append(result)
        except (ValueError,PermissionError):continue
    return changes

def registered_evidence(state,owner,subject,trace):
    """Reauthorize only references that this bound run actually injected."""
    evidence={};ids=set(trace.get('payload',{}).get('injected_ids',[]))
    for fact in state.snapshot(owner,subject,trace.get('case_id')).get('facts',[]):
        if fact['id'] in ids or 'fact:'+fact['id'] in ids:
            evidence['fact:'+fact['id']]={'source':'memory','data':fact}
    for ref in ids:
        if not ref.startswith('source:'):continue
        try:row=state.get_message(owner,ref.removeprefix('source:'))
        except (ValueError,PermissionError):continue
        if row['subject']!=subject or row['role']!='user':continue
        evidence[ref]={'source':'user_message','data':row}
    return evidence
