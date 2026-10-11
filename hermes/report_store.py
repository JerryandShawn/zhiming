"""Validate and upsert complete reports before scheduler delivery."""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from archive_store import transaction, deep_merge, read_json
from state_store import StateStore,RevisionConflict,ScopeError

def store(path, date, kind, content, structured=None, dates=None, *,state=None,owner=None,subject='self',expected_revision=None,run_id=None):
    datetime.strptime(date, '%Y-%m-%d')
    if kind not in ('晨报','周报','月报','季报'):
        raise ValueError('报告类型无效')
    if date>='2026-09-30' and structured is None:
        raise ValueError('新报告必须通过结构化校验，不能用纯文本绕过')
    if state is None and date>='2026-09-30' and (Path(path).parent/'state.sqlite').exists():
        raise ScopeError('共享状态已启用，报告必须使用显式绑定身份与上下文版本')
    effective=read_json(path,{})
    context_meta=None
    authorized=None
    if state is not None:
        from context_query import ChannelContext
        from context_builder import ContextBuilder
        if not owner:raise ScopeError('报告必须明确归属用户')
        if run_id:
            trace=state.get_trace(owner,run_id)
            if trace['subject']!=subject:raise ScopeError('报告上下文属于其他人物')
            recorded=trace['payload']['revision']
            if expected_revision is not None and expected_revision!=recorded:raise RevisionConflict('报告上下文版本与服务端执行记录不一致')
            expected_revision=recorded
        if expected_revision is None:raise RevisionConflict('报告提交必须携带生成时读取的资料版本')
        if state.revision(owner)!=expected_revision:raise RevisionConflict('报告生成后资料已更正，请重新读取最新状态生成')
        bridge=ChannelContext(state.path.parent);bridge.state=state
        effective=bridge.archive(owner,subject)
        _,_,_,context_meta=ContextBuilder(state).build(owner,subject,'三盘联动'+kind,bridge.history(owner,subject))
        if context_meta['revision']!=expected_revision:raise RevisionConflict('报告校验期间资料发生变化')
        from domain_context import registered_evidence
        if run_id:authorized=registered_evidence(state,owner,subject,trace)
        else:
            authorized={f'fact:{f["id"]}':{'source':'memory','data':f} for f in state.snapshot(owner,subject)['facts'] if f['assertion_status'] in ('user_asserted','user_confirmed')}
    if structured is not None:
        from guidance import validate_document
        dates=dates or [date]
        if date not in dates: raise ValueError('计算日期须包含报告日期')
        content=date+' '+kind+'\n\n'+validate_document(structured,effective,dates,'三盘联动'+kind,authorized)
    if len(content.strip())<200:
        raise ValueError('报告不足200字，拒绝保存空报告或片段')
    record={'id':date+'-'+{'晨报':'daily','周报':'weekly','月报':'monthly','季报':'quarterly'}[kind],
            'date':date,'type':kind,'content':content.strip(),'channel':'cron','schema_version':'3.0'}
    if structured is not None:
        record.update(schema_version='5.0', guidance=structured,
                      validation={'chart_fields_checked':True,'synthesis_coverage_checked':True,
                                  'scope':'仅校验来源字段与结构，不证明象征解释或预测成立'})
    if state is not None:
        record.update(owner_user_id=owner,subject_id=subject,state_revision=expected_revision,context_meta=context_meta,run_id=run_id)
        record.setdefault('validation',{})['state_revision_checked']=True
    def update(arc):
        if state is not None:
            bound=arc.get('state_report_owner')
            if bound and bound!={'owner':owner,'subject':subject}:raise ScopeError('此报告归档文件已绑定其他用户或人物，请使用隔离的输出位置')
            arc['state_report_owner']={'owner':owner,'subject':subject}
        deep_merge(arc, {'reports':[record]})
        return arc.get('config',{}).get('site_url','').rstrip('/')+'/#/reports?date='+date
    if state is None:return transaction(path, update, {})
    # No model/tool execution while holding this short commit fence. Corrections
    # cannot slip between the final revision check and the exported archive.
    with state.db(write=True) as c:
        state._revision(c,owner,expected_revision)
        return transaction(path,update,{})

def store_structured(path, date, kind, document, dates=None, **state_args):
    return store(path,date,kind,'',structured=document,dates=dates,**state_args)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--date',required=True)
    p.add_argument('--type',required=True)
    inputs=p.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--file')
    inputs.add_argument('--structured',help='v5结构化JSON，重算三盘并校验字段后落库')
    p.add_argument('--dates',help='逗号分隔的实际分析日期，包含报告日期，最多7个')
    p.add_argument('--archive',default=os.path.expanduser('~/.hermes/zhiming/archive.json'))
    p.add_argument('--base',default=os.environ.get('ZHIMING_BASE'))
    p.add_argument('--channel',default=os.environ.get('ZHIMING_CHANNEL'))
    p.add_argument('--external-id',default=os.environ.get('ZHIMING_EXTERNAL_ID'))
    p.add_argument('--run-id',help='chart_context/context_query 返回的服务端上下文执行编号')
    p.add_argument('--revision',type=int,help='受控内部调用可显式传递上下文版本；推荐 --run-id')
    a=p.parse_args()
    from context_query import ChannelContext
    bridge=ChannelContext(a.base or Path(a.archive).parent)
    binding=bridge.identity(a.channel,a.external_id)
    state_args={'state':bridge.state,'owner':binding['owner'],'subject':binding['subject'],'expected_revision':a.revision,'run_id':a.run_id}
    if a.structured:
        document=json.loads(Path(a.structured).read_text(encoding='utf-8'))
        url=store_structured(a.archive,a.date,a.type,document,a.dates.split(',') if a.dates else None,**state_args)
    else:
        url=store(a.archive,a.date,a.type,Path(a.file).read_text(encoding='utf-8'),**state_args)
    result={'ok':True,'url':url}
    if a.structured:
        result['content']=next(r['content'] for r in read_json(a.archive)['reports'] if r.get('date')==a.date and r.get('type')==a.type)
    print(json.dumps(result,ensure_ascii=False))
