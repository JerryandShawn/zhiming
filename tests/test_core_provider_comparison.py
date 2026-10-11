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
        self.assertEqual(single['durable_budget']['calls'],3)
        self.assertEqual(multi['durable_budget']['calls'],6)
        self.assertTrue(single['fixed_cards_unchanged']);self.assertTrue(multi['fixed_cards_unchanged'])

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
