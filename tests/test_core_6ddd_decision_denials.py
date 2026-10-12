"""Full original synthetic 6ddd decision via actual PG/Core/LangGraph.

Only provider responses are substituted. Reference rebinding requires the
actual saved literal, subject, case and original source span, never an ordinal.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
import uuid

from psycopg import sql
from mingjing_core.domain.consultation import InvalidAnswer
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_memory import test_dsn
from tests.test_core_76b_provider_denials import ObservedService,LocalAnswerModel,GUARANTEE

FIXTURE=Path(__file__).parent/'fixtures'/'6ddd_decision_denials.json'


class Original6dddDecisionModel:
    def __init__(self,evidence,saved_receipt):
        self.evidence=evidence;self.saved=saved_receipt;self.calls=[];self.mapping={};self.outputs={}

    def bind(self,value):
        if isinstance(value,dict):return {key:self.bind(item) for key,item in value.items()}
        if isinstance(value,list):return [self.bind(item) for item in value]
        if isinstance(value,str):
            for original,actual in self.mapping.items():value=value.replace(original,actual)
        return value

    def generate(self,**kwargs):
        purpose=kwargs['purpose'];self.calls.append(purpose)
        if purpose not in self.evidence['outputs']:raise AssertionError('Unexpected phase')
        facts=kwargs['payload']['reference_data'].get('facts',[])
        if purpose in ('synthesis','repair'):
            binding=self.evidence['memory_binding']
            matches=[f for f in facts if f.get('content')==binding['literal']
                     and f.get('kind')==binding['kind'] and f.get('subject_id')==binding['subject_id']
                     and f.get('case_id')==binding['case_id']]
            if len(matches)!=1:raise AssertionError('Saved original literal has no unique subject/case fact')
            actual=matches[0];expected=self.saved
            if (actual['id']!=expected['fact_id'] or actual.get('owner_user_id')!=expected['owner_user_id']
                    or actual['status']!='active' or actual['revision']!=expected['revision']
                    or actual.get('context_only')):raise AssertionError('Reference is not the actual saved receipt')
            span=binding['original_source_ref'];refs=actual.get('source_refs',[])
            if len(refs)!=1 or any(refs[0].get(key)!=span[key] for key in ('version','start','end','quote')):
                raise AssertionError('Literal original span differs')
            if refs[0]['message_id']!=expected['source_refs'][0]['message_id']:
                raise AssertionError('Literal source identity differs')
            self.mapping={binding['original_fact_id']:actual['id']}
        output=self.bind(deepcopy(self.evidence['outputs'][purpose]));self.outputs[purpose]=deepcopy(output)
        return {'output':output,'usage':{'input_tokens':1,'output_tokens':1},'model':'synthetic-original-6ddd-decision'}


class Original6dddDecisionDenials(unittest.TestCase):
    def setUp(self):
        self.evidence=json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.schema='test_6ddd_decision_'+uuid.uuid4().hex[:16]
        self.repo=PostgresRepository(test_dsn(),schema=self.schema,max_size=4)
        self.owner='synthetic-6ddd-decision';self.repo.ensure_owner(self.owner)
        self.service=ObservedService(self.repo,model=LocalAnswerModel('先核实真实条件。'))
        binding=self.evidence['memory_binding'];source=self.service.memory.receive(self.owner,
            binding['subject_id'],content=binding['memory_question'],source_id='actual-known-memory-original',case_ids=[])
        self.receipt=self.service.memory.save_fact(self.owner,binding['subject_id'],source['id'],
            binding['literal'],binding['kind'],case_id=binding['case_id'],operation_id='actual-known-memory-save')
        self.assertEqual(self.receipt['write_status'],'saved');self.assertEqual(self.receipt['subject_id'],'self')
        self.assertIsNone(self.receipt['case_id']);self.assertEqual(self.receipt['content'],'我不能上夜班')
        span=binding['original_source_ref'];self.assertEqual(len(self.receipt['source_refs']),1)
        for key in ('version','start','end','quote'):self.assertEqual(self.receipt['source_refs'][0][key],span[key])
        self.assertEqual(source['content'][span['start']:span['end']],binding['literal'])
        self.model=Original6dddDecisionModel(self.evidence,self.receipt);self.service.model=self.model

    def tearDown(self):
        with self.repo.connection() as connection:
            runs=connection.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for run in runs:
            for epoch in range(run['retry_epoch']+1):self.service.runtime.purge(run['id'],epoch)
        self.assertTrue(self.schema.startswith('test_6ddd_decision_'))
        with self.repo.connection() as connection:connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def local(self,passage,operation,*,unsafe_appendix=None):
        self.service.model=LocalAnswerModel(passage)
        if unsafe_appendix is not None:
            generate=self.service.model.generate
            def with_appendix(**kwargs):
                result=generate(**kwargs)
                if kwargs['purpose'] in ('synthesis','repair'):result['output']['professional_appendix']=unsafe_appendix
                return result
            self.service.model.generate=with_appendix
        run=self.service.submit(owner=self.owner,message='费用和退出条件未知，只比较现实条件，不排盘。',
                                request_id=operation,depth='standard')
        return run,self.service.execute(self.owner,run['id'])

    def run_for(self,operation):
        with self.repo.connection() as connection:
            row=connection.execute(sql.SQL('SELECT id FROM {} WHERE owner=%s AND operation_id=%s').format(
                self.repo.table('core_runs')),(self.owner,operation)).fetchone()
        return self.repo.fetch_run(self.owner,row['id'])

    def test_complete_original_unsafe_synthesis_repairs_once_three_calls_and_replays_free(self):
        before=hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only']);self.assertEqual(self.evidence['original_calls'],3)
        self.assertEqual(self.evidence['source_commit'],'6ddd9196c1e0230e3207071e4f2f0e396734f557')
        self.assertRegex(self.evidence['source_sha256'],r'^[0-9a-f]{64}$')
        self.assertRegex(self.evidence['evaluation_sha256'],r'^[0-9a-f]{64}$')
        run=self.service.submit(owner=self.owner,message=self.evidence['question'],request_id='original-full-decision',depth='standard')
        result=self.service.execute(self.owner,run['id']);current=self.repo.fetch_run(self.owner,run['id'])
        self.assertEqual((current['status'],current['calls'],current['call_limit'],current['repair_used']),('succeeded',3,6,True))
        self.assertEqual(self.model.calls,['intake','synthesis','repair'])
        self.assertEqual(self.service.validation_attempts,[[GUARANTEE],[]])
        self.assertIn(GUARANTEE,self.service._validate(self.owner,current,self.model.bind(deepcopy(self.evidence['outputs']['synthesis']))))
        self.assertEqual(self.service._validate(self.owner,current,self.model.bind(deepcopy(self.evidence['outputs']['repair']))),[])
        for key in self.evidence['outputs']['repair']:
            if key!='professional_appendix':self.assertEqual(result[key],self.model.outputs['repair'][key])
        self.assertEqual(result['cited_fact_ids'],[self.receipt['fact_id']]);self.assertEqual(result['cited_claim_ids'],[])
        self.assertEqual(result['memory_receipts'],[]);self.assertEqual(len(self.service.memory.facts(self.owner)),1)
        calculation=self.service._record(self.owner,run['id'],'calculation')
        self.assertTrue(self.service.knowledge.revalidate_claims(calculation['calculation'],calculation['claims'])['eligible'])
        self.assertEqual(calculation['claims'],[]);self.assertTrue(result['validation']['valid'])
        self.assertEqual(current['dependencies']['fact:'+self.receipt['fact_id']],self.receipt['revision'])
        replay=self.service.submit(owner=self.owner,message=self.evidence['question'],request_id='original-full-decision',depth='standard')
        self.assertEqual(replay['id'],run['id']);self.assertEqual(self.service.execute(self.owner,replay['id']),result)
        self.assertEqual(len(self.model.calls),3);self.assertEqual(self.repo.fetch_run(self.owner,run['id'])['calls'],3)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),before)

    def test_finite_do_or_make_postposed_inference_denials_commit_without_repair(self):
        passages=('未做任何零风险推断。','未做零风险或完全可逆推断。',
                  '未做任何零风险、完全可逆或无损失推断。','未做任何“零风险、完全可逆或无损失”推断。',
                  '未做零风险或可逆性推断。','未做任何无损失推断。','未作任何零风险推断。')
        for index,passage in enumerate(passages):
            with self.subTest(passage=passage):
                run,result=self.local(passage,'finite-postposed-'+str(index));current=self.repo.fetch_run(self.owner,run['id'])
                self.assertEqual((current['status'],current['calls'],current['repair_used']),('succeeded',2,False))
                self.assertEqual(result['memory_receipts'],[]);self.assertTrue(result['validation']['valid'])
                self.assertEqual(len(self.service.memory.facts(self.owner)),1)

    def test_double_denial_object_cross_sentence_or_new_positive_guarantee_stays_rejected(self):
        passages=('零风险或完全可逆。','没有未做零风险推断。','未曾未做任何零风险推断。',
                  '未未做零风险推断。','不是“未做零风险或完全可逆推断”。','没有“未做任何无损失推断”。',
                  '未做A零风险推断。','未做任何A零风险推断。','未做零风险或B完全可逆推断。',
                  '未做零风险报价推断。','未做零风险推断依据。','未做零风险。',
                  '未做任何说明，但报名无损失。','未做零风险推断。但报名完全可逆。',
                  '未做零风险推断，报名无损失。','未做任何零风险或可逆性推断，但是B完全可逆。',
                  '未做任何零风险推断并确认付款无损失。','没有未作任何零风险推断。',
                  '未做零风险推断”不是事实。','未做任何零风险推断。资料已长期保存。')
        for index,passage in enumerate(passages):
            with self.subTest(passage=passage):
                operation='unsafe-postposed-'+str(index)
                with self.assertRaises(InvalidAnswer):self.local(passage,operation)
                current=self.run_for(operation)
                self.assertEqual((current['status'],current['calls'],current['repair_used']),('failed',3,True))
                self.assertIsNone(current['result']);self.assertTrue(self.service.validation_attempts[-1])

    def test_saved_negative_source_never_supplies_positive_guarantee_permission(self):
        literal='未做任何零风险、完全可逆或无损失推断'
        source=self.service.memory.receive(self.owner,content='请记住：'+literal,source_id='negative-inference-original')
        receipt=self.service.memory.save_fact(self.owner,'self',source['id'],literal,'background',operation_id='negative-inference-save')
        self.assertEqual(receipt['write_status'],'saved')
        with self.assertRaises(InvalidAnswer):self.local('付款零风险、完全可逆且无损失。','negative-source-is-not-positive-support')
        self.assertIn(GUARANTEE,self.service.validation_attempts[-1])

    def test_observed_single_tarot_tight_denials_pass_without_guarantee_or_save(self):
        passages=('不能假设中途退出无损失。','不预设"完全可逆"或"无损失"。','未承诺完全可逆或无损失。')
        for index,passage in enumerate(passages):
            with self.subTest(passage=passage):
                run,result=self.local(passage,'single-tarot-denial-'+str(index));current=self.repo.fetch_run(self.owner,run['id'])
                self.assertEqual((current['status'],current['calls'],current['repair_used']),('succeeded',2,False))
                self.assertEqual(result['memory_receipts'],[]);self.assertTrue(result['validation']['valid'])
                self.assertEqual(len(self.service.memory.facts(self.owner)),1)

    def test_observed_single_tarot_denials_never_allow_positive_double_object_or_cross_field(self):
        passages=('中途退出无损失。','预设完全可逆或无损失。','承诺完全可逆或无损失。',
                  '不是不能假设中途退出无损失。','不是“不预设完全可逆或无损失”。','没有未承诺完全可逆。',
                  '未曾未承诺无损失。','不是“未承诺完全可逆或无损失”。','没有“未承诺无损失”。',
                  '不能假设A中途退出无损失。','不能假设中途退出A无损失。','不预设A无损失或B完全可逆。',
                  '未承诺A无损失或B完全可逆。','不能假设中途退出。但是报名无损失。',
                  '不预设完全可逆或无损失。但付款零风险。','未承诺完全可逆，但报名无损失。',
                  '不预设完全可逆或无损失，却认为中途退出无损失。',
                  '未承诺完全可逆。核实阶段完全可逆（尚未付款）。')
        for index,passage in enumerate(passages):
            with self.subTest(passage=passage):
                operation='single-tarot-denial-unsafe-'+str(index)
                with self.assertRaises(InvalidAnswer):self.local(passage,operation)
                current=self.run_for(operation)
                self.assertEqual((current['status'],current['calls'],current['repair_used']),('failed',3,True))
                self.assertIsNone(current['result']);self.assertIn(GUARANTEE,self.service.validation_attempts[-1])
        for index,passage in enumerate(('不能假设中途退出无损失。','不预设完全可逆或无损失。','未承诺完全可逆或无损失。')):
            with self.subTest(cross_field=passage):
                with self.assertRaises(InvalidAnswer):self.local(passage,'single-tarot-cross-field-'+str(index),unsafe_appendix='但付款完全可逆。')
                self.assertIn(GUARANTEE,self.service.validation_attempts[-1])

    def test_saved_single_tarot_negative_or_hypothesis_source_is_not_positive_guarantee_support(self):
        for index,literal in enumerate(('不能假设中途退出无损失','不预设完全可逆或无损失','未承诺完全可逆或无损失')):
            with self.subTest(literal=literal):
                kind='hypothesis' if '假设' in literal else 'background'
                content=('请保存以下资料：“'+literal+'”。') if kind=='hypothesis' else '请记住：'+literal
                source=self.service.memory.receive(self.owner,content=content,source_id='negative-tarot-denial-'+str(index))
                authorization_id=None
                if kind=='hypothesis':
                    # The user directive is outside the quoted hypothesis;
                    # a real consent record covers the full original span.
                    consent=self.service.memory.grant_authorization(self.owner,'self',source['id'],content,
                        kinds=['hypothesis'],operation_id='negative-tarot-denial-consent-'+str(index))
                    authorization_id=consent['id']
                receipt=self.service.memory.save_fact(self.owner,'self',source['id'],literal,kind,
                    authorization_id=authorization_id,operation_id='negative-tarot-denial-save-'+str(index))
                self.assertEqual(receipt['write_status'],'saved');self.assertEqual(receipt['kind'],kind)
                with self.assertRaises(InvalidAnswer):self.local('付款完全可逆，中途退出无损失。','negative-tarot-source-'+str(index))
                self.assertIn(GUARANTEE,self.service.validation_attempts[-1])


if __name__=='__main__':unittest.main()
