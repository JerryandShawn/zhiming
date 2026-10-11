"""Ported user-visible v6 behavior through the actual Core service and PostgreSQL."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import hashlib
import os
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient
from mingjing_core.adapters.web import create_app
from mingjing_core.adapters.tarot import TarotService
from mingjing_core.domain.contracts import ScopeError
from mingjing_core.domain.consultation import FinalAnswer
import unittest

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict
from tests import test_core_runtime as runtime_helpers


class CompatibilityProvider(runtime_helpers.ProgrammableProvider):
    def __init__(self):
        super().__init__();self.final_patch={};self.plan_patch={};self.first_call_gate=None;self.repair_patch=None;self.retire_ids=[]
    def generate(self,**kwargs):
        response=super().generate(**kwargs)
        if kwargs['purpose']=='intake':
            response['output']['plan'].update(deepcopy(self.plan_patch));response['output']['retire_fact_ids']=list(self.retire_ids)
            if self.first_call_gate:
                entered,release=self.first_call_gate;self.first_call_gate=None;entered.set();release.wait(10)
        if kwargs['purpose'] in ('synthesis','repair'):
            response['output'].update(deepcopy(self.final_patch))
            if kwargs['purpose']=='repair' and self.repair_patch is not None:response['output'].update(deepcopy(self.repair_patch))
        return response


class CoreCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):runtime_helpers.CoreRuntimeTests.setUpClass.__func__(cls)
    setUp=runtime_helpers.CoreRuntimeTests.setUp
    tearDown=runtime_helpers.CoreRuntimeTests.tearDown
    consult=runtime_helpers.CoreRuntimeTests.consult
    run_by_request=runtime_helpers.CoreRuntimeTests.run_by_request

    def configure_provider(self):
        self.provider=CompatibilityProvider();self.service=ConsultationService(self.repo,model=self.provider)

    def save(self,text,*,kind='constraint',case_id=None):
        source=self.service.memory.receive('alice',content=text,source_id='fixture-'+str(len(self.repo.list('alice','message'))),case_ids=[case_id] if case_id else [])
        return self.service.memory.save_fact('alice','self',source['id'],text,kind,case_id=case_id)

    def test_real_service_concurrent_same_request_has_one_provider_execution(self):
        self.configure_provider();entered=threading.Event();release=threading.Event()
        self.provider.first_call_gate=(entered,release)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(self.consult,request_id='same-operation')
            self.assertTrue(entered.wait(10))
            try:
                with self.assertRaises(LeaseConflict):self.consult(request_id='same-operation')
            finally:release.set()
            result=first.result(timeout=20)
        self.assertEqual(len(self.provider.requests),2)
        self.assertEqual(self.consult(request_id='same-operation'),result)

    def test_saved_receipt_cannot_be_replaced_by_model_acknowledgement(self):
        self.configure_provider();self.provider.final_patch={'plain_summary':'我已经记住了。'}
        with self.assertRaises(Exception):self.consult(request_id='invented-save',depth='standard')
        self.assertNotEqual(self.run_by_request('invented-save')['status'],'succeeded')
        self.assertEqual(self.service.memory.facts('alice'),[])

    def test_plain_refusal_and_support_do_not_force_three_calculators(self):
        self.configure_provider();self.provider.plan_patch={'systems':['bazi','ziwei','astro']}
        result=self.consult(message='不用排盘，我只是想聊聊今天的学习。')
        self.assertEqual(result['meta']['plan']['systems'],[])
        self.assertEqual([r['purpose'] for r in self.provider.requests],['intake','synthesis'])
        self.provider.requests=[];self.provider.plan_patch={'mode':'support','systems':['bazi','ziwei','astro']}
        result=self.consult(message='我现在很累，想要一点低负担的支持。')
        self.assertEqual(result['meta']['plan']['systems'],[])

    def test_decision_requires_real_tradeoffs_and_a_reversible_first_step(self):
        self.configure_provider();self.provider.plan_patch={'mode':'decision','decision':True}
        self.provider.final_patch={'decision_options':[],'actions':[]}
        with self.assertRaises(Exception):self.consult(request_id='missing-tradeoff',depth='standard')
        self.assertNotEqual(self.run_by_request('missing-tradeoff')['status'],'succeeded')

    def test_hard_night_shift_constraint_cannot_be_relaxed_in_plain_summary(self):
        self.configure_provider();self.save('我不能上夜班')
        self.provider.final_patch={'plain_summary':'虽然你不能上夜班，可以每月破例上一次夜班。'}
        with self.assertRaises(Exception):self.consult(message='选择学习时间时请考虑我的硬限制。',request_id='night-exception',depth='standard')
        self.assertNotEqual(self.run_by_request('night-exception')['status'],'succeeded')

    def test_unrelated_monthly_meeting_cap_cannot_authorize_night_shift(self):
        self.configure_provider();self.save('我不能上夜班');self.save('我每月最多参加两次会议')
        self.provider.final_patch={'plain_summary':'每月最多两次会议，因此你每月可以上两次夜班。'}
        with self.assertRaises(Exception):self.consult(request_id='unrelated-cap',depth='standard')
        self.assertNotEqual(self.run_by_request('unrelated-cap')['status'],'succeeded')

    @staticmethod
    def option(benefit):
        return {'option':'岗位A','benefit':benefit,'cost':'需核实实际费用','risk':'信息尚未齐全',
                'reversibility':'先试做可撤回','first_step':'向负责人核对要求'}

    @classmethod
    def options(cls,benefit):
        second=cls.option('暂缓选择，核实信息后再比较。');second['option']='暂缓核实'
        return [cls.option(benefit),second]

    def test_unknown_job_familiarity_cannot_be_invented(self):
        self.configure_provider();self.provider.plan_patch={'mode':'decision','decision':True}
        self.provider.final_patch={'decision_options':self.options('你熟悉岗位A的日常任务，所以值得优先选。')}
        with self.assertRaises(Exception):self.consult(request_id='unsupported-familiarity',depth='standard')
        self.assertNotEqual(self.run_by_request('unsupported-familiarity')['status'],'succeeded')

    def test_unknown_familiarity_and_negotiation_cost_cannot_be_invented(self):
        self.configure_provider();self.provider.plan_patch={'mode':'decision','decision':True}
        self.provider.final_patch={'decision_options':self.options('你熟悉岗位A，而且协商成本低，所以值得优先选。')}
        with self.assertRaises(Exception):self.consult(request_id='invented-recommendation',depth='standard')
        self.assertNotEqual(self.run_by_request('invented-recommendation')['status'],'succeeded')

    def test_known_familiarity_does_not_authorize_unknown_negotiation_cost(self):
        self.configure_provider();self.save('请记住：我熟悉岗位A的日常任务',kind='background')
        self.provider.plan_patch={'mode':'decision','decision':True}
        self.provider.final_patch={'decision_options':self.options('你熟悉岗位A，协商成本低，所以值得优先选。')}
        with self.assertRaises(Exception):self.consult(request_id='unsupported-cost',depth='standard')
        self.assertNotEqual(self.run_by_request('unsupported-cost')['status'],'succeeded')

    def test_explicit_unknown_cost_is_accepted_without_fabricating_preference(self):
        self.configure_provider();self.provider.plan_patch={'mode':'decision','decision':True}
        self.provider.final_patch={'decision_options':self.options('成本与熟悉程度未知，待核实后比较。')}
        result=self.consult(request_id='honest-unknown',depth='standard')
        self.assertEqual(result['validation']['status'],'validated')
        self.assertEqual(self.service.memory.facts('alice'),[])

    def test_long_preloaded_history_does_not_displace_saved_constraint_after_restart(self):
        self.configure_provider();critical=self.save('我不能上夜班')
        for index in range(300):
            self.service.memory.receive('alice',content='合成日常闲聊'+str(index),source_id='history-'+str(index),channel='synthetic')
        self.service=ConsultationService(self.repo,model=self.provider)
        result=self.consult(message='现在需要安排学习时间，请沿用我的实际限制。',request_id='after-300-history')
        facts=self.provider.requests[-1]['payload']['reference_data']['facts']
        self.assertIn(critical['id'],{f['id'] for f in facts})
        self.assertIn(critical['id'],result['cited_fact_ids'])

    def test_negated_decision_is_not_written_as_action_or_feedback(self):
        self.configure_provider()
        self.consult(message='我还没决定选岗位A，也没有执行。',request_id='negated-choice')
        self.assertEqual(self.repo.list('alice','feedback'),[])
        self.assertEqual(self.repo.list('alice','episode'),[])

    def test_corrections_do_not_promote_separate_new_sensitive_information(self):
        self.configure_provider();old=self.save('我喜欢上午学习',kind='preference')
        self.provider.proposal={'quote':'更正：我现在喜欢下午学习','category':'更正','supersedes':old['id']}
        result=self.consult(message='更正：我现在喜欢下午学习。我家人的出生日期只是随口提到。',request_id='scoped-correction')
        self.assertTrue(any(r.get('write_status')=='saved' for r in result['memory_receipts']))
        facts=self.service.memory.facts('alice')
        self.assertEqual(len(facts),1);self.assertIn('下午',facts[0]['content'])
        self.assertNotIn('家人',json.dumps(facts,ensure_ascii=False))


    def test_normal_contract_neither_invents_answer_nor_shares_mutable_defaults(self):
        first=FinalAnswer(plain_summary='你好',actions=[],decision_options=[],cited_fact_ids=[],cited_claim_ids=[]);second=FinalAnswer(plain_summary='你好',actions=[],decision_options=[],cited_fact_ids=[],cited_claim_ids=[])
        first.actions.append('合成动作');self.assertEqual(second.actions,[])
        self.configure_provider();self.provider.final_patch={'plain_summary':''}
        with self.assertRaises(Exception):self.consult(request_id='empty-final')
        self.assertNotEqual(self.run_by_request('empty-final')['status'],'succeeded')

    def test_support_keeps_one_optional_low_burden_action(self):
        self.configure_provider();self.provider.plan_patch={'mode':'support','systems':['astro','bazi','ziwei']}
        self.provider.final_patch={'actions':['如果愿意，先休息一会儿。']}
        result=self.consult(request_id='one-support-action')
        self.assertEqual(result['actions'],['如果愿意，先休息一会儿。'])
        self.assertFalse(result['meta']['plan']['systems']);self.assertFalse(result['decision_options'])
        self.provider.final_patch={'actions':['先休息','再完成任务','再制订计划']}
        with self.assertRaises(Exception):self.consult(request_id='overloaded-support',depth='standard')

    def test_supported_cost_and_familiarity_keep_actual_fact_citation(self):
        self.configure_provider();fact=self.save('请记住：我对现有关系和流程都已熟悉，协商成本低',kind='background')
        self.provider.plan_patch={'mode':'decision','decision':True}
        self.provider.final_patch={'decision_options':self.options('现有关系和流程都已熟悉，协商成本低，可用于比较。')}
        result=self.consult(request_id='known-cost-and-familiarity')
        self.assertIn(fact['id'],result['cited_fact_ids'])
        self.assertEqual(self.service.memory.facts('alice')[0]['source_refs'],fact['source_refs'])

    def test_expired_memory_cannot_reenter_current_service_context(self):
        self.configure_provider();source=self.service.memory.receive('alice',content='我喜欢合成过期偏好',source_id='expired-source')
        expired=self.service.memory.save_fact('alice','self',source['id'],source['content'],valid_to=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat())
        result=self.consult(request_id='expired-context')
        self.assertNotIn(expired['id'],result['cited_fact_ids'])
        self.assertFalse(any(f['id']==expired['id'] for f in self.provider.requests[-1]['payload']['reference_data']['facts']))

    def test_auto_memory_disable_requires_scoped_explicit_permission(self):
        self.configure_provider();self.service.memory.update_settings('alice',{'auto_save_low_sensitivity':False},expected_revision=self.repo.get_revision('alice'))
        self.provider.proposal={'quote':'我喜欢合成静音学习','category':'偏好'}
        first=self.consult(message='我喜欢合成静音学习',request_id='disabled-auto')
        self.assertFalse(any(r.get('write_status')=='saved' for r in first['memory_receipts']))
        self.provider.proposal={'quote':'请记住我喜欢合成静音学习','category':'偏好'}
        second=self.consult(message='请记住我喜欢合成静音学习',request_id='explicit-after-disabled')
        self.assertTrue(any(r.get('write_status')=='saved' for r in second['memory_receipts']))

    def test_explicit_profile_boolean_and_conflicts_are_not_last_write_wins(self):
        self.configure_provider();mem=self.service.memory
        for index,value in enumerate(('2000-01-01 08:00','2000-01-02 08:00')):
            text='请保存我的出生日期为'+value
            source=mem.receive('alice',content=text,source_id='profile-conflict-'+str(index))
            self.assertEqual(mem.save_fact('alice','self',source['id'],text,'profile',field='birth.solar_datetime',value=value)['write_status'],'saved')
        source=mem.receive('alice',content='请保存 birth.time_unknown=True',source_id='profile-bool')
        self.assertEqual(mem.save_fact('alice','self',source['id'],source['content'],'profile',field='birth.time_unknown',value=True)['write_status'],'saved')
        snap=mem.snapshot('alice');self.assertNotIn('birth.solar_datetime',snap['profile'])
        self.assertIn('birth.solar_datetime',snap['profile_conflicts']);self.assertIs(snap['profile']['birth.time_unknown'],True)
        self.assertNotIn('solar_datetime',self.service.authorized_archive('alice','self',snap).get('user',{}).get('birth',{}))

    def test_corrected_birth_is_used_in_authorized_calculation_archive(self):
        self.configure_provider();mem=self.service.memory
        source=mem.receive('alice',content='请保存我的出生日期为2000-01-01 08:00',source_id='birth-first')
        old=mem.save_fact('alice','self',source['id'],source['content'],'profile',field='birth.solar_datetime',value='2000-01-01 08:00')
        correction=mem.receive('alice',content='更正：出生日期应为2000-01-02 08:00',source_id='birth-correction')
        mem.correct_fact('alice',old['id'],correction['id'],correction['content'],expected_revision=old['revision'],field='birth.solar_datetime',value='2000-01-02 08:00')
        archive=self.service.authorized_archive('alice','self',mem.snapshot('alice'))
        self.assertEqual(archive['user']['birth']['solar_datetime'],'2000-01-02 08:00')
        self.assertNotIn(old['id'],{f['id'] for f in mem.facts('alice')})

    def test_explicit_multi_case_feedback_has_real_source_and_survives_restart(self):
        self.configure_provider();cases=[self.service.memory.create_case('alice','self',title,operation_id='case-'+str(i))['id'] for i,title in enumerate(('学习','工作'))]
        self.consult(message='同时讨论学习与工作安排',case_ids=cases,request_id='two-selected')
        with patch.dict(os.environ,{'MINGJING_TOKEN':'compat-synthetic','MINGJING_OWNER_ID':'alice','ZHIMING_TOKEN_OWNERS':'{}'}):
            with TestClient(create_app(self.service)) as client:
                response=client.post('/api/cases/'+cases[1]+'/events',headers={'X-Token':'compat-synthetic'},json={'request_id':'feedback-second','expected_revision':self.repo.get('alice','case',cases[1])['revision'],'kind':'completed','content':'我完成了工作安排'} )
                self.assertEqual(response.status_code,200,response.text)
        rows=self.repo.list('alice','feedback',case_ids=cases)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['case_id'],cases[1]);self.assertEqual(rows[0]['kind'],'completed')
        self.assertEqual(self.repo.get('alice','message',rows[0]['source_refs'][0]['message_id'])['content'],'我完成了工作安排')
        restarted=ConsultationService(self.repo,model=self.provider)
        self.assertEqual(restarted.repo.list('alice','feedback',case_ids=[cases[1]])[0]['id'],rows[0]['id'])

    def test_privacy_wrong_owner_or_schema_rolls_back_and_exports_no_body(self):
        self.configure_provider();fact=self.save('我喜欢SYNTHETIC_LEDGER_BODY_218')
        self.service.memory.retire_fact('alice',fact['id'],expected_revision=fact['revision'],scope='source')
        ledger=self.repo.export_privacy('alice');self.assertNotIn('SYNTHETIC_LEDGER_BODY_218',json.dumps(ledger))
        before=self.repo.get_revision('alice')
        for invalid in (dict(ledger,owner_user_id='bob'),dict(ledger,schema_version='unknown')):
            with self.assertRaises(ScopeError):self.repo.apply_privacy('alice',invalid)
            self.assertEqual(self.repo.get_revision('alice'),before)

    def test_original_tarot_assets_are_complete_unique_and_safe_svg(self):
        root=Path(__file__).resolve().parents[1]/'static/tarot';manifest=json.loads((root/'licenses.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['files']),79);hashes=set()
        for name in manifest['files']:
            data=(root/name).read_bytes();element=ET.fromstring(data)
            self.assertTrue(element.tag.endswith('svg'));self.assertEqual(element.attrib['viewBox'],'0 0 250 390')
            self.assertFalse(any(e.tag.endswith(('script','image','foreignObject')) for e in element.iter()))
            hashes.add(hashlib.sha256(data).hexdigest())
        self.assertEqual(len(hashes),79)

    def test_tarot_unbiased_shuffle_bounds_and_reversal_setting(self):
        self.configure_provider();case=self.service.memory.create_case('alice','self','合成抽牌')['id'];bounds=[]
        cards=TarotService(self.repo,randbelow=lambda n:(bounds.append(n) or 0))
        draw=cards.create_draw('alice',subject_id='self',case_id=case,question='合成问题',reversals=False,idempotency_key='bounded-shuffle')['draw']
        self.assertEqual(bounds,list(range(78,1,-1)))
        shown=cards.reveal('alice',draw['id']);self.assertTrue(all(c['orientation']=='upright' for c in shown['cards']))
        self.assertFalse(cards.preferences('alice')['reversals'])


    def test_cli_status_and_resume_share_service_budget_and_minimal_trace(self):
        from tools.core_run import execute_command
        self.configure_provider();self.provider.synthesis_failures=1
        with self.assertRaises(TimeoutError):self.consult(message='SYNTHETIC_CLI_PRIVATE_BODY',request_id='cli-recovery',depth='standard')
        run=self.run_by_request('cli-recovery')
        status=execute_command(self.service,owner='alice',run_id=run['id'],action='status')
        self.assertEqual(status['budget'],{'calls':2,'limit':6})
        self.assertNotIn('SYNTHETIC_CLI_PRIVATE_BODY',json.dumps(status))
        with self.assertRaises(ScopeError):execute_command(self.service,owner='bob',run_id=run['id'])
        result=execute_command(self.service,owner='alice',run_id=run['id'],action='resume')
        self.assertEqual(self.repo.fetch_run('alice',run['id'])['calls'],3)
        self.assertEqual(execute_command(self.service,owner='alice',run_id=run['id'],action='result'),result)
        self.assertEqual(execute_command(self.service,owner='alice',run_id=run['id'],action='resume'),result)
        self.assertEqual(len(self.provider.requests),3)


    def test_invalid_hard_constraint_answer_repairs_once_with_durable_charge(self):
        self.configure_provider();fact=self.save('我不能上夜班')
        self.provider.final_patch={'plain_summary':'可以每月破例上一次夜班。'}
        self.provider.repair_patch={'plain_summary':'先排除夜班安排，再核实白班条件。'}
        result=self.consult(request_id='one-charged-repair',depth='standard')
        run=self.run_by_request('one-charged-repair')
        self.assertEqual([r['purpose'] for r in self.provider.requests],['intake','synthesis','repair'])
        self.assertEqual(run['calls'],3);self.assertTrue(run['repair_used'])
        self.assertIn(fact['id'],result['cited_fact_ids']);self.assertNotIn('破例',result['plain_summary'])

    def test_natural_stop_uses_real_receipt_and_refreshes_current_context(self):
        self.configure_provider();fact=self.save('我喜欢上午学习')
        self.provider.retire_ids=[fact['id']]
        result=self.consult(message='停止使用“我喜欢上午学习”这条记忆',request_id='natural-stop')
        self.assertTrue(any(r.get('write_status')=='stopped' for r in result['memory_receipts']))
        self.assertNotIn(fact['id'],result['cited_fact_ids'])
        self.assertFalse(any(f['id']==fact['id'] for f in self.provider.requests[-1]['payload']['reference_data']['facts']))

    def test_unrelated_meeting_cap_is_allowed_without_relaxing_night_constraint(self):
        self.configure_provider();self.save('我不能上夜班')
        self.provider.final_patch={'actions':['每月最多2次面谈，用来核实白班条件。']}
        result=self.consult(request_id='allowed-meeting-cap')
        self.assertEqual(result['actions'],['每月最多2次面谈，用来核实白班条件。'])

    def test_fixed_tarot_meanings_ignore_later_in_memory_catalog_edit(self):
        from hermes.tarot_deck import CARD_BY_ID
        self.configure_provider();case=self.service.memory.create_case('alice','self','合成固定牌意')['id']
        draw=self.service.tarot.create_draw('alice',subject_id='self',case_id=case,question='合成反思问题',draw_source='manual',manual_cards=[{'card_id':c,'orientation':'upright'} for c in ('major-00','cups-01','pentacles-08')],idempotency_key='frozen-meaning')['draw']
        original=CARD_BY_ID['major-00']['upright']
        try:
            CARD_BY_ID['major-00']['upright']='后续未发布材料改版'
            revealed=self.service.tarot.reveal('alice',draw['id'])
            self.assertEqual(revealed['cards'][0]['card']['upright'],original)
        finally:CARD_BY_ID['major-00']['upright']=original
        provenance=self.service.knowledge.tarot_claims(revealed,owner='alice',subject='self',revision=self.repo.get_revision('alice'))
        self.assertTrue(provenance['claims'])
        self.assertTrue(self.service.knowledge.revalidate_claims({'artifacts':{},'features':{},'profiles':{},'branches':[]},provenance['claims'],provenance)['eligible'])
        altered=deepcopy(revealed);altered['draw_source']='auto'
        self.assertFalse(self.service.knowledge.tarot_claims(altered,owner='alice',subject='self',revision=self.repo.get_revision('alice'))['claims'])

    def test_cancelled_stage_reuses_draw_and_explicit_new_is_linked(self):
        self.configure_provider();case=self.service.memory.create_case('alice','self','合成同阶段')['id']
        args=dict(subject_id='self',case_id=case,question='合成问题',idempotency_key='first')
        first=self.service.tarot.create_draw('alice',**args)['draw'];self.service.tarot.cancel('alice',first['id'])
        reused=self.service.tarot.create_draw('alice',**dict(args,idempotency_key='after-cancel'))
        self.assertTrue(reused['reused']);self.assertEqual(reused['draw']['id'],first['id'])
        fresh=self.service.tarot.create_draw('alice',**dict(args,idempotency_key='explicit-next',explicit_new=True))['draw']
        self.assertNotEqual(fresh['id'],first['id']);self.assertEqual(fresh['previous_draw_id'],first['id'])

    def test_privacy_delete_purges_all_manual_revisions_readings_and_keys(self):
        from mingjing_core.adapters.tarot import IdempotencyConflict
        self.configure_provider();case=self.service.memory.create_case('alice','self','合成实体牌删除')['id'];cards=self.service.tarot
        manual=[{'card_id':c,'orientation':'upright'} for c in ('major-00','cups-01','pentacles-08')]
        args=dict(subject_id='self',case_id=case,question='合成问题',draw_source='manual',manual_cards=manual,idempotency_key='delete-all-root')
        root=cards.reveal('alice',cards.create_draw('alice',**args)['draw']['id'])
        first=cards.begin_reading('alice',root['id'],model='fixture',prompt_version='core3',context_snapshot={},idempotency_key='first-reading')['reading']
        cards.finish_reading('alice',first['id'],error='合成中断')
        revised=cards.revise_manual('alice',root['id'],[dict(c,orientation='reversed') for c in manual],'实体牌方向录错','manual-change')
        revised=cards.reveal('alice',revised['id'])
        second=cards.begin_reading('alice',revised['id'],model='fixture',prompt_version='core3',context_snapshot={},idempotency_key='second-reading')['reading']
        cards.finish_reading('alice',second['id'],error='合成中断')
        deleted=cards.delete('alice',root['id']);self.assertEqual(set(deleted['deleted_ids']),{root['id'],revised['id']})
        for ident in (root['id'],revised['id']):
            with self.assertRaises(KeyError):cards.get('alice',ident)
        for ident in (first['id'],second['id']):
            with self.assertRaises(KeyError):cards.get_reading('alice',ident)
        with self.assertRaises(IdempotencyConflict):cards.create_draw('alice',**args)


if __name__=='__main__':unittest.main()
