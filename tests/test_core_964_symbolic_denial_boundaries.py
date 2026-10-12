"""Finite real-provider clauses through actual PG, Tarot, charts and runtime.

Only the model is a fixture. This does not replay opaque old run identities.
"""
from copy import deepcopy
import unittest
import uuid
from psycopg import sql

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import InvalidAnswer
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_memory import test_dsn
from tests.test_core_pg_channels import FixtureModel

SYMBOLIC='象征解释被提升为现实确定性或概率'
SAVE='保存或删除提示必须由实际程序回执生成'
SAFE=(
    '牌面只是反思框架，不构成对学习效果的任何保证。',
    '牌面不构成对学习效果、成绩或他人动机的保证。',
)
RUN_EVIDENCE=[]


class SymbolicClauseModel(FixtureModel):
    def __init__(self,clause,*,extra=None,unknown=False,deep=False,repair=None):
        super().__init__();self.clause=clause;self.extra=extra or {};self.unknown=unknown
        self.deep=deep;self.repair=repair
    def generate(self,**kwargs):
        response=super().generate(**kwargs);output=response['output'];purpose=kwargs['purpose']
        if purpose=='intake':
            output['plan'].update(mode='tarot',topic='study',decision=False,
                systems=['tarot','bazi','ziwei','astro'] if self.deep else ['tarot'],
                time_scale='natal' if self.deep else 'daily',target_date='2026-10-11')
        elif not purpose.startswith('specialist:'):
            output['plain_summary']=self.repair if purpose=='repair' and self.repair is not None else self.clause
            output.update(deepcopy(self.extra))
            if self.unknown:output['cited_fact_ids'].append('unknown_not_in_actual_snapshot')
        return response


