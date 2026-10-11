"""Two synthetic questions, four isolated workflows, real configured provider.

This is an optional deployment evaluation, not a unit test. All original data
and cards are fixed synthetic material. Production v5 controllers run in a separate
process against private temporary SQLite; Core runs use disposable PG schemas.
Only the expanded legacy arm raises the two original hardcoded history bounds. No response, plan,
specialist choice or model citation is supplied by a fixture in real mode.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LEGACY_FIXTURE = ROOT/'tests/legacy/production_v5'

ARMS = ('legacy', 'expanded_legacy', 'new_single_specialist', 'new_controlled_multi_specialists')
FIXED_CARDS = [
    {'card_id': 'major-00', 'orientation': 'upright'},
    {'card_id': 'cups-01', 'orientation': 'reversed'},
    {'card_id': 'pentacles-08', 'orientation': 'upright'},
]
QUESTIONS = {
    'decision': '工作安排该怎么选？已确认“我不能上夜班”。比较两个方案：A班次尚未确认，B明确白班但费用未知。结合已确认的限制，只比较现实取舍和一个可逆第一步。',
    'tarot': '已确认“我不能上夜班”。请用这组已经记录的实体塔罗牌（按顺序：major-00 upright；cups-01 reversed；pentacles-08 upright），并结合本命八字、紫微、星盘三盘反思学习与工作安排：A班次尚未确认，B明确白班但费用未知。现实条件优先，逐项保持独立依据、每张牌的实际方向与各体系局限，不把象征相似当作结局或概率。',
}
FACTS = [('constraint', '我不能上夜班'), ('preference', '我喜欢先核实班次、费用和退出条件')]
PROFILE_ITEMS = [('gender','女'),('birth.solar_datetime','2000-01-01 08:00'),('birth.location.lng',116.4),('birth.location.lat',39.9),('birth.timezone_offset',8),('birth.time_unknown',False),('birth.precision','exact')]
WORKER_OUTPUT = None
WORKER_CONTEXT = {}


def comparison_budget(arm, scenario):
    """Expose each workflow's real budget; the arms do not share one cap."""
    if arm not in ARMS or scenario not in QUESTIONS:
        raise ValueError('Unknown comparison arm or scenario')
    if arm in ARMS[:2]:
        return {'depth': 'original_v5', 'call_limit': None, 'legacy_tool_round_limit': 8}
    from mingjing_core.repositories.postgres import CALL_LIMITS
    depth = 'deep' if arm == 'new_controlled_multi_specialists' and scenario == 'tarot' else 'standard'
    return {'depth': depth, 'call_limit': CALL_LIMITS[depth]}


