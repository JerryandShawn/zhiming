import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'hermes'))
from guidance import FINAL_SCHEMA, normalize_final, mode_schema, workflow, validate_final, validate_document, render_answer

DATE='2026-10-10'

def chart_fixture():
    charts={e:{'status':'ok','data':{'angle':1.5,'name':'例子'+e}} for e in ('bazi','ziwei','astro')}
    refs={f'chart:{e}:{DATE}':v for e,v in charts.items()}
    return refs,{DATE:charts}

def contribution(engine,status='used',evidence=True):
    return {'engine':engine,'status':status,'reason':'仅作为待核对的反思视角。',
            'evidence':[{'ref':f'chart:{engine}:{DATE}','path':'/angle','value':1.5}] if evidence else []}

class GuidanceModesTests(unittest.TestCase):
    def test_plain_and_correction_are_short_without_unused_fields(self):
        for message in ('你好','帮我复盘昨天','这条不对，以后别再用这个前提'):
            route=workflow(message);args={'plain_summary':'先核对你指出的那条记录。'}
            self.assertEqual(mode_schema(route)['required'],['plain_summary'])
            self.assertNotIn('synthesis',mode_schema(route)['properties'])
            validate_final(args,{}, {},route)
            self.assertEqual(render_answer(args),'先核对你指出的那条记录。')
            self.assertEqual(args['actions'],[]);self.assertEqual(args['synthesis'],[])
        self.assertEqual(workflow('这条不对，以后别再用这个前提')['mode'],'memory_correction')

    def test_normalization_is_not_an_invented_answer_or_shared_mutable_default(self):
        raw={'plain_summary':'你好。'};a=normalize_final(raw);b=normalize_final(raw)
        a['actions'].append('one')
        self.assertEqual(raw,{'plain_summary':'你好。'});self.assertEqual(b['actions'],[])
        self.assertNotIn('plain_summary',normalize_final({}))
        with self.assertRaises(ValueError):validate_final({}, {},{},workflow('你好'))
        self.assertEqual(FINAL_SCHEMA['required'],['plain_summary'])

    def test_support_needs_only_one_optional_low_burden_action(self):
        route=workflow('我今天有点焦虑')
        schema=mode_schema(route)
        self.assertEqual(set(schema['required']),{'plain_summary','actions'})
        self.assertNotIn('decision_options',schema['properties'])
        args={'plain_summary':'听起来你今天有些紧绷。','actions':['如果愿意，先放下手头的事坐一会儿。']}
        validate_final(args,{}, {},route)
        self.assertFalse(args['follow_up']);self.assertFalse(args['professional_appendix'])
        with self.assertRaises(ValueError):validate_final({'plain_summary':'我听到了。'}, {},{},route)

    def test_decision_contract_keeps_tradeoffs_without_charts(self):
        route=workflow('要不要转学？');schema=mode_schema(route)
        self.assertIn('decision_options',schema['required']);self.assertNotIn('synthesis',schema['properties'])
        args={'plain_summary':'先核对现实条件再决定。','actions':['了解课程安排。'],'follow_up':'拿到安排后再比较。',
              'decision_options':[{'option':name,'benefit':'可能适合','cost':'需要了解','risk':'情况未知','reversibility':'需核对退出条件','first_step':'先询问'} for name in ('了解新学校','暂时保持') ]}
        validate_final(args,{}, {},route)
        self.assertEqual(args['synthesis'],[])

    def test_tarot_does_not_trigger_three_charts_or_birth_requirement(self):
        for question in ('帮我用塔罗梳理一下','塔罗占卜','抽三张牌'):
            route=workflow(question)
            self.assertTrue(route['needs_tarot']);self.assertFalse(route['needs_charts'])
            self.assertNotIn('synthesis',mode_schema(route)['properties'])
        combined=workflow('把塔罗和八字作对照')
        self.assertTrue(combined['needs_charts']);self.assertTrue(combined['compare_systems'])

    def test_real_contribution_subset_not_forced_into_three(self):
        refs,calculated=chart_fixture()
        args={'plain_summary':'可以从两个角度观察，仍需现实反馈。','professional_appendix':'这里只解释实际字段。',
              'synthesis':[{'theme':'投入与节奏','relationship':'mixed','interpretation':'两种角度存在侧重差异。',
                            'contributions':[contribution('bazi'),contribution('astro')]}]}
        validate_final(args,refs,calculated,workflow('三盘综合'))
        self.assertEqual(len(args['synthesis'][0]['contributions']),2)
        ziwei=next(c for c in args['coverage'] if c['engine']=='ziwei')
        self.assertEqual(ziwei['status'],'notused');self.assertEqual(ziwei['evidence'],[])

    def test_one_contribution_is_not_called_consensus(self):
        refs,calculated=chart_fixture()
        args={'plain_summary':'只取得一个相关视角。','professional_appendix':'仍需现实核对。',
              'synthesis':[{'theme':'学习','relationship':'insufficient','interpretation':'不能据此形成共同结论。','contributions':[contribution('bazi')]}]}
        validate_final(args,refs,calculated,workflow('八字解释'))
        args['synthesis'][0]['relationship']='aligned'
        with self.assertRaisesRegex(ValueError,'少于两体系'):validate_final(args,refs,calculated,workflow('八字解释'))

    def test_noncontributions_do_not_need_fabricated_field_citations(self):
        refs,calculated=chart_fixture()
        args={'plain_summary':'现有素材不足以比较，不需要硬作共同结论。',
              'coverage':[contribution('bazi','not_relevant',False),contribution('ziwei','notused',False),contribution('astro','uncertain',False)]}
        validate_final(args,refs,calculated,workflow('三盘综合'))
        self.assertFalse(args['synthesis']);self.assertFalse(args['professional_appendix'])
        args['coverage'][0]['status']='used'
        with self.assertRaises(ValueError):validate_final(args,refs,calculated,workflow('三盘综合'))

    def test_unknown_fields_wrong_values_and_unavailable_lies_still_rejected(self):
        refs,calculated=chart_fixture()
        template={'plain_summary':'一个反思角度。','professional_appendix':'专业依据。','coverage':[contribution('bazi')]}
        for change in ({'path':'/missing'},{'value':'1.5'},{'ref':f'chart:astro:{DATE}'}):
            args=copy.deepcopy(template);args['coverage'][0]['evidence'][0].update(change)
            with self.assertRaises(ValueError):validate_final(args,refs,calculated,workflow('八字'))
        args=copy.deepcopy(template);args['coverage'][0]=contribution('bazi','unavailable',False)
        with self.assertRaisesRegex(ValueError,'已有可用'):validate_final(args,refs,calculated,workflow('八字'))

    def test_tarot_field_provenance_checks_registered_frozen_draw(self):
        refs={'tarot:draw-1':{'status':'ok','data':{'cards':[{'card_id':'cups-01','orientation':'reversed'}]}}}
        args={'plain_summary':'把这张牌当作表达感受的讨论入口。','professional_appendix':'此处采用冻结的实际方向。',
              'coverage':[{'engine':'tarot','status':'used','reason':'实际抽到的牌。','evidence':[{'ref':'tarot:draw-1','path':'/cards/0/orientation','value':'reversed'}]}]}
        validate_final(args,refs,{},workflow('看这张塔罗'))
        args['coverage'][0]['evidence'][0]['value']='upright'
        with self.assertRaises(ValueError):validate_final(args,refs,{},workflow('看这张塔罗'))

    def test_minimal_normal_reply_cli_does_not_compute_or_require_reports(self):
        with patch('chart_context.bundle') as compute:
            text=validate_document({'plain_summary':'先说说你现在最想处理的事。'}, {}, [],message='你好')
            compute.assert_not_called();self.assertEqual(text,'先说说你现在最想处理的事。')
        self.assertEqual(workflow('日报几点发送？')['mode'],'conversation')
        self.assertEqual(workflow('生成三盘联动晨报')['mode'],'report')
        with self.assertRaisesRegex(ValueError,'定期报告'):
            validate_final({'plain_summary':'只有一段摘要。'}, {},{},workflow('生成晨报'))

if __name__=='__main__':unittest.main()
