"""Real PG/service/LangGraph guard regressions; only model outputs replaced."""
from copy import deepcopy
from pathlib import Path
import unittest
import uuid
from psycopg import sql

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import InvalidAnswer
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_memory import test_dsn
from tests.test_core_pg_channels import FixtureModel

SAFE = [
 '两方的退出条件、违约金、退款规则均待核实，不能假定退出无损失',
 '但两方的退出条件、退款规则均待核实，不能假定任何后续步骤完全可逆或无损失',
 '即使在签约付款前，退出是否零损失也取决于尚未确认的具体条款',
 '待核实前不能按零成本、无损失或可退出处理',
 '核实与等待有真实的时间与机会成本（确认时限、报名窗口），任何阶段都不能称为完全可逆或无损失',
 '条款书面确认前不能视为可退出或无损失',
 '不支付不可退费用、不作承诺可保留主要选择空间，但等待消耗的时间、报名窗口与确认时限不可收回，故非完全可逆、非无损失',
 '不能按“完全可逆或无损失”处理',
 '不应按零成本退出或完全可逆处理',
 '不能称为“完全可逆或无损失”',
 '不是完全可逆，也不是无损失',
 '故非无损失',
 '不能保证退出无损失',
 '不能按零成本退出处理',
 '本轮不把“零成本”当作已经核实的现实费用',
]
UNSAFE = [
 '在任一方未付款、未签约之前，选择本身完全可逆',
 '核实动作本身完全可逆',
 '在截止时点前完全可逆，不支付不可退费用、不作承诺即可保持灵活性',
 'B可以零成本退出',
 '“零成本退出”',
 '“完全可逆”',
 '不是非完全可逆',
 '并非非无损失',
 '非非无损失',
 '不是“不能称为完全可逆”',
 '并非“不能按无损失处理”',
 '不是不能假定任何后续步骤完全可逆',
 '除非完全可逆，否则立即签约',
 '不能按零成本处理，但B可以零成本退出',
 '不能按零成本退出处理，实际可以零成本退出',
 '不能称为A完全可逆，但B完全可逆',
 '不能视为可退出或无损失，但报名无损失',
 '故非完全可逆，报名完全可逆',
 '不能假定退出无损失。B无损失',
 '退出是否零损失也取决于尚未确认的具体条款，但报名无损失',
 '不能按任意内容无损失处理',
]


class ClauseProvider(FixtureModel):
    def __init__(self):
        super().__init__();self.clause='';self.field='explanation';self.deep=False
        self.repair_clause=None;self.extra_fields={};self.unknown_cite=False
    def generate(self,**kwargs):
        response=super().generate(**kwargs);output=response['output'];purpose=kwargs['purpose']
        if purpose=='intake':
            output['plan'].update(mode='decision',decision=True,topic='career',time_scale='natal',
                                  systems=['tarot','bazi','ziwei','astro'] if self.deep else [],target_date='2026-10-11')
        elif not purpose.startswith('specialist:'):
            output['decision_options']=[{'option':name,'benefit':'仅在核实后纳入比较','cost':'费用和时间待核实',
                'risk':'条件未知','reversibility':'可停止核实，已经投入的时间不能收回','first_step':'索取书面条款'} for name in ('核实A','核实B')]
            clause=self.repair_clause if purpose=='repair' and self.repair_clause is not None else self.clause
            if self.field=='caveats':output['caveats']=[clause]
            elif self.field=='reversibility':output['decision_options'][0]['reversibility']=clause
            else:output[self.field]=clause
            output.update(deepcopy(self.extra_fields))
            if self.unknown_cite:output['cited_fact_ids'].append('fact_not_in_scope')
        return response


