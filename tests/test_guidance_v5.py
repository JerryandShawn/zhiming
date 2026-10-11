import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'hermes'))
from guidance import workflow,validate_final,validate_document,render_answer,render_document,source_kind
from report_store import store_structured,store
from report_pipeline import Pipeline,TZ
from archive_store import atomic_write,read_json

DATE='2026-09-30'
def fixtures():
    charts={e:{'status':'ok','data':{'position':'示例'+e,'angle':1.5}} for e in ('bazi','ziwei','astro')}
    evidence={f'chart:{e}:{DATE}':v for e,v in charts.items()}
    args={'plain_summary':'先做一次小范围尝试，再结合实际结果调整。','explanation':'你还没有提供目前的进度，以下是可调整的建议。',
          'actions':['今天挑一个十分钟能完成的小任务。'],'decision_options':[],'follow_up':'明天看是否完成，再决定是否调整。',
          'professional_appendix':'这里是末尾的专业依据；传统象征不等于事实预测。','evidence':[], 'caveats':['缺少最近的实际进度。'],
          'synthesis':[{'theme':'当前学习安排','relationship':'mixed','interpretation':'三种传统解释侧重不同，不能折算成成功率。','contributions':[
              {'engine':e,'status':'used','reason':'此字段只作为观察角度，不能判定现实结果。','evidence':[{'ref':f'chart:{e}:{DATE}','path':'/position','value':'示例'+e}]}
              for e in charts]}]}
    return args,evidence,{DATE:charts}

