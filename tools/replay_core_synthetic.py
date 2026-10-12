"""Seeded target-round replay through real memory/service/PG and a fixture provider.

Four arms: actual legacy StateStore candidate/context replay, the same with full
history, real Core fast, real Core standard with on-demand specialist planning.
The two legacy arms do not execute the retired controller or its model. This is
an input/permission/context experiment, not a model quality or predictive study.
All sources and answers are fixed synthetic material; no production is read.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import time
import uuid
from psycopg import sql

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from tests.test_core_runtime import ProgrammableProvider

SCENARIOS=('constraint_recall','no_save','third_party','old_prediction','correction','multi_case')


class ReplayProvider(ProgrammableProvider):
    def generate(self,**kwargs):
        response=super().generate(**kwargs)
        if kwargs['purpose'] in ('synthesis','repair'):
            facts=kwargs['payload'].get('reference_data',{}).get('facts',[])
            response['output']['explanation']='本轮有效用户陈述：'+'；'.join(f['content'] for f in facts)
        return response


def source_fixture(scenario):
    a='我喜欢深夜学习' if scenario=='correction' else '我不能上夜班'
    rows=[('critical','user',a,'A'),('cost','user','我不能接受额外费用','B'),
          ('irrelevant','user','我不能通宵开会','C'),('global','user','我喜欢先核对实际成本',None),
          ('prediction','assistant','旧助手预测：今年必定成功','A'),
          ('third','user','同事说他喜欢深夜学习','A')]
    rows.extend(('noise-'+str(i),'user','这是无须长期保存的合成日常记录'+str(i),'A') for i in range(36))
    message='请根据已经确认的限制安排今天的学习。'
    proposal=None
    if scenario=='no_save':message='不要记住这件事，我喜欢独自学习。';proposal={'quote':'我喜欢独自学习','category':'偏好'}
    if scenario=='third_party':message='朋友喜欢深夜学习，我只是在转述。';proposal={'quote':'朋友喜欢深夜学习','category':'偏好'}
    if scenario=='old_prediction':message='请区分旧助手预测与我真实确认的限制。'
    if scenario=='correction':message='更正：我现在可以上夜班';proposal={'quote':message,'category':'更正','supersedes':'critical'}
    selected=['A','B'] if scenario=='multi_case' else ['A']
    expected={a,'我喜欢先核对实际成本'}
    if scenario=='correction':expected.discard(a);expected.add(message)
    if scenario=='multi_case':expected.add('我不能接受额外费用')
    return rows,message,proposal,selected,expected


def context_checks(repo,service,owner,run,data,selected,expected,scenario,case_a):
    """Independent oracle: a single current quote never counts as durable memory."""
    provided=data['facts'];durable=[f for f in provided if not f.get('context_only')]
    current_quotes=[f for f in provided if f.get('context_only')]
    selected_ids=service.memory.facts(owner,'self',selected)
    source_id=service._record(owner,run['id'],'intake')['source_id']
    source=service.memory.get_source(owner,source_id)
    ids=[f['id'] for f in provided]
    checks={'unique_context_ids':len(ids)==len(set(ids)),
        'durable_contents':len(durable)==len(expected) and {f['content'] for f in durable}==expected,
        'durable_scope_ids':{f['id'] for f in durable}=={f['id'] for f in selected_ids},
        'owner_subject_case_scope':all(f.get('owner_user_id')==owner and f.get('subject_id')=='self'
            and f.get('case_id') in [None,*selected] for f in provided)}
    # This scenario alone permits exactly this observed first-person quote.
    # Third-person, correction, unknown or missing quotes receive no exception.
    expected_quotes=['我喜欢独自学习'] if scenario=='no_save' else []
    checks['current_quote_count']=len(current_quotes)==len(expected_quotes)
    checks['current_quote_contents']=[f['content'] for f in current_quotes]==expected_quotes
    valid=True
    for fact in current_quotes:
        quote='我喜欢独自学习';start=run['request']['message'].find(quote);end=start+len(quote)
        ident='current_source_'+fingerprint([owner,source_id,start,end,'preference',case_a,None,None])[:32]
        refs=fact.get('source_refs',[])
        valid=valid and scenario=='no_save' and start>=0 and fact['id']==ident and fact.get('case_id')==case_a
        valid=valid and source.get('role')=='user' and source.get('subject_id')=='self' and source['content']==run['request']['message']
        valid=valid and source.get('policy',{}).get('origin')=='current_user' and source.get('policy',{}).get('run_context') is True
        valid=valid and fact.get('kind')=='preference' and fact.get('status')=='current_source' and fact.get('assertion_status')=='current_source'
        valid=valid and fact.get('consent')=='current_round' and fact.get('retention')=='current_round'
        valid=valid and fact.get('field') is None and fact.get('value') is None and fact.get('revision')==source['revision']
        valid=valid and refs==[{'message_id':source_id,'version':source['revision'],'start':start,'end':end,'quote':quote}]
        valid=valid and run['dependencies'].get('message:'+source_id)==source['revision'] and 'fact:'+ident not in run['dependencies']
    checks['current_quote_exact_source_scope_version']=bool(valid)
    all_persisted_ids={f['id'] for f in repo.list(owner,'fact',include_deleted=True)}
    checks['current_quotes_not_persisted']=not {f['id'] for f in current_quotes}&all_persisted_ids
    return checks,durable,current_quotes


def core_arm(repo,scenario,index,depth):
    owner='replay-'+depth+'-'+str(index)
    repo.ensure_owner(owner);provider=ReplayProvider();service=ConsultationService(repo,model=provider)
    cases={label:service.memory.create_case(owner,'self','合成事项'+label,operation_id='case-'+label)['id'] for label in ('A','B','C')}
    rows,message,proposal,selected,expected=source_fixture(scenario)
    facts={}
    for key,role,text,label in rows:
        source=service.memory.receive(owner,content=text,source_id=key,role=role,channel='synthetic',case_ids=[cases[label]] if label else [])
        if key in ('critical','cost','irrelevant','global'):
            facts[key]=service.memory.save_fact(owner,'self',source['id'],text,'preference' if key=='global' or scenario=='correction' and key=='critical' else 'constraint',case_id=cases[label] if label else None)
    if proposal:
        proposal=deepcopy(proposal);proposal['case_id']=cases['A']
        if proposal.get('supersedes'):proposal['supersedes']=facts[proposal['supersedes']]['id']
    provider.proposal=proposal
    run=service.submit(owner=owner,message=message,request_id='target',case_ids=[cases[x] for x in selected],depth=depth)
    answer=service.execute(owner,run['id'])
    data=next(r['payload']['reference_data'] for r in reversed(provider.requests) if r['purpose']=='synthesis')
    current=repo.fetch_run(owner,run['id'])
    checks,durable,current_quotes=context_checks(repo,service,owner,current,data,[cases[x] for x in selected],expected,scenario,cases['A'])
    checks['cited_scope_ids']=len(answer['cited_fact_ids'])==len(data['facts']) and set(answer['cited_fact_ids'])=={f['id'] for f in data['facts']}
    checks['target_budget']=current['calls']==len(provider.requests) and current['calls']<=current['call_limit']
    saved=sum(r.get('write_status')=='saved' for r in answer['memory_receipts'])
    checks['actual_write_receipts']=saved==(1 if scenario=='correction' else 0)
    # Read through a fresh service after completion; no model or effect is replayed.
    restarted_provider=ReplayProvider();restarted=ConsultationService(repo,model=restarted_provider)
    replay=restarted.submit(owner=owner,message=message,request_id='target',case_ids=[cases[x] for x in selected],depth=depth)
    checks['exact_replay_no_calls']=replay['status']=='succeeded' and replay['id']==run['id'] and replay['result']==answer and restarted.execute(owner,replay['id'])==answer and not restarted_provider.requests
    probe_calls=None;probe_run=None
    if scenario=='no_save':
        # A separate real round with no proposal may read prior original history,
        # but it cannot inherit the former run's temporary fact identities.
        probe_run=restarted.submit(owner=owner,message='只按已确认的限制安排下一步学习。',request_id='continuation-oracle',case_ids=[cases[x] for x in selected],depth=depth)
        probe_answer=restarted.execute(owner,probe_run['id'])
        probe_data=next(r['payload']['reference_data'] for r in reversed(restarted_provider.requests) if r['purpose']=='synthesis')
        probe_current=repo.fetch_run(owner,probe_run['id']);probe_calls=probe_current['calls']
        checks['next_round_no_current_quote']=not any(f.get('context_only') for f in probe_data['facts']) and {f['content'] for f in probe_data['facts']}==expected
        checks['next_round_cited_durable_only']=set(probe_answer['cited_fact_ids'])=={f['id'] for f in durable} and not {f['id'] for f in current_quotes}&set(probe_answer['cited_fact_ids'])
        checks['next_round_no_save_or_budget_reset']=not probe_answer['memory_receipts'] and probe_calls==len(restarted_provider.requests) and probe_calls<=probe_current['call_limit'] and repo.fetch_run(owner,run['id'])['calls']==current['calls']
        checks['next_round_durable_unchanged']={f['id'] for f in service.memory.facts(owner,'self',[cases[x] for x in selected])}=={f['id'] for f in durable}
    size=len(json.dumps(data,ensure_ascii=False,default=str))
    for epoch in range(current.get('retry_epoch',0)+1):service.runtime.purge(run['id'],epoch)
    if probe_run:
        for epoch in range(probe_current.get('retry_epoch',0)+1):restarted.runtime.purge(probe_run['id'],epoch)
    return {'passed':all(checks.values()),'checks':checks,'context_characters':size,'calls':current['calls'],'call_limit':current['call_limit'],
            'saved_receipts':saved,'replay_provider_calls':0 if checks['exact_replay_no_calls'] else None,
            'target_provider_calls':current['calls'],'continuation_probe_calls':probe_calls,
            'combined_provider_calls':current['calls']+(probe_calls or 0),'real_model_calls':0,
            'expected_fact_count':len(expected),'actual_fact_count':len(durable),
            'expected_durable_fact_count':len(expected),'actual_durable_fact_count':len(durable),
            'expected_current_quote_count':1 if scenario=='no_save' else 0,'actual_current_quote_count':len(current_quotes),
            'expected_context_fact_count':len(expected)+(1 if scenario=='no_save' else 0),'actual_context_fact_count':len(data['facts'])}


def legacy_arms(store_class,scenario):
    rows,message,proposal,selected,expected=source_fixture(scenario)
    with tempfile.TemporaryDirectory(prefix='core-replay-legacy-') as directory:
        store=store_class(directory);store.ensure_owner('synthetic')
        cases={x:store.create_case('synthetic','self','合成事项'+x,case_id='case-'+x)['id'] for x in ('A','B','C')}
        facts={};history=[]
        for key,role,text,label in rows:
            source=store.import_message('synthetic','web',key,role,text,subject='self',case=cases[label] if label else None)
            history.append({'role':role,'content':text})
            if key in ('critical','cost','irrelevant','global'):
                facts[key]=store.put_fact('synthetic','self',text,[{'message_id':source['id'],'quote':text}],kind='preference' if key=='global' or scenario=='correction' and key=='critical' else 'constraint',case_id=cases[label] if label else None)
        source=store.import_message('synthetic','web','target','user',message,subject='self',case=cases['A'])
        write_status='not_requested'
        if proposal:
            try:
                result=store.put_fact('synthetic','self',proposal['quote'],[{'message_id':source['id'],'quote':proposal['quote']}],
                          kind='correction' if proposal.get('supersedes') else 'preference',case_id=cases['A'],
                          supersedes_id=facts[proposal['supersedes']]['id'] if proposal.get('supersedes') else None,
                          expected_revision=store.revision('synthetic'),explicit=True)
                write_status='saved' if result.get('status')=='active' else result.get('status','unknown')
            except (ValueError,PermissionError):write_status='rejected'
        collected={}
        for label in selected:
            for fact in store.snapshot('synthetic',case=cases[label])['facts']:collected[fact['id']]=fact
        actual={f['content'] for f in collected.values()}
        passed=actual==expected
        if scenario in ('no_save','third_party'):passed=passed and write_status!='saved'
        def arm(history_rows):
            return {'passed':passed,'context_characters':len(json.dumps({'facts':list(collected.values()),'history':history_rows},ensure_ascii=False,default=str)),
                    'calls':None,'write_status':write_status,'expected_fact_count':len(expected),'actual_fact_count':len(actual)}
        return arm(history[-12:]),arm(history)


def replay(*,dsn,legacy_root,rounds=300,seed=311021):
    legacy_file=Path(legacy_root)/'hermes/state_store.py'
    spec=importlib.util.spec_from_file_location('synthetic_legacy_state_store',legacy_file)
    legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
    schema='test_replay_'+uuid.uuid4().hex[:16];repo=PostgresRepository(dsn,schema=schema)
    scenarios=[SCENARIOS[i%len(SCENARIOS)] for i in range(rounds)];random.Random(seed).shuffle(scenarios)
    source_files=(ROOT/'mingjing_core/application/consultation.py',ROOT/'mingjing_core/application/memory.py',ROOT/'mingjing_core/runtime/graph.py')
    source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    started=time.monotonic();rows=[]
    try:
        for index,scenario in enumerate(scenarios):
            old,expanded=legacy_arms(legacy.StateStore,scenario)
            single=core_arm(repo,scenario,index,'fast');multi=core_arm(repo,scenario,index,'standard')
            rows.append({'round':index+1,'scenario':scenario,'legacy_candidate_context':old,'expanded_legacy_history':expanded,'new_single_fast':single,'new_on_demand_standard':multi})
            if (index+1)%25==0:print(json.dumps({'completed_rounds':index+1,'total':rounds}),flush=True)
        arms={name:{'passed':sum(r[name]['passed'] for r in rows),'rounds':rounds,
                    'provider_calls':sum(r[name]['calls'] or 0 for r in rows) if name.startswith('new_') else None,
                    **({'target_provider_calls':sum(r[name]['target_provider_calls'] for r in rows),
                        'continuation_probe_calls':sum(r[name]['continuation_probe_calls'] or 0 for r in rows),
                        'combined_provider_calls':sum(r[name]['combined_provider_calls'] for r in rows),
                        'real_model_calls':0} if name.startswith('new_') else {}),
                    'mean_context_characters':round(sum(r[name]['context_characters'] for r in rows)/rounds,2)}
              for name in ('legacy_candidate_context','expanded_legacy_history','new_single_fast','new_on_demand_standard')}
        return {'schema_version':'core-synthetic-replay-v1','seed':seed,'rounds':rounds,'synthetic_only':True,
                'provider':'fixture-only','real_model_calls':0,'elapsed_seconds':round(time.monotonic()-started,2),
                'target_provider_calls':sum(arms[name]['target_provider_calls'] for name in ('new_single_fast','new_on_demand_standard')),
                'continuation_probe_calls':sum(arms[name]['continuation_probe_calls'] for name in ('new_single_fast','new_on_demand_standard')),
                'combined_provider_calls':sum(arms[name]['combined_provider_calls'] for name in ('new_single_fast','new_on_demand_standard')),
                'scenario_counts':dict(Counter(scenarios)),'arms':arms,'rows':rows,
                'source_hashes':source_hashes,
                'source_hashes_after':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},
                'source_unchanged_during_run':all(source_hashes[str(p.relative_to(ROOT))]==hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files),
                'legacy_source_hash':hashlib.sha256(legacy_file.read_bytes()).hexdigest(),
                'measurement_limits':['Legacy arms run original StateStore candidate/context API, not the retired controller/model.',
                    'The expanded arm changes history size only; it is not a new permission policy.',
                    'Provider responses are scripted; this measures service effects, evidence and context, not real model quality.',
                    'Core fact counts mean durable facts; current-round exact quotes are counted separately and are not saved facts.',
                    'Target provider calls and additional no-save continuation-oracle calls are reported separately.',
                    'Ordinary conversation invokes no forced specialists. Real model comparison remains a separate deployment record.']}
    finally:
        assert schema.startswith('test_replay_')
        with repo.transaction() as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        repo.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--rounds',type=int,default=300)
    parser.add_argument('--seed',type=int,default=311021);parser.add_argument('--legacy-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if not 1<=args.rounds<=2000:parser.error('rounds must be 1..2000')
    settings=ROOT.parent/'dev-environment.json'
    dsn=os.getenv('CORE_TEST_DSN') or (json.loads(settings.read_text())['dsn'] if settings.is_file() else '')
    if not dsn:parser.error('requires disposable CORE_TEST_DSN')
    report=replay(dsn=dsn,legacy_root=args.legacy_root,rounds=args.rounds,seed=args.seed)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'arms':report['arms'],'scenario_counts':report['scenario_counts']},ensure_ascii=False))
    if any(report['arms'][arm]['passed']!=args.rounds for arm in ('new_single_fast','new_on_demand_standard')):sys.exit(1)
