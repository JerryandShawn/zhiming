"""Comparison preflight; provider only is replaced, not either business flow."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_core_memory import test_dsn
from tests.test_core_charts import has_dependency
from tools import compare_core_providers as comparison
from mingjing_core.adapters.model import ConfiguredModel


class CoreProviderComparisonPreflight(unittest.TestCase):
    def test_plan_only_invokes_no_provider_or_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'plan.json'
            with patch.object(ConfiguredModel,'generate',side_effect=AssertionError('No calls in dry-run')):
                comparison.main(['--legacy-root',str(comparison.ROOT),'--output',str(output),'--dry-run'])
            result=json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(result['provider_calls'],0)
            self.assertEqual(result['status'],'plan_only_no_provider_calls')
            self.assertEqual(result['fixed_cards'],comparison.FIXED_CARDS)
            self.assertEqual(result['arm_budgets']['tarot']['new_single_specialist'],{'depth':'standard','call_limit':6})
            self.assertEqual(result['arm_budgets']['tarot']['new_controlled_multi_specialists'],{'depth':'deep','call_limit':10})
            for arm in comparison.ARMS[2:]:self.assertEqual(result['arm_budgets']['decision'][arm],{'depth':'standard','call_limit':6})
            self.assertEqual(result['arm_budgets']['tarot']['legacy'],{'depth':'original_v5','call_limit':None,'legacy_tool_round_limit':8})
            self.assertTrue(any('not a same-budget comparison' in limit for limit in result['measurement_limits']))

    @unittest.skipUnless(os.getenv('CHART_PYTHON') and all(has_dependency(x) for x in ('lunar_python', 'pythonmonkey', 'swisseph')),
                         'requires actual configured CHART_PYTHON with all three calculator libraries')
    def test_current_single_and_multi_use_actual_specialists_and_same_manual_cards(self):
        def provider(model,**kwargs):
            data=kwargs['payload']['reference_data'];purpose=kwargs['purpose']
            if purpose=='intake':
                output={'plan':{'mode':'tarot','topic':'study','systems':['bazi','ziwei','astro','tarot'],
                    'target_date':'2026-10-11','time_scale':'natal','decision':True,'rationale':'合成脚本预检','missing_inputs':[]},
                    'proposals':[],'retire_fact_ids':[],'attachment_observations':[]}
            elif purpose.startswith('specialist:'):
                output={'system':purpose.split(':')[1],'claim_ids':[c['claim_id'] for c in data['claims']],
                        'discussion':'仅在发布规则内提供独立的条件反思。','uncertainties':[]}
            else:
                output={'plain_summary':'先核对实际班次和费用，再选择可逆的小行动。','explanation':'象征仅供讨论。',
                        'actions':['先核实白班要求。'],
                        'decision_options':[{'option':label,'benefit':'核实后才能判断白班条件','cost':'实际费用未知','risk':'班次条件待核实',
                            'reversibility':'先询问，再承诺','first_step':'核实书面班次与费用'} for label in ('核实A','核实B')],
                        'follow_up':'按现实反馈复盘。',
                        'professional_appendix':'仅按已验证字段与规则解释，象征不能证明现实结局。','cited_fact_ids':[f['id'] for f in data.get('facts',[])],
                        'cited_claim_ids':[c['claim_id'] for c in data.get('claims',[])],'caveats':[]}
            return {'output':output,'usage':{'input_tokens':7,'output_tokens':11},'latency_seconds':0,'model':'synthetic-preflight'}
        with patch.dict(os.environ,{'CORE_COMPARE_PREFLIGHT_DSN':test_dsn()}),patch.object(ConfiguredModel,'generate',provider):
            single=comparison.core_worker('new_single_specialist','tarot','CORE_COMPARE_PREFLIGHT_DSN')
            multi=comparison.core_worker('new_controlled_multi_specialists','tarot','CORE_COMPARE_PREFLIGHT_DSN')
        self.assertEqual(single['status'],'validated',single.get('error_type'))
        self.assertEqual(multi['status'],'validated',multi.get('error_type'))
        self.assertEqual(single['specialist_provider_calls'],1)
        self.assertEqual(multi['specialist_provider_calls'],4)
        self.assertEqual((single['depth'],single['call_limit'],single['durable_budget']),('standard',6,{'calls':3,'limit':6}))
        self.assertEqual((multi['depth'],multi['call_limit'],multi['durable_budget']),('deep',10,{'calls':7,'limit':10}))
        self.assertEqual((single['base_phase_provider_calls'],multi['base_phase_provider_calls']),(3,6))
        self.assertEqual((single['review_provider_calls'],multi['review_provider_calls']),(0,1))
        self.assertEqual((single['repair_provider_calls'],multi['repair_provider_calls']),(0,0))
        self.assertEqual([c['purpose'] for c in multi['calls']].count('review'),1)
        self.assertTrue(single['fixed_cards_unchanged']);self.assertTrue(multi['fixed_cards_unchanged'])
        self.assertEqual(single['validation_attempts'][0]['issues'],[])
        self.assertEqual(multi['last_phase'],'commit')

    def test_isolated_legacy_and_context_only_expansion_run_original_controller(self):
        import httpx
        class Response:
            status_code=200
            def __init__(self,body):self.body=body
            def json(self):return self.body
        class ProviderTransport:
            def __init__(self,**kwargs):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def post(self,url,headers,json):
                pinned=__import__('json').loads(json['system'].split('<reference_data>')[-1].split('</reference_data>')[0])
                fact=next(f for f in pinned['retrieved'] if f['source']=='memory' and f['data'].get('text')=='我不能上夜班')
                final={'plain_summary':'先排除夜班安排，实际成本尚未知。','actions':['向两边核实书面条件。'],
                       'follow_up':'核实后复盘。','evidence':[{'ref':fact['ref'],'claim':'限制来自合成用户原话。'}],
                       'explanation':'只比较现实条件。','professional_appendix':'','synthesis':[],'caveats':[],
                       'decision_options':[{'option':label,'benefit':'可能符合白班要求','cost':'实际费用未知','risk':'班次仍待核实',
                                           'reversibility':'提前核对退出条件','first_step':'向负责人核实'} for label in ('核实A','核实B')]}
                return Response({'content':[{'type':'tool_use','id':'preflight-final','name':'final_answer','input':final}],
                                 'usage':{'input_tokens':13,'output_tokens':17}})
        previous=dict(os.environ)
        try:
            with patch.dict(os.environ,{'KIMI_API_KEY':'synthetic-preflight-only'}),patch.object(httpx,'AsyncClient',ProviderTransport):
                old=comparison.legacy_worker('legacy','decision',comparison.LEGACY_FIXTURE)
                expanded=comparison.legacy_worker('expanded_legacy','decision',comparison.LEGACY_FIXTURE)
        finally:
            os.environ.clear();os.environ.update(previous)
        self.assertEqual(old['status'],'validated',old.get('error_type'))
        self.assertEqual(expanded['status'],'validated',expanded.get('error_type'))
        self.assertEqual((old['provider_calls'],expanded['provider_calls']),(1,1))
        self.assertGreater(expanded['input_body_bytes'],old['input_body_bytes'])
        self.assertEqual(old['legacy_source_hashes'],expanded['legacy_source_hashes'])
        self.assertEqual(len(old['legacy_source_hashes']),10)
        self.assertEqual(old['context_only_source_changes'],[])
        self.assertEqual(len(expanded['context_only_source_changes']),2)
        self.assertEqual((old['depth'],old['call_limit'],old['legacy_tool_round_limit']),('original_v5',None,8))
        self.assertEqual(old['calls'][0]['contract_tools'][0]['name'],'final_answer')
        self.assertIn('plain_summary',old['calls'][0]['contract_tools'][0]['output'])

    def test_failure_diagnostics_preserve_strict_business_issues_and_contract_output(self):
        def provider(model,**kwargs):
            self.assertIn('询问与等待也有时间和机会成本',kwargs['system'])
            self.assertIn('已保存塔罗声明',kwargs['system'])
            self.assertIn('本轮引用的声明',kwargs['system'])
            data=kwargs['payload']['reference_data']
            if kwargs['purpose']=='intake':
                output={'plan':{'mode':'decision','topic':'career','systems':[],
                    'target_date':'2026-10-11','time_scale':'natal','decision':True,'rationale':'合成失败诊断','missing_inputs':[]},
                    'proposals':[],'retire_fact_ids':[],'attachment_observations':[]}
            else:
                if kwargs['purpose']=='repair':
                    instruction=kwargs['payload']['instruction']
                    self.assertIn('未知费用、退出条件或时限不能宣称零风险、完全可逆或无损失',instruction)
                    self.assertIn('询问和等待也有时间及机会成本',instruction)
                    self.assertIn('塔罗声明、牌面和资料',instruction)
                    self.assertIn('保存状态由程序真实回执生成',instruction)
                output={'plain_summary':'你可以每月上一次夜班。','explanation':'这条错误内容必须被真正业务校验拒绝。',
                    'actions':['先核实书面条件。'],'decision_options':[{'option':x,'benefit':'待确认','cost':'未知',
                        'risk':'待确认','reversibility':'待核实','first_step':'询问班次'} for x in ('询问A','询问B')],
                    'follow_up':'核实后复盘','professional_appendix':'','cited_fact_ids':[f['id'] for f in data.get('facts',[])],
                    'cited_claim_ids':[],'caveats':[]}
            return {'output':output,'usage':{},'latency_seconds':0,'model':'synthetic-preflight'}
        with patch.dict(os.environ,{'CORE_COMPARE_PREFLIGHT_DSN':test_dsn()}),patch.object(ConfiguredModel,'generate',provider):
            result=comparison.core_worker('new_single_specialist','decision','CORE_COMPARE_PREFLIGHT_DSN')
            controlled=comparison.core_worker('new_controlled_multi_specialists','decision','CORE_COMPARE_PREFLIGHT_DSN')
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['error_type'],'InvalidAnswer')
        self.assertEqual(result['last_phase'],'validation')
        self.assertEqual(result['provider_calls'],3)
        self.assertEqual(len(result['validation_attempts']),2)
        self.assertTrue(all(any('不能上夜班' in issue for issue in a['issues']) for a in result['validation_attempts']))
        self.assertEqual(result['calls'][-1]['contract_output']['plain_summary'],'你可以每月上一次夜班。')
        for row in (result,controlled):
            self.assertEqual((row['depth'],row['call_limit'],row['durable_budget']),('standard',6,{'calls':3,'limit':6}))
            self.assertEqual(row['specialist_provider_calls'],0)
            self.assertEqual(row['review_provider_calls'],0)

    def test_contract_diagnostics_drop_thinking_headers_and_known_secrets(self):
        from mingjing_core.domain.consultation import FinalAnswer,Intake
        secret='synthetic-only-secret-do-not-persist'
        raw={'plain_summary':'合成 '+secret,'thinking':'DO_NOT_WRITE_THINKING',
             'headers':{'x-api-key':'DO_NOT_WRITE_HEADER'},'decision_options':[
             {'option':'A','benefit':'核实条件','headers':{'authorization':'DO_NOT_WRITE_NESTED'},'thinking':'DO_NOT_WRITE_NESTED_THINKING'}]}
        clean=comparison.synthetic_contract_snapshot(raw,FinalAnswer.model_json_schema(),[secret])
        encoded=json.dumps(clean)
        self.assertNotIn('DO_NOT_WRITE',encoded)
        self.assertNotIn(secret,encoded)
        self.assertEqual(clean['plain_summary'],'合成 <redacted>')
        nested=comparison.synthetic_contract_snapshot({'proposals':[{'value':{'headers':{'x-api-key':'DO_NOT_WRITE_ANY'},'safe':3}}]},Intake.model_json_schema())
        self.assertEqual(nested,{'proposals':[{'value':{'safe':3}}]})

    def test_modified_legacy_helper_is_rejected_before_provider_call(self):
        import shutil
        with tempfile.TemporaryDirectory() as temporary:
            copied=Path(temporary)/'production_v5'
            shutil.copytree(comparison.LEGACY_FIXTURE,copied)
            with (copied/'guidance.py').open('a',encoding='utf-8') as changed:changed.write('\n# altered source\n')
            with patch.object(ConfiguredModel,'generate',side_effect=AssertionError('No provider')):
                with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                    comparison.legacy_worker('legacy','decision',copied)


if __name__=='__main__':unittest.main()