def persist_observations(calls):
    if WORKER_OUTPUT:
        partial=dict(WORKER_CONTEXT,status='in_progress',calls=calls,**aggregate(calls))
        WORKER_OUTPUT.write_text(json.dumps(partial,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def history_fixture():
    # Long enough that the original default context cap and 128k cap admit
    # different history sizes, without changing the old selection algorithm.
    rows = [{'id': 'known-'+str(i), 'turn_id': 'known-'+str(i), 'role': 'user',
             'content': text, 'source': 'web', 'status': 'complete',
             'at': '2026-10-01T08:00:00+08:00'} for i, (_, text) in enumerate(FACTS)]
    rows.append({'id': 'old-prediction', 'turn_id': 'old-prediction', 'role': 'assistant',
                 'content': '旧助手的未经证实预测：岗位A必然成功。这不是用户确认的现实事实。',
                 'source': 'web', 'status': 'complete', 'at': '2026-10-01T08:01:00+08:00'})
    rows.extend({'id': 'noise-'+str(i), 'turn_id': 'noise-'+str(i), 'role': 'user',
                 'content': '第'+str(i)+'条无须长期保存的合成闲聊。' + '今天只是记录普通日常细节，无关工作选择，不构成成本或熟悉程度证据。' * 60,
                 'source': 'web', 'status': 'complete', 'at': '2026-10-02T08:00:00+08:00'}
                for i in range(120))
    return rows


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode()).hexdigest()


def aggregate(calls):
    usage = {}
    for call in calls:
        for key, value in call.get('usage', {}).items():
            if type(value) in (int, float):
                usage[key] = usage.get(key, 0) + value
    return {'provider_calls': len(calls), 'usage': usage,
            'provider_latency_seconds': round(sum(c.get('latency_seconds', 0) for c in calls), 3),
            'input_body_bytes': sum(c.get('input_body_bytes', 0) for c in calls)}


def card_projection(draw):
    return [{'card_id': c['card_id'], 'orientation': c['orientation']} for c in draw['cards']]


def synthetic_contract_snapshot(value, schema, secrets=()):
    """Persist only a synthetic structured contract, never transport/thinking.

    The evaluator owns all supplied records. Projection uses the submitted tool
    schema; raw response content, request headers and extra model fields are not
    diagnostic material. Known configured keys are also removed from strings.
    """
    blocked = {'thinking', 'reasoning', 'reasoning_content', 'headers', 'authorization',
               'x_api_key', 'api_key', 'apikey', 'access_token', 'secret'}
    definitions = schema.get('$defs', {})

    def clean(item, shape):
        if '$ref' in shape:
            shape = definitions.get(shape['$ref'].rsplit('/', 1)[-1], {})
        if isinstance(item, dict):
            properties = shape.get('properties')
            return {key: clean(child, properties.get(key, {}) if properties is not None else {})
                    for key, child in item.items() if isinstance(key, str)
                    and key.lower().replace('-', '_') not in blocked
                    and (properties is None or key in properties)}
        if isinstance(item, list):
            return [clean(child, shape.get('items', {})) for child in item]
        if isinstance(item, str):
            for secret in secrets:
                if isinstance(secret, str) and len(secret) > 8:
                    item = item.replace(secret, '<redacted>')
            return item
        if type(item) is float and not math.isfinite(item):
            return '<nonfinite-number>'
        return item if item is None or type(item) in (bool, int, float) else '<invalid-json-type>'

    return clean(value, schema)


def synthetic_contract_errors(exc):
    """Pydantic error locations/types only, without input values or context."""
    if not hasattr(exc, 'errors'):
        return []
    return [{'type': issue['type'], 'location': list(issue['loc'])}
            for issue in exc.errors(include_input=False, include_url=False)[:24]]


class LegacySourceMismatch(ValueError):
    def __init__(self, name, expected, actual, byte_count):
        super().__init__('Legacy source checksum mismatch: '+name)
        self.diagnostic = {'phase': 'legacy_source_verification', 'file': name,
                           'expected_sha256': expected['sha256'], 'actual_sha256': actual,
                           'expected_bytes': expected['bytes'], 'actual_bytes': byte_count}


def verified_legacy_sources(legacy_root):
    """Require the exact original production source, including its helpers."""
    directory = Path(legacy_root)
    directory = directory/'hermes' if (directory/'hermes').is_dir() else directory
    manifest = json.loads((LEGACY_FIXTURE/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    hashes = {}
    for name, expected in manifest['files'].items():
        raw = (directory/name).read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected['sha256'] or len(raw) != expected['bytes']:
            raise LegacySourceMismatch(name, expected, actual, len(raw))
        hashes[name] = actual
    return directory, hashes


def legacy_worker(arm, scenario, legacy_root):
    """Run the original production v5 controller and its real ConversationStore."""
    import logging
    import httpx
    directory, source_hashes = verified_legacy_sources(legacy_root)
    original_source=(directory/'chat_agent.py').read_text(encoding='utf-8')
    # The production v5 has hardcoded history bounds, not a context env switch.
    expanded_source=original_source
    if arm=='expanded_legacy':
        assert original_source.count('history[-32:]')==1 and original_source.count('size+len(text)>12000')==1
        expanded_source=original_source.replace('history[-32:]','history[-124:]').replace('size+len(text)>12000','size+len(text)>96000')
    sys.path.insert(0,str(directory))
    names=('archive_store','context_engine','chart_context','guidance','semantic_index','conversation_store','chat_agent')
    previous_modules={name:sys.modules.pop(name,None) for name in names}
    calls=[];original_client=httpx.AsyncClient;known_secrets=[]
    class ObservedClient:
        def __init__(self,**kwargs):self.client=original_client(**kwargs)
        async def __aenter__(self):await self.client.__aenter__();return self
        async def __aexit__(self,*args):return await self.client.__aexit__(*args)
        async def post(self,url,**kwargs):
            body=kwargs.get('json',{});started=time.monotonic()
            record={'purpose':'legacy-tool-round','input_body_bytes':len(json.dumps(body,ensure_ascii=False).encode()),'model':body.get('model'),'usage':{}}
            calls.append(record);persist_observations(calls)
            try:
                response=await self.client.post(url,**kwargs);record['http_status']=response.status_code
                if response.status_code==200:
                    parsed=response.json();record['usage']=parsed.get('usage',{})
                    schemas={tool['name']:tool.get('input_schema',{}) for tool in body.get('tools',[])}
                    record['contract_tools']=[{'name':block['name'],
                        'output':synthetic_contract_snapshot(block.get('input'),schemas[block['name']],known_secrets)}
                        for block in parsed.get('content',[]) if block.get('type')=='tool_use' and block.get('name') in schemas]
                    record['stop_reason']=parsed.get('stop_reason')
                return response
            finally:record['latency_seconds']=round(time.monotonic()-started,3);persist_observations(calls)
    result={'arm':arm,'scenario':scenario,'synthetic_only':True,'calls':calls,**comparison_budget(arm,scenario),'legacy_controller':'production-v5-ChatAgent',
            'legacy_history_window':124 if arm=='expanded_legacy' else 32,
            'legacy_history_character_cap':96000 if arm=='expanded_legacy' else 12000,
            'legacy_frozen_tarot_capability':'unsupported: v5 has no draw store or card identity validation; the same fixed physical-card input is in the question',
            'fixed_cards_unchanged':None,'legacy_retrieval':'original SemanticIndex builtin lexical fallback; no external/private index'}
    result['legacy_source_hashes'] = source_hashes
    started=time.monotonic();old_embedding=os.environ.get('ZHIMING_EMBEDDING_MODEL');old_logging=logging.root.manager.disable
    try:
        from conversation_store import ConversationStore
        from semantic_index import SemanticIndex
        from mingjing_core.adapters.model import ConfiguredModel
        namespace={'__name__':'synthetic_legacy_controller','__file__':str(directory/'chat_agent.py')}
        exec(compile(expanded_source,str(directory/'chat_agent.py'),'exec'),namespace)
        ChatAgent=namespace['ChatAgent'];configured=ConfiguredModel()
        known_secrets.append(configured.key)
        with tempfile.TemporaryDirectory(prefix='core-provider-production-v5-') as temporary:
            base=Path(temporary);archive=base/'archive.json';profile={}
            for field,value in PROFILE_ITEMS:
                target=profile;parts=field.split('.')
                for part in parts[:-1]:target=target.setdefault(part,{})
                target[parts[-1]]=value
            archive.write_text(json.dumps({'user':profile},ensure_ascii=False),encoding='utf-8')
            store=ConversationStore(base)
            for i,(_,text) in enumerate(FACTS):
                ident='fixed-fact-'+str(i);store.begin(ident,'shared',text,[],{});store.finish(ident,'','complete');store.remember(ident,text,'背景' if i==0 else '偏好')
            for row in history_fixture()[2:]:
                ident='history-'+row['id'];message=row['content'] if row['role']=='user' else ''
                store.begin(ident,'shared',message,[],{});store.finish(ident,row['content'] if row['role']=='assistant' else '','complete')
            index=SemanticIndex(base)
            # Exercise the original controller's lexical fallback without loading
            # production embedding weights or contacting a second provider.
            os.environ['ZHIMING_EMBEDDING_MODEL']=str(base/'no-production-embedding-model')
            logging.disable(logging.CRITICAL)
            history=lambda session,exclude:store.history(session=session,exclude=exclude,limit=10000)
            agent=ChatAgent(store,index,str(archive),history,configured.key,configured.base,configured.model,'')
            turn,_=store.begin('synthetic-target','shared',QUESTIONS[scenario],[],{'date':'2026-10-11'})
            async def emit(event):pass
            httpx.AsyncClient=ObservedClient
            try:
                answer=asyncio.run(agent.run(turn,emit));store.finish(turn['id'],answer['answer'],'complete',answer.get('meta'))
                result.update(status='validated',final=answer,validation=answer.get('validation',{}))
            except Exception as exc:
                store.finish(turn['id'],'','failed');result.update(status='failed',error_type=type(exc).__name__)
    finally:
        httpx.AsyncClient=original_client;logging.disable(old_logging)
        if old_embedding is None:os.environ.pop('ZHIMING_EMBEDDING_MODEL',None)
        else:os.environ['ZHIMING_EMBEDDING_MODEL']=old_embedding
        for name in names:
            sys.modules.pop(name,None)
            if previous_modules[name] is not None:sys.modules[name]=previous_modules[name]
        sys.path.remove(str(directory))
    result.update(aggregate(calls));result['wall_seconds']=round(time.monotonic()-started,3)
    result['legacy_controller_hash']=source_hashes['chat_agent.py']
    result['executed_controller_hash']=hashlib.sha256(expanded_source.encode()).hexdigest()
    result['context_only_source_changes']=[] if arm=='legacy' else ['history[-32:] -> history[-124:]','size+len(text)>12000 -> size+len(text)>96000']
    return result


def core_worker(arm, scenario, dsn_env):
    from psycopg import sql
    from mingjing_core.adapters.model import ConfiguredModel
    from mingjing_core.application.consultation import ConsultationService
    from mingjing_core.domain.consultation import FinalAnswer
    from mingjing_core.repositories.postgres import PostgresRepository
    dsn = os.getenv(dsn_env)
    if not dsn: raise ValueError('Explicit synthetic PostgreSQL environment is required')
    if scenario == 'tarot' and arm == 'new_controlled_multi_specialists' and not os.getenv('CHART_PYTHON'):
        raise ValueError('Four-specialist comparison requires the actual configured chart interpreter')
    calls = [];validation_attempts=[];phase_events=[]
    class ObservedModel(ConfiguredModel):
        def generate(self, **kwargs):
            started = time.monotonic()
            record = {'purpose': kwargs['purpose'], 'input_body_bytes': len(json.dumps(kwargs['payload'], ensure_ascii=False).encode()),
                      'model': self.model, 'usage': {}}
            calls.append(record); persist_observations(calls)
            try:
                output = super().generate(**kwargs)
                record['usage'] = output.get('usage', {})
                record['output_contract'] = kwargs['schema'].get('title')
                record['contract_output'] = synthetic_contract_snapshot(output.get('output'),kwargs['schema'],[self.key])
                return output
            except Exception as exc:
                record['error_type']=type(exc).__name__
                record['error_code']=getattr(exc,'code',None)
                raise
            finally:
                record['latency_seconds'] = round(time.monotonic()-started, 3); persist_observations(calls)
    class DiagnosticService(ConsultationService):
        def _validate(self, owner, run, final):
            # Observational only: the original business validator decides and
            # returns unchanged. Both failed first answers and repairs remain.
            attempt={'phase':'validation','contract_output':synthetic_contract_snapshot(final,
                FinalAnswer.model_json_schema(),[self.model.key])}
            validation_attempts.append(attempt)
            try:
                issues=super()._validate(owner,run,final)
                attempt['issues']=list(issues)
                return issues
            except Exception as exc:
                attempt.update(error_type=type(exc).__name__,contract_errors=synthetic_contract_errors(exc))
                raise
    schema = 'test_compare_'+uuid.uuid4().hex[:16]
    repo = PostgresRepository(dsn, schema=schema)
    service = DiagnosticService(repo, model=ObservedModel())
    owner = 'synthetic-comparison'; repo.ensure_owner(owner)
    budget = comparison_budget(arm, scenario)
    result = {'arm': arm, 'scenario': scenario, 'synthetic_only': True, 'calls': calls,
              'validation_attempts':validation_attempts,'phase_events':phase_events, **budget}
    def observe_phase(event):
        if event.get('type') == 'status':
            phase_events.append(event['stage'])
            if WORKER_OUTPUT:
                WORKER_CONTEXT.update(last_phase=event['stage'],validation_attempts=validation_attempts)
    started = time.monotonic(); run_id = None
    try:
        case = service.memory.create_case(owner, 'self', '合成工作安排比较')['id']
        for i, (kind, text) in enumerate(FACTS):
            original = service.memory.receive(owner, content=text, source_id='fixed-fact-'+str(i), case_ids=[case])
            service.memory.save_fact(owner, 'self', original['id'], text, kind, case_id=case)
        for i, (field, value) in enumerate(PROFILE_ITEMS):
            text='请保存 '+field+'='+str(value)
            original=service.memory.receive(owner,content=text,source_id='fixed-profile-'+str(i))
            receipt=service.memory.save_fact(owner,'self',original['id'],text,'profile',field=field,value=value)
            assert receipt['write_status']=='saved'
        for row in history_fixture():
            service.memory.receive(owner, content=row['content'], source_id=row['id'], role=row['role'],
                                   conversation_id='synthetic-conversation', case_ids=[case], at=row['at'])
        draw = None
        if scenario == 'tarot':
            draw = service.tarot.create_draw(owner, subject_id='self', case_id=case,
                question=QUESTIONS[scenario], spread_id='reflect3', draw_source='manual',
                manual_cards=deepcopy(FIXED_CARDS), idempotency_key='fixed-manual-draw')['draw']
            draw = service.tarot.reveal(owner, draw['id']); assert card_projection(draw) == FIXED_CARDS
        run = service.submit(owner=owner, message=QUESTIONS[scenario], conversation_id='synthetic-conversation',
            request_id='fixed-target', case_ids=[case], depth=budget['depth'],
            selection={'date':'2026-10-11','systems':(['tarot'] if arm=='new_single_specialist' else ['tarot','bazi','ziwei','astro']) if scenario=='tarot' else []},
            draw_id=draw['id'] if draw else None)
        run_id = run['id']
        try:
            answer = service.execute(owner, run_id, observe_phase)
            result.update(status='validated', final=answer, validation=answer['validation'])
        except Exception as exc:
            result.update(status='failed', error_type=type(exc).__name__,error_code=getattr(exc,'code',None),
                          contract_errors=synthetic_contract_errors(exc))
        current = repo.fetch_run(owner, run_id)
        result['last_phase']=phase_events[-1] if phase_events else None
        result['last_completed_phase']=current['checkpoint'].get('phase')
        result['durable_budget'] = {'calls': current['calls'], 'limit': current['call_limit']}
        result['depth'] = current['request']['depth']; result['call_limit'] = current['call_limit']
        assert result['depth'] == budget['depth'] and result['call_limit'] == budget['call_limit']
        result['specialist_provider_calls'] = sum(c['purpose'].startswith('specialist:') for c in calls)
        result['base_phase_provider_calls'] = sum(c['purpose'] in ('intake', 'synthesis') or c['purpose'].startswith('specialist:') for c in calls)
        result['review_provider_calls'] = sum(c['purpose'] == 'review' for c in calls)
        result['repair_provider_calls'] = sum(c['purpose'] == 'repair' for c in calls)
        expected_specialists = (1 if arm == 'new_single_specialist' else 4) if scenario == 'tarot' else 0
        result['expected_specialist_provider_calls'] = expected_specialists
        if result.get('status') == 'validated' and result['specialist_provider_calls'] != expected_specialists:
            result['status'] = 'incomplete_specialist_scope'
        result['actual_plan'] = service._record(owner,run_id,'plan')
        assert current['calls'] == len(calls)
        if draw: result['fixed_cards_unchanged'] = card_projection(service.tarot.get_for_reading(owner, draw['id'])) == FIXED_CARDS
    finally:
        if run_id:
            current = repo.fetch_run(owner, run_id)
            for epoch in range(current.get('retry_epoch', 0)+1): service.runtime.purge(run_id, epoch)
        assert schema.startswith('test_compare_')
        with repo.transaction() as c: c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        repo.close()
    result.update(aggregate(calls)); result['wall_seconds'] = round(time.monotonic()-started, 3)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-root', type=Path, default=LEGACY_FIXTURE)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dsn-env', default='CORE_TEST_DSN')
    parser.add_argument('--scenarios', nargs='+', choices=tuple(QUESTIONS), default=list(QUESTIONS))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--worker-arm', choices=ARMS)
    parser.add_argument('--worker-scenario', choices=tuple(QUESTIONS))
    args = parser.parse_args(argv)
    if args.worker_arm:
        global WORKER_OUTPUT, WORKER_CONTEXT
        WORKER_OUTPUT=args.output;WORKER_CONTEXT={'arm':args.worker_arm,'scenario':args.worker_scenario,'synthetic_only':True,
                                                **comparison_budget(args.worker_arm,args.worker_scenario)}
        try:
            result = legacy_worker(args.worker_arm, args.worker_scenario, args.legacy_root) if args.worker_arm in ARMS[:2] else core_worker(args.worker_arm, args.worker_scenario, args.dsn_env)
        except Exception as exc:
            result = json.loads(args.output.read_text(encoding='utf-8')) if args.output.is_file() else dict(WORKER_CONTEXT)
            result.update(status='failed_setup',error_type=type(exc).__name__)
            if isinstance(exc,LegacySourceMismatch):result['setup_diagnostic']=exc.diagnostic
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        return
    from mingjing_core.adapters.model import ConfiguredModel
    model = ConfiguredModel()
    report = {'schema_version': 'core-real-provider-four-arm-v1', 'synthetic_only': True,
              'provider': 'real-configured-provider', 'model': model.model,
              'questions': {s: QUESTIONS[s] for s in args.scenarios}, 'fixed_cards': FIXED_CARDS, 'authorized_synthetic_profile':dict(PROFILE_ITEMS),
              'fixture_hash': digest({'questions': QUESTIONS, 'cards': FIXED_CARDS, 'facts': FACTS, 'profile':PROFILE_ITEMS,'history': history_fixture()}),
              'arm_budgets': {s: {arm: comparison_budget(arm,s) for arm in ARMS} for s in args.scenarios},
              'measurement_limits': [
                  'Only two fixed synthetic questions; not a statistical evaluation or predictive study.',
                  'Legacy uses original production v5 ChatAgent + ConversationStore, private temporary SQLite and the original builtin lexical fallback.',
                  'Expanded legacy only changes two history constants (32 to 124 messages, 12000 to 96000 characters); all other controller code is identical and source hashes are saved.',
                  'New single arm runs standard depth with explicit selection.systems=[tarot] for the tarot question; both reality-only decision arms run standard depth without specialists.',
                  'Controlled multi tarot uses the same question/profile, explicit selection.systems=[tarot,bazi,ziwei,astro] and deep depth. Deep review is retained and charged; actual specialist calls are recorded and missing claims are gaps. This controls interpretation scope, not model-autonomous selection.',
                  'The workflows have different budgets: '+json.dumps({s:{arm:comparison_budget(arm,s) for arm in ARMS} for s in args.scenarios},sort_keys=True)+'. Controlled tarot has six base calls (intake, four specialists, synthesis), plus deep review; semantic repair and technical retries also consume its persisted cap. This is not a same-budget comparison.',
                  'Input bytes exclude HTTP headers and differ in accounting: legacy entire request body, Core reference payload. Provider usage is authoritative.',
                  'Production v5 has no frozen Tarot store/validator. It receives exactly the same physical-card input in the question; this capability gap is explicit, never supplied by a newer controller.',
                  'No hidden thinking or API credentials are persisted; final synthetic answers need manual quality review.'],
              'source_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                (ROOT/'mingjing_core/application/consultation.py', ROOT/'mingjing_core/knowledge/builtin.json',
                                 ROOT/'mingjing_core/knowledge/registry.py', ROOT/'tests/legacy/production_v5/SOURCE_MANIFEST.json')},
              'rows': []}
    if not args.dry_run and (not model.key or not os.getenv(args.dsn_env)):
        parser.error('requires configured provider and explicit synthetic PostgreSQL DSN environment')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        report.update(status='plan_only_no_provider_calls', provider_calls=0)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8'); return
    with tempfile.TemporaryDirectory(prefix='core-provider-comparison-') as temporary:
        for scenario in args.scenarios:
            for arm in ARMS:
                child = Path(temporary)/(scenario+'-'+arm+'.json')
                started = time.monotonic()
                command = [sys.executable, str(Path(__file__).resolve()), '--legacy-root', str(args.legacy_root.resolve()),
                    '--output', str(child), '--dsn-env', args.dsn_env, '--worker-arm', arm, '--worker-scenario', scenario]
                try:
                    process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=2100)
                    row = json.loads(child.read_text(encoding='utf-8')) if child.is_file() else {
                        'arm': arm, 'scenario': scenario, 'status': 'failed_process', 'returncode': process.returncode}
                except subprocess.TimeoutExpired:
                    row=json.loads(child.read_text(encoding='utf-8')) if child.is_file() else {'arm':arm,'scenario':scenario}
                    row['status']='evaluation_timeout'
                row['process_wall_seconds'] = round(time.monotonic()-started, 3)
                report['rows'].append(row)
                report['provider_calls'] = sum(r.get('provider_calls', 0) for r in report['rows'])
                # Persist completed samples before continuing, including failures.
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
                print(json.dumps({'scenario': scenario, 'arm': arm, 'status': row['status'], 'provider_calls': row.get('provider_calls')}, ensure_ascii=False), flush=True)
    report['completed_samples'] = len(report['rows'])
    report['validated_samples'] = sum(r['status']=='validated' for r in report['rows'])
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