class SymbolicDenialBoundariesPG(unittest.TestCase):
    def setUp(self):
        self.repo=PostgresRepository(test_dsn(),schema='test_964_symbolic_'+uuid.uuid4().hex[:16])
        self.owner='synthetic-symbolic-limit';self.repo.ensure_owner(self.owner)
        self.service=ConsultationService(self.repo,model=SymbolicClauseModel(SAFE[0]))
        self.case=self.service.memory.create_case(self.owner,'self','合成学习反思')['id']
        for i,(kind,text) in enumerate((('constraint','我不能上夜班'),('preference','我喜欢先核实学习时间'))):
            source=self.service.memory.receive(self.owner,content=text,source_id='known-'+str(i),case_ids=[self.case])
            self.assertEqual(self.service.memory.save_fact(self.owner,'self',source['id'],text,kind,case_id=self.case)['write_status'],'saved')
        cards=[{'card_id':'major-00','orientation':'upright'},{'card_id':'cups-01','orientation':'reversed'},
               {'card_id':'pentacles-08','orientation':'upright'}]
        draw=self.service.tarot.create_draw(self.owner,subject_id='self',case_id=self.case,question='如何核对学习安排？',
            spread_id='reflect3',draw_source='manual',manual_cards=cards,idempotency_key='fixed-draw')['draw']
        self.draw=self.service.tarot.reveal(self.owner,draw['id']);self.fixed_cards=deepcopy(self.draw['cards'])
    def tearDown(self):
        with self.repo.connection() as c:runs=c.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for run in runs:
            for epoch in range(run['retry_epoch']+1):self.service.runtime.purge(run['id'],epoch)
        with self.repo.connection() as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.repo.schema)))
        self.repo.close()
    def execute_clause(self,clause,*,issue=None,extra=None,unknown=False,deep=False,repair=None):
        self.model=SymbolicClauseModel(clause,extra=extra,unknown=unknown,deep=deep,repair=repair)
        self.service.model=self.model
        run=self.service.submit(owner=self.owner,message='请用这次固定塔罗反思学习安排，班次和费用仍待核实。',
            request_id='symbolic-'+uuid.uuid4().hex,case_ids=[self.case],draw_id=self.draw['id'],
            depth='deep' if deep else 'standard',
            selection={'date':'2026-10-11','systems':['tarot','bazi','ziwei','astro'] if deep else ['tarot']})
        result=None
        try:
            if issue:
                with self.assertRaises(InvalidAnswer) as caught:self.service.execute(self.owner,run['id'])
                self.assertEqual(caught.exception.code,'REFERENCE_ERROR')
                self.assertIn(issue,self.model.requests[-1]['payload']['errors'])
            else:
                result=self.service.execute(self.owner,run['id']);self.assertTrue(result['validation']['valid'])
            saved=self.repo.fetch_run(self.owner,run['id'])
            self.assertEqual(saved['status'],'failed' if issue else 'succeeded')
            self.assertEqual(saved['calls'],8 if deep else 4 if issue or repair is not None else 3)
            self.assertEqual(saved['call_limit'],10 if deep else 6)
            self.assertEqual(saved['repair_used'],bool(issue or repair is not None))
            if issue:self.assertIsNone(saved['result'])
            self.assertEqual(self.service.tarot.get_for_reading(self.owner,self.draw['id'])['cards'],self.fixed_cards)
            return result,saved
        finally:
            saved=self.repo.fetch_run(self.owner,run['id'])
            RUN_EVIDENCE.append({'status':saved['status'],'calls':saved['calls'],'limit':saved['call_limit'],
                'repair_used':saved['repair_used'],'purposes':[r['purpose'] for r in self.model.requests],
                'fixed_draw_unchanged':self.service.tarot.get_for_reading(self.owner,self.draw['id'])['cards']==self.fixed_cards})
    def test_two_actual_clauses_and_cannot_variants_commit_without_repair(self):
        for clause in SAFE+tuple(s.replace('不构成','不能构成') for s in SAFE):
            with self.subTest(clause=clause):self.execute_clause(clause)
    def test_each_clause_keeps_double_denial_quotes_objects_contrasts_and_sentence_boundaries(self):
        for clause in SAFE:
            mutations=(
                clause.replace('不构成','不是不构成'),
                '不是“'+clause+'”',
                '“'+clause+'”',
                clause.replace('不构成','“不构成').replace('保证。','保证”。'),
                clause+'但牌面保证学习成功。',
                clause.rstrip('。')+'，但保证你学习成功。',
                clause.replace('学习效果','投资收益'),
                clause.replace('学习效果','学习效果及任意内容'),
                '牌面不构成对学习效果。牌面保证学习成功。',
            )
            for mutation in mutations:
                with self.subTest(mutation=mutation):self.execute_clause(mutation,issue=SYMBOLIC)
    def test_different_field_denial_cannot_launder_a_positive(self):
        for clause in SAFE:
            with self.subTest(clause=clause):
                self.execute_clause(clause,issue=SYMBOLIC,extra={'explanation':'牌面保证学习成功。'})
    def test_original_false_save_stays_rejected_with_only_save_issue(self):
        _,saved=self.execute_clause(SAFE[0],issue=SAVE,extra={'professional_appendix':'同一轮已保存问题与牌阵，逐牌仅作反思。'})
        self.assertEqual(self.model.requests[-1]['payload']['errors'],[SAVE])
        initial=self.service._record(self.owner,saved['id'],'synthesis')
        self.assertEqual(self.service._validate(self.owner,saved,initial),[SAVE])
        self.assertEqual(len(self.service.memory.facts(self.owner)),2)
    def test_unknown_reference_stays_rejected_for_each_safe_clause(self):
        for clause in SAFE:
            with self.subTest(clause=clause):self.execute_clause(clause,issue='引用了本轮有效范围之外的事实',unknown=True)
    def test_actual_native_specialists_one_global_repair_preserve_draw_and_budget(self):
        profile=[('gender','女'),('birth.solar_datetime','2000-01-01 08:00'),('birth.location.lng',116.4),
            ('birth.location.lat',39.9),('birth.timezone_offset',8),('birth.time_unknown',False),('birth.precision','exact')]
        for i,(field,value) in enumerate(profile):
            text='请保存 '+field+'='+str(value)
            source=self.service.memory.receive(self.owner,content=text,source_id='profile-'+str(i))
            self.assertEqual(self.service.memory.save_fact(self.owner,'self',source['id'],text,'profile',field=field,value=value)['write_status'],'saved')
        result,saved=self.execute_clause('牌面保证学习成功。',deep=True,repair=SAFE[1])
        self.assertEqual([r['purpose'] for r in self.model.requests],
            ['intake','specialist:tarot','specialist:bazi','specialist:ziwei','specialist:astro','synthesis','review','repair'])
        self.assertIn(SYMBOLIC,self.model.requests[-1]['payload']['errors'])
        calculation=self.service._record(self.owner,saved['id'],'calculation')
        self.assertEqual(calculation['calculation']['errors'],[])
        self.assertEqual({claim['system'] for claim in calculation['claims']},{'tarot','bazi','ziwei','astro'})
        self.assertEqual(len(self.service.memory.facts(self.owner)),9)


if __name__=='__main__':unittest.main()
