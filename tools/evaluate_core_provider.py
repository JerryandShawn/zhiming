"""Real configured provider evaluation with synthetic data only, no delivery."""
import argparse, asyncio, json, os, time, uuid
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from psycopg import sql
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.adapters.channels.reports import CoreReportAdapter
from mingjing_core.domain.consultation import ModelUnavailable


async def consult_with_recovery(service, attempts, **kwargs):
    """One technical recovery of the same durable operation, never new budget.

    Retain the failed attempt in the evaluation. Contract/reference failures
    are not retried here; they remain failed samples for investigation.
    """
    try:
        return await service.consult(**kwargs)
    except ModelUnavailable:
        repo=service.repo;owner=kwargs['owner']
        with repo.transaction(owner) as connection:
            run=connection.execute(sql.SQL('SELECT id FROM {} WHERE owner=%s AND operation_id=%s').format(
                repo.table('core_runs')),(owner,kwargs['request_id'])).fetchone()
        if not run:raise
        current=repo.fetch_run(owner,run['id'])
        diagnostics=[d for d in repo.list(owner,'model_call') if d.get('run_id')==run['id'] and d.get('status')=='failed']
        failure=max(diagnostics,key=lambda d:d.get('created_at','')) if diagnostics else {}
        attempts.append({'run_id':run['id'],'operation_id':kwargs['request_id'],'status':current['status'],
            'calls':current['calls'],'limit':current['call_limit'],'failure_code':failure.get('failure_code'),
            'provider_http_status':failure.get('provider_http_status')})
        transient=failure.get('reason') in ('network','tool_count','json','tool_input') or (
            failure.get('reason')=='http' and (failure.get('provider_http_status')==429 or
                                             (failure.get('provider_http_status') or 0)>=500))
        if not transient or current['status']!='failed' or current['calls']>=current['call_limit']:raise
        retry=repo.prepare_retry(owner,run['id'])
        if retry['purge_checkpoint']:service.runtime.purge(run['id'],retry['run']['retry_epoch']-1)
        result=await asyncio.to_thread(service.execute,owner,run['id'])
        after=repo.fetch_run(owner,run['id'])
        attempts.append({'run_id':run['id'],'operation_id':kwargs['request_id'],'status':after['status'],
                         'calls':after['calls'],'limit':after['call_limit']})
        return result