class DenialBoundariesPG(unittest.TestCase):
    def setUp(self):
        self.repo=PostgresRepository(test_dsn(),schema='test_2bc_denial_'+uuid.uuid4().hex[:16])
        self.model=ClauseProvider();self.service=ConsultationService(self.repo,model=self.model)
        self.owner='synthetic-clause';self.repo.ensure_owner(self.owner)
        self.case=self.service.memory.create_case(self.owner,'self','合成现实比较')['id']
        for i,(kind,text) in enumerate((('constraint','我不能上夜班'),('preference','我喜欢先核实班次、费用和退出条件'))):
            source=self.service.memory.receive(self.owner,content=text,source_id='known-'+str(i),case_ids=[self.case])
            saved=self.service.memory.save_fact(self.owner,'self',source['id'],text,kind,case_id=self.case)
            self.assertEqual(saved['write_status'],'saved')
    def tearDown(self):
        with self.repo.connection() as c:runs=c.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for run in runs:
            for epoch in range(run['retry_epoch']+1):self.service.runtime.purge(run['id'],epoch)
        with self.repo.connection() as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.repo.schema)))
        self.repo.close()
    def submit(self,depth='standard',draw_id=None):
        return self.service.submit(owner=self.owner,message='请比较合成A与B，费用和退出条件仍待核实，我不能上夜班。',
             request_id='clause-'+uuid.uuid4().hex,case_ids=[self.case],depth=depth,draw_id=draw_id,
             selection={'date':'2026-10-11','systems':['tarot','bazi','ziwei','astro'] if self.model.deep else []})
    def assert_safe(self,clause,field='explanation'):
        self.model.clause=clause;self.model.field=field;run=self.submit()
        result=self.service.execute(self.owner,run['id']);saved=self.repo.fetch_run(self.owner,run['id'])
        self.assertTrue(result['validation']['valid']);self.assertEqual(saved['calls'],2)
        self.assertFalse(saved['repair_used']);self.assertEqual(saved['status'],'succeeded')
        self.assertEqual(len(self.service.memory.facts(self.owner)),2)
    def assert_rejected(self,clause,field='explanation'):
        self.model.clause=clause;self.model.field=field;run=self.submit()
        with self.assertRaises(InvalidAnswer) as caught:self.service.execute(self.owner,run['id'])
        self.assertEqual(caught.exception.code,'REFERENCE_ERROR')
        self.assertEqual(self.model.requests[-1]['purpose'],'repair')
        self.assertTrue(any('费用、退出和风险条件' in error for error in self.model.requests[-1]['payload']['errors']))
        saved=self.repo.fetch_run(self.owner,run['id']);self.assertEqual(saved['calls'],3)
        self.assertTrue(saved['repair_used']);self.assertEqual(saved['status'],'failed')
        self.assertIsNone(saved['result']);self.assertEqual(len(self.service.memory.facts(self.owner)),2)
    def test_exact_fifteen_safe_clauses_use_actual_service_no_repair(self):
        for i,clause in enumerate(SAFE):
            with self.subTest(index=i):self.assert_safe(clause)
    def test_unsafe_originals_and_twentyone_mutations_still_fail(self):
        for i,clause in enumerate(UNSAFE):
            with self.subTest(index=i):self.assert_rejected(clause)
    def test_disclaimer_in_other_field_does_not_launder_positive(self):
        self.model.extra_fields={'caveats':['不能称为完全可逆或无损失']}
        self.assert_rejected('报名无损失')
        self.model.extra_fields={'explanation':'不能按完全可逆或无损失处理'}
        self.assert_rejected('B可以零成本退出',field='reversibility')
    def test_safe_grammar_does_not_bypass_unknown_fact_citation(self):
        self.model.unknown_cite=True;self.model.clause=SAFE[3];run=self.submit()
        with self.assertRaises(InvalidAnswer) as caught:self.service.execute(self.owner,run['id'])
        self.assertEqual(caught.exception.code,'REFERENCE_ERROR')
        self.assertTrue(any('本轮有效范围之外' in error for error in self.model.requests[-1]['payload']['errors']))
        self.assertEqual(self.repo.fetch_run(self.owner,run['id'])['calls'],3)
    def test_actual_four_specialists_review_and_one_repair_keep_draw_and_cap(self):
        profile=[('gender','女'),('birth.solar_datetime','2000-01-01 08:00'),('birth.location.lng',116.4),
            ('birth.location.lat',39.9),('birth.timezone_offset',8),('birth.time_unknown',False),('birth.precision','exact')]
        for i,(field,value) in enumerate(profile):
            text='请保存 '+field+'='+str(value)
            source=self.service.memory.receive(self.owner,content=text,source_id='profile-'+str(i))
            result=self.service.memory.save_fact(self.owner,'self',source['id'],text,'profile',field=field,value=value)
            self.assertEqual(result['write_status'],'saved')
        cards=[{'card_id':'major-00','orientation':'upright'},{'card_id':'cups-01','orientation':'reversed'},
               {'card_id':'pentacles-08','orientation':'upright'}]
        draw=self.service.tarot.create_draw(self.owner,subject_id='self',case_id=self.case,question='合成安排',
            spread_id='reflect3',draw_source='manual',manual_cards=cards,idempotency_key='draw-fixed')['draw']
        draw=self.service.tarot.reveal(self.owner,draw['id']);before=deepcopy(draw['cards'])
        self.model.deep=True;self.model.clause=UNSAFE[1];self.model.repair_clause=SAFE[3]+'。'+SAFE[4]+'。'+SAFE[5]+'。'+SAFE[6]
        run=self.submit(depth='deep',draw_id=draw['id']);result=self.service.execute(self.owner,run['id'])
        saved=self.repo.fetch_run(self.owner,run['id']);self.assertEqual(saved['calls'],8);self.assertEqual(saved['call_limit'],10)
        self.assertTrue(saved['repair_used']);self.assertTrue(result['validation']['valid'])
        purposes=[request['purpose'] for request in self.model.requests]
        self.assertEqual(purposes,['intake','specialist:tarot','specialist:bazi','specialist:ziwei','specialist:astro','synthesis','review','repair'])
        self.assertEqual(self.service.tarot.get_for_reading(self.owner,draw['id'])['cards'],before)
        self.assertEqual(len(self.service.memory.facts(self.owner)),9)


if __name__=='__main__':unittest.main()
