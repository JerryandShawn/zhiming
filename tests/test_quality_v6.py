"""Synthetic answer-quality regressions through the real v6 ChatAgent loop.

Provider responses are mocked; state, routing, source validation and frozen
tarot draws use their real implementations. No external model is contacted.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'hermes'))
from chat_agent import ChatAgent
from guidance import mode_schema,normalize_final,validate_final,workflow
from state_store import StateStore
from tarot_deck import card
from tarot_store import TarotDrawService


class Index:
    def search(self,*args):return []


class FakeClient:
    def __init__(self,replies):self.replies=iter(replies);self.requests=[]
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def post(self,url,headers,json):
        self.requests.append(copy.deepcopy(json))
        try:content=next(self.replies)
        except StopIteration:
            raise AssertionError('Unexpected retry feedback: '+str(json['messages'][-1]['content'])) from None
        class Response:
            status_code=200
            def json(self):return {'content':content,'usage':{'input_tokens':10,'output_tokens':10}}
        return Response()


def final_call(args,number=1):
    return [{'type':'tool_use','id':'quality-final-'+str(number),'name':'final_answer','input':args}]


class AnswerQualityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.archive=self.base/'archive.json';self.archive.write_text('{}',encoding='utf-8')
        self.state=StateStore(self.base);self.owner='quality-owner';self.state.ensure_owner(self.owner)
        self.turn_number=0;self.fact_number=0

    def fact(self,text,kind='constraint'):
        self.fact_number+=1
        row=self.state.import_message(self.owner,'web','quality-source-'+str(self.fact_number)+':user','user',text)
        return self.state.put_fact(self.owner,'self',text,[{'message_id':row['id'],'quote':text}],kind=kind,explicit=True)

    def decision(self,fact):
        return {
            'plain_summary':'先排除需要夜班的安排，再核对书面条件；资料不足时暂缓承诺。',
            'explanation':'现有条件不足以判断哪一个安排更合适。',
            'actions':['向两边询问书面班次，保留符合白班要求的安排。'],
            'decision_options':[
                {'option':'A：了解明确的白班岗位','benefit':'可能满足白天工作的要求','cost':'薪酬与通勤待核实',
                 'risk':'岗位是否合适仍未知','reversibility':'退出条件需提前核实','first_step':'询问书面班次'},
                {'option':'B：暂缓变动并核对当前安排','benefit':'保留比较条件的时间','cost':'等待成本需要了解',
                 'risk':'当前安排是否满足要求仍未知','reversibility':'以实际约定为准','first_step':'确认能否提供白班'}],
            'follow_up':'取得双方的班次和费用条件后，再检查是否符合现有约束。',
            'evidence':[{'ref':'fact:'+fact['id'],'claim':'工作边界来自已登记的用户原话。'}],
        }

    async def run_agent(self,message,answers,draw=None,case=None,full=False):
        self.turn_number+=1
        agent=ChatAgent(object(),Index(),str(self.archive),lambda *args:[],'fixture-key','https://fixture.invalid','fixture-model','')
        agent.state_store=self.state;agent.owner_id=self.owner;agent.subject_id='self';agent.legacy_owner=False
        agent.case_ids=[case] if case else None;agent.draw=draw;agent.tarot_full=full
        turn={'id':'quality-turn-'+str(self.turn_number),'message':message,'selection':'{}','images':'[]','session_id':'shared'}
        fake=FakeClient([final_call(answer,n+1) for n,answer in enumerate(answers)])
        events=[]
        async def emit(event):events.append(event)
        with patch('v6_agent.httpx.AsyncClient',return_value=fake):
            result=await agent.run(turn,emit)
        return result,fake.requests,events

    async def assert_repaired(self,bad,good,fact,error_fragment,message='工作安排该怎么选？',**kwargs):
        # The rejected answer is structurally valid. Its failure must come from
        # the quality gate, not missing decision fields or a made-up citation.
        if not kwargs.get('draw'):
            schema_evidence={'fact:'+row['id']:{'source':'memory','data':row} for row in self.state.list_facts(self.owner)}
            validate_final(normalize_final(bad),schema_evidence, {},workflow(message))
        result,requests,_=await self.run_agent(message,[bad,good],**kwargs)
        self.assertEqual(result['meta']['tool_rounds'],2,'The unsafe first final_answer was accepted')
        self.assertEqual(len(requests),2)
        feedback=requests[1]['messages'][-1]['content'][0]
        self.assertTrue(feedback.get('is_error'))
        self.assertIn(error_fragment,feedback['content'])
        self.assertEqual(result['plain_summary'],good['plain_summary'])
        self.assertIn('fact:'+fact['id'],[item['ref'] for item in result['evidence']])
        original=self.state.get_fact(self.owner,fact['id'])
        self.assertEqual(original['content'],fact['content'])
        self.assertEqual(original['source_refs'],fact['source_refs'])
        self.assertEqual(original['status'],'active')
        return result,requests

    async def test_night_shift_exceptions_and_monthly_caps_error_then_repair(self):
        fact=self.fact('我不能上夜班。');good=self.decision(fact)
        for text in ('可以尝试少量夜班来协调安排。','夜班可以少量例外。','每月最多2次夜班。'):
            with self.subTest(suggestion=text):
                bad=copy.deepcopy(good);bad['decision_options'][1]['first_step']=text
                result,_=await self.assert_repaired(bad,good,fact,'不能上夜班')
                self.assertNotIn(text,json.dumps(result,ensure_ascii=False))

    async def test_night_shift_exception_in_plain_summary_is_also_rejected(self):
        fact=self.fact('我不能上夜班。');good=self.decision(fact);bad=copy.deepcopy(good)
        bad['plain_summary']='可以接受少量夜班，作为协商中的例外。'
        await self.assert_repaired(bad,good,fact,'不能上夜班')

    async def test_unknown_cost_or_familiarity_cannot_support_recommendation(self):
        fact=self.fact('我不能上夜班。');good=self.decision(fact)
        for reason in ('由于协商成本低，优先保留B方案。','现有关系都已熟悉，优先保留B方案。','关系和流程熟悉，优先保留B方案。'):
            with self.subTest(reason=reason):
                bad=copy.deepcopy(good);bad['plain_summary']=reason
                await self.assert_repaired(bad,good,fact,'没有已授权现实来源')

    async def test_unknowns_marked_as_missing_are_accepted_without_inventing_a_preference(self):
        fact=self.fact('我不能上夜班。');good=self.decision(fact)
        good['plain_summary']='协商成本和流程熟悉程度都未知，暂不因这些条件偏向任何方案。'
        result,requests,_=await self.run_agent('工作安排该怎么选？',[good])
        self.assertEqual(len(requests),1);self.assertEqual(result['meta']['tool_rounds'],1)
        self.assertEqual(result['plain_summary'],good['plain_summary'])
        self.assertEqual([row['id'] for row in self.state.list_facts(self.owner)],[fact['id']])

    async def test_supported_cost_and_familiarity_keep_their_real_source(self):
        fact=self.fact('我不能上夜班。')
        known=self.fact('我对现有关系和流程都已熟悉，协商成本低。',kind='background')
        good=self.decision(fact)
        good['plain_summary']='现有关系和流程都已熟悉，协商成本低，可作为比较条件；仍须先核实白班安排。'
        good['evidence'].append({'ref':'fact:'+known['id'],'claim':'熟悉程度与成本是用户明确提供的条件。'})
        result,requests,_=await self.run_agent('结合现有流程与协商成本，工作安排该怎么选？',[good])
        self.assertEqual(len(requests),1)
        self.assertIn('fact:'+known['id'],[item['ref'] for item in result['evidence']])

    async def test_known_familiarity_does_not_authorize_unknown_low_negotiation_cost(self):
        fact=self.fact('我不能上夜班。')
        known=self.fact('我对现有流程都已熟悉。',kind='background')
        good=self.decision(fact)
        good['evidence'].append({'ref':'fact:'+known['id'],'claim':'只有流程熟悉程度有用户原话，成本尚不清楚。'})
        bad=copy.deepcopy(good);bad['plain_summary']='因为协商成本低，优先保留B方案。'
        await self.assert_repaired(bad,good,fact,'没有已授权现实来源',message='结合现有流程与协商成本，工作安排该怎么选？')

    async def test_unrelated_monthly_meeting_limit_does_not_relax_night_shift_constraint(self):
        fact=self.fact('我不能上夜班。');good=self.decision(fact)
        good['actions']=['每月最多2次面谈，用来核实白班条件。']
        result,requests,_=await self.run_agent('工作安排该怎么选？',[good])
        self.assertEqual(len(requests),1)
        self.assertEqual(result['actions'],good['actions'])

    async def test_full_tarot_moves_card_name_chain_to_interpretations_without_changing_draw(self):
        fact=self.fact('我不能上夜班。')
        case=self.state.create_case(self.owner,'self','工作安排比较')['id']
        tarot=TarotDrawService(self.base,randbelow=lambda n:n-1)
        draw=tarot.create_draw(self.owner,subject_id='self',case_id=case,question='比较两个工作安排的现实取舍',
                               spread_id='choice5',options={'A':'了解明确的白班岗位','B':'暂缓变动并核对当前安排'},
                               context_snapshot={'fact_ids':[fact['id']]},idempotency_key='quality-draw')['draw']
        draw=tarot.reveal(self.owner,draw['id']);before=copy.deepcopy(draw)
        good=self.decision(fact)
        good.update(reality_context=[{'kind':'known','statement':'用户不能上夜班','ref':'fact:'+fact['id']},
                                     {'kind':'missing','statement':'协商成本与熟悉程度尚不清楚','ref':''}],
                    card_interpretations=[{'position':entry['position'],'card_id':entry['card_id'],'orientation':entry['orientation'],
                       'theme':card(entry['card_id'])['name']+'的象征主题',
                       'interpretation':card(entry['card_id'])['name']+'仅用于提出检查条件的问题，不能证明哪种安排更合适。',
                       'question':'这个提示对应的现实条件是否已核实？'} for entry in draw['cards']],
                    tarot_synthesis=['各牌提示可能有侧重差异；现实选择仍按已知约束与待核实条件比较。'],
                    professional_appendix='逐牌内容来自这次固定的牌位和方向，只作为反思提示，不构成现实预测。')
        good['evidence'].append({'ref':'tarot:'+draw['id'],'claim':'采用本次冻结的实际牌面。','path':'/cards/0/card_id','value':draw['cards'][0]['card_id']})
        names=[card(entry['card_id'])['name'] for entry in draw['cards'][:2]]
        bad=copy.deepcopy(good)
        bad['explanation']=names[0]+'逆位说明应该谨慎，'+names[1]+'逆位说明先确认条件，所以先暂缓承诺。'
        result,_=await self.assert_repaired(bad,good,fact,'白话正文不要逐牌',message='请完整解读这次塔罗牌阵。',draw=draw,case=case,full=True)
        self.assertEqual(tarot.get(self.owner,draw['id']),before)
        self.assertEqual(result['meta']['draw_id'],draw['id'])
        self.assertEqual(result['validation']['draw_id_checked'],draw['id'])
        self.assertTrue(result['validation']['cards_checked'])
        self.assertEqual([(row['position'],row['card_id'],row['orientation']) for row in result['card_interpretations']],
                         [(row['position'],row['card_id'],row['orientation']) for row in before['cards']])
        plain=result['plain_summary']+result['explanation']
        self.assertTrue(all(name not in plain for name in names))
        self.assertTrue(all(name in json.dumps(result['card_interpretations'],ensure_ascii=False) for name in names))

    async def test_completed_choice_and_deferral_are_feedback_not_new_decisions(self):
        for message in ('我后来选了B','我决定工作安排先暂缓'):
            with self.subTest(message=message):
                route=workflow(message)
                self.assertEqual(route['mode'],'conversation');self.assertFalse(route['decision'])
                self.assertNotIn('decision_options',mode_schema(route)['required'])
                result,requests,_=await self.run_agent(message,[{'plain_summary':'收到，可以围绕已经作出的选择继续复盘。'}])
                self.assertEqual(len(requests),1)
                self.assertEqual(result['meta']['workflow']['mode'],'conversation')
                self.assertFalse(result['decision_options'])


if __name__=='__main__':unittest.main(verbosity=2)