async def evaluate(output):
    service=ConsultationService.from_base();repo=service.repo
    owner='provider_eval_'+uuid.uuid4().hex[:16];repo.ensure_owner(owner)
    profile={'gender':'男','birth.solar_datetime':'1990-05-03 13:18','birth.location.lng':104.07,'birth.location.lat':30.67,'birth.timezone_offset':8,'birth.precision':'exact'}
    text='请保存我已核对并确认的合成出生资料：\n'+'\n'.join(f'{k}：{v}' for k,v in profile.items())
    source=service.memory.receive(owner,content=text,source_id='synthetic-profile')
    grant=service.memory.grant_authorization(owner,'self',source['id'],text,kinds=['profile'],operation_id='synthetic-profile-consent')
    for field,value in profile.items():service.memory.save_fact(owner,'self',source['id'],f'{field}：{value}','profile',field=field,value=value,authorization_id=grant['id'],operation_id='profile:'+field)
    case_source=service.memory.receive(owner,content='合成学习决策。目标：在固定白天时间内学习',source_id='synthetic-case-source')
    case=service.memory.create_case(owner,'self','合成学习决策',goal='在固定白天时间内学习',message_id=case_source['id'],operation_id='synthetic-case')
    draw=service.tarot.create_draw(owner,subject_id='self',case_id=case['id'],question='如何在白天安排学习？',spread_id='reflect3',draw_source='manual',manual_cards=[{'card_id':'major-00','orientation':'upright'},{'card_id':'major-02','orientation':'reversed'},{'card_id':'major-08','orientation':'upright'}],idempotency_key='synthetic-fixed-cards')['draw']
    draw=service.tarot.reveal(owner,draw['id']);fixed=draw['cards']
    cases=[('memory','请记住：我不能上夜班。请帮我考虑白天的学习安排。',{},'standard'),
           ('recall','请结合我之前说明的工作限制，安排一个现实的小行动，不要排盘。',{},'standard'),
           ('bazi','请依据八字讨论2026-10-11的学习反思角度，保留专业字段和局限。',{},'standard'),
           ('ziwei','请依据紫微命盘讨论2026-10-11的学习主题，保留专业字段和局限。',{},'standard'),
           ('astro','请依据西方星盘讨论2026-10-11的学习主题，保留专业字段和局限。',{},'standard'),
           ('tarot','请解释这次固定塔罗的学习反思，给一个现实行动。',{'draw_id':draw['id']},'standard'),
           ('fusion','请把八字、紫微和西方星盘在2026-10-11的学习主题下对照，说明差异与缺失，不能提供事件概率。',{},'deep'),
           ('decision','A是每周白天两小时的课程，B是夜间两小时课程，两者费用与退出条件未知。应该怎么选？不要排盘。',{},'standard')]
    report={'schema':'core-provider-evaluation-v1','synthetic_only':True,'owner':owner,'model':service.model.model,'samples':[],'messages_sent':0,'new_paid_services':0}
    for name,message,extra,depth in cases:
        started=time.monotonic();item={'sample':name,'depth':depth,'ok':False,'technical_attempts':[]}
        try:
            result=await consult_with_recovery(service,item['technical_attempts'],owner=owner,message=message,request_id='evaluate:'+name,depth=depth,**extra)
            run=repo.fetch_run(owner,result['meta']['core_run']['run_id'])
            item.update(ok=True,run_id=run['id'],calls=run['calls'],limit=run['call_limit'],validated=result['validation'],systems=result['meta']['plan']['systems'],claims=len(result['cited_claim_ids']),facts=len(result['cited_fact_ids']),save_receipts=[{k:r.get(k) for k in ('write_status','fact_id','revision')} for r in result['memory_receipts']],summary=result['plain_summary'],answer=result['answer'],professional_appendix=result['professional_appendix'])
            if name=='tarot' and service.tarot.get(owner,draw['id'])['cards']!=fixed:raise RuntimeError('fixed tarot changed')
            if name in ('memory','recall'):
                constraints=[f for f in service.memory.facts(owner) if '不能上夜班' in f.get('content','')]
                if not constraints:raise RuntimeError('authorized constraint missing')
                if name=='memory' and not any(r.get('write_status')=='saved' and r.get('fact_id') in {f['id'] for f in constraints}
                                              for r in result['memory_receipts']):raise RuntimeError('actual save receipt missing')
                if name=='recall' and not set(result['cited_fact_ids']).intersection(f['id'] for f in constraints):raise RuntimeError('recall omitted constraint citation')
        except Exception as exc:
            item.update(ok=False,error_code=getattr(exc,'code',type(exc).__name__),error=str(exc))
            with repo.connection() as connection:
                failed=connection.execute(sql.SQL('SELECT id,calls,call_limit,status,error FROM {} WHERE owner=%s AND operation_id=%s').format(repo.table('core_runs')),(owner,'evaluate:'+name)).fetchone()
                if failed:item.update(run_id=failed['id'],calls=failed['calls'],limit=failed['call_limit'],run_status=failed['status'])
        item['latency_seconds']=round(time.monotonic()-started,3);report['samples'].append(item)
        Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:item[k] for k in ('sample','ok','latency_seconds')},ensure_ascii=False),flush=True)
    report_external='synthetic-report:'+owner
    repo.bind_channel(owner,'report',report_external,binding_kind='task')
    started=time.monotonic();item={'sample':'report','ok':False}
    try:
        result=await CoreReportAdapter('.',service=service).prepare(external_id=report_external,kind='daily',day='2026-10-12')
        item.update(ok=True,run_id=result['meta']['core_run']['run_id'],calls=result['meta']['core_run']['calls'],limit=result['meta']['core_run']['call_limit'],summary=result['plain_summary'],answer=result['answer'],validated=result['validation'])
    except Exception as exc:
        item.update(error_code=getattr(exc,'code',type(exc).__name__),error=str(exc))
        with repo.connection() as connection:
            failed=connection.execute(sql.SQL('SELECT id,calls,call_limit,status FROM {} WHERE owner=%s AND operation_id=%s').format(repo.table('core_runs')),(owner,'report:'+report_external+':daily:2026-10-12')).fetchone()
            if failed:item.update(run_id=failed['id'],calls=failed['calls'],limit=failed['call_limit'],run_status=failed['status'])
    item['latency_seconds']=round(time.monotonic()-started,3);report['samples'].append(item)
    charges=repo.list(owner,'model_call');report['usage_samples']=[{k:x.get(k) for k in ('run_id','purpose','status','reason','failure_code','provider_http_status','stop_reason','tool_count','usage','usage_known','latency_seconds','model')} for x in charges]
    report['all_passed']=all(x['ok'] for x in report['samples'])
    report['technical_recovery_samples']=sum(bool(x.get('technical_attempts')) for x in report['samples'])
    with repo.connection() as connection:
        report['provider_calls']=connection.execute(sql.SQL('SELECT COALESCE(sum(calls),0) AS n FROM {} WHERE owner=%s').format(repo.table('core_runs')),(owner,)).fetchone()['n']
    report['cost']={'reported_usage':True,'billing_amount':'not_returned_by_provider','basis':'Existing configured subscription/provider; token counts recorded; no invented monetary fee'}
    Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');repo.close()
    return report['all_passed']

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
    raise SystemExit(0 if asyncio.run(evaluate(args.output)) else 1)