class GuidanceTests(unittest.TestCase):
    def test_routes_prioritize_user_need(self):
        self.assertFalse(workflow('帮我复盘昨天的学习')['needs_charts'])
        self.assertTrue(workflow('综合八字紫微星盘看看学习')['needs_charts'])
        self.assertEqual(workflow('我很焦虑，睡不着')['mode'],'support')
        self.assertFalse(workflow('不要算命，帮我安排学习',{'system':'ziwei'})['needs_charts'])
        self.assertFalse(workflow('不需要八字和紫微，帮我整理复习计划')['needs_charts'])
        self.assertFalse(workflow('别看星盘，只想聊聊天')['needs_charts'])
        self.assertFalse(workflow('这道复合函数题怎么做')['decision'])
        self.assertFalse(workflow('帮我选择一个笑话')['decision'])
        self.assertNotEqual(workflow('我没有想自杀，只是担心期末考试')['mode'],'urgent_support')
        self.assertFalse(workflow('我担心你没理解，请再看一遍我的描述')['reassurance_loop'])
        self.assertTrue(workflow('要不要转学？')['decision'])
        r=workflow('我很害怕，请再算一次保证不会出事')
        self.assertTrue(r['reassurance_loop']);self.assertFalse(r['chart_allowed'])
        r=workflow('我不想活了，命盘是不是这样？')
        self.assertEqual(r['mode'],'urgent_support');self.assertFalse(r['needs_charts'])
        self.assertEqual(workflow('我想死')['mode'],'urgent_support')

    def test_three_engines_required_not_one_reference(self):
        args,refs,calculated=fixtures()
        validate_final(args,refs,calculated,workflow('三盘分析'))
        args['synthesis'][0]['contributions'].pop()
        # A real contribution subset is permitted; missing systems need not invent support.
        validate_final(args,refs,calculated,workflow('三盘分析'))

    def test_malformed_model_input_is_repairable(self):
        args,refs,calculated=fixtures()
        for invalid in (None,[],42):
            with self.assertRaises(ValueError):validate_final(invalid,refs,calculated,workflow('三盘分析'))
        args['synthesis'][0]['contributions'][0]['engine']=[]
        with self.assertRaises(ValueError):validate_final(args,refs,calculated,workflow('三盘分析'))

    def test_reader_layer_rejects_dense_jargon_and_unprompted_emergency(self):
        args,refs,calculated=fixtures();args['explanation']='日主戊土，流日丁未，太阴化禄，容许度2度。'
        with self.assertRaisesRegex(ValueError,'密集术语'):validate_final(args,refs,calculated,workflow('三盘分析'))
        args,refs,calculated=fixtures();args['explanation']='考试焦虑时立刻联系急救。'
        with self.assertRaisesRegex(ValueError,'普通担心'):validate_final(args,refs,calculated,workflow('考试让我焦虑'))
        args['explanation']='急救课程通常可以从基础内容学起，先核对课程要求。'
        validate_final(args,refs,calculated,workflow('急救课程适合零基础吗？'))

    def test_invented_field_value_and_cross_engine_rejected(self):
        for key,value in [('path','/invented'),('value','错误星曜'),('ref',f'chart:astro:{DATE}')]:
            args,refs,calculated=fixtures();args['synthesis'][0]['contributions'][0]['evidence'][0][key]=value
            with self.assertRaises(ValueError):validate_final(args,refs,calculated,workflow('三盘分析'))
        args,refs,calculated=fixtures()
        args['evidence']=[{'ref':f'chart:bazi:{DATE}','claim':'伪造的笼统出处'}]
        with self.assertRaises(ValueError):validate_final(args,refs,calculated,workflow('三盘分析'))

    def test_scalar_evidence_preserves_types(self):
        args,refs,calculated=fixtures();cite=args['synthesis'][0]['contributions'][0]['evidence'][0]
        cite.update(path='/angle',value=1.5);validate_final(args,refs,calculated,workflow('三盘分析'))
        cite['value']='1.5'
        with self.assertRaises(ValueError):validate_final(args,refs,calculated,workflow('三盘分析'))

    def test_missing_and_not_relevant_are_honest(self):
        args,refs,calculated=fixtures();theme=args['synthesis'][0];theme['relationship']='insufficient'
        for contribution in theme['contributions'][1:]:contribution['status']='not_relevant'
        validate_final(args,refs,calculated,workflow('三盘分析'))
        theme['relationship']='aligned'
        with self.assertRaisesRegex(ValueError,'少于两体系'):validate_final(args,refs,calculated,workflow('三盘分析'))
        args,refs,calculated=fixtures();c=args['synthesis'][0]['contributions'][0];c.update(status='unavailable',evidence=[])
        with self.assertRaisesRegex(ValueError,'已有可用'):validate_final(args,refs,calculated,workflow('三盘分析'))
        calculated[DATE]['bazi']={'status':'missing','reason':'出生时刻不明'}
        validate_final(args,refs,calculated,workflow('三盘分析'))

    def test_decision_requires_tradeoffs_and_review(self):
        args,refs,calculated=fixtures();route=workflow('要不要换学校？')
        with self.assertRaisesRegex(ValueError,'至少2个'):validate_final(args,refs,calculated,route)
        args['decision_options']=[dict(option=n,benefit='可能更适合，待验证',cost='先花半小时了解',risk='信息不全',reversibility='可暂停',first_step='先询问课程安排') for n in ('先了解','先保持')]
        args['decision_options'][0]['risk']='不能保证零风险，需核实费用和退出条件'
        validate_final(args,refs,calculated,route)
        self.assertLess(render_document(args).index('现在可以做'),render_document(args).index('专业依据与方法边界'))
        self.assertNotIn(args['professional_appendix'],render_answer(args))

    def test_plain_chat_requires_no_chart_and_history_not_fact(self):
        args,_,_=fixtures();args['synthesis']=[];args['professional_appendix']=''
        validate_final(args,{}, {},workflow('你好'))
        with patch('chart_context.bundle') as calculate:
            validate_document(args,{},[],message='你好');calculate.assert_not_called()
        self.assertIn('not_fact',source_kind('reports'))
        self.assertIn('not_verified',source_kind('history.feishu',{'role':'assistant'}))

    def test_report_recomputes_before_archive(self):
        args,refs,calculated=fixtures()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'archive.json';atomic_write(path,{'user':{}})
            with patch('chart_context.bundle',return_value=calculated[DATE]):
                with self.assertRaises(ValueError):store(path,DATE,'晨报','编造报告'*100,structured={'fake':True})
                store_structured(path,DATE,'晨报',args)
                record=read_json(path)['reports'][0]
                self.assertEqual(record['schema_version'],'5.0');self.assertTrue(record['validation']['chart_fields_checked'])
                args['synthesis'][0]['contributions'][0]['evidence'][0]['value']='编造'
                with self.assertRaises(ValueError):store_structured(path,DATE,'晨报',args)
                self.assertEqual(read_json(path)['reports'][0],record)

    def test_pipeline_rejects_unvalidated_new_report(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);atomic_write(p/'report-pipeline.json',{'enabled':True,'structured_from':DATE,'jobs':[{'id':'daily','kind':'daily','target':'oc_fixture'}]})
            atomic_write(p/'archive.json',{'reports':[{'date':DATE,'type':'晨报','schema_version':'3.0','content':'未经验证的报告'*60}]})
            pipeline=Pipeline(d,p/'cron');now=datetime(2026,9,30,6,50,tzinfo=TZ);pipeline.seed(now);pipeline.prepare(now)
            self.assertEqual(next(r for r in pipeline.rows() if r['date']==DATE)['status'],'waiting')
            arc=read_json(p/'archive.json');arc['reports'][0].update(schema_version='5.0',validation={'chart_fields_checked':True});atomic_write(p/'archive.json',arc)
            pipeline.prepare(now);self.assertEqual(next(r for r in pipeline.rows() if r['date']==DATE)['status'],'ready')

if __name__=='__main__':unittest.main(verbosity=2)
