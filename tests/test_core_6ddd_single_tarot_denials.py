"""Original synthetic failed 6ddd Tarot replay; only model HTTP is substituted.

The opaque case fact pair is projected only as a complete set. Current quote
identity is proven by owner/source/case/kind/exact original span, not array order.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.repositories.postgres import fingerprint
from tests import test_core_comparison_repairs as helpers
from tests import test_core_76b_provider_denials as providers
from tests.test_core_035_comparison_tarot_denials import RecordedHttpModel, original_profile_ids
from tools.compare_core_providers import FACTS, card_projection

FIXTURE=Path(__file__).parent/'fixtures/6ddd_single_tarot_denials.json'


class CaseBoundRecordedHttpModel(RecordedHttpModel):
    def __init__(self,evidence,owner,case_id):
        ConfiguredModel.__init__(self,key='synthetic-test-key',base='https://synthetic.invalid/v1',model='synthetic-original-6ddd')
        self.evidence=evidence;self.owner=owner;self.case_id=case_id
        self.records=evidence['sample']['calls']
        self.original_outputs={c['purpose']:c['contract_output'] for c in self.records}
        self.trace=[];self.outputs={};self.claim_map={};self.span_map={};self.actual_spans={}
        self.unsafe_review=False;self.invalid_fact=None;self.natural_ids=False;self.failed_astro=False
        self.reference_data=None;self.purpose=None
        self.program_source_id='msg_'+fingerprint([owner,'web','fixed-target','user'])[:32]
        question=evidence['questions']['tarot']
        proposals=self.original_outputs['intake']['proposals']
        assert len(proposals)==2
        old_cases={p['case_id'] for p in proposals};assert len(old_cases)==1
        self.original_case=next(iter(old_cases));assert isinstance(self.original_case,str)
        for proposal in proposals:
            assert proposal['category']=='背景' and proposal.get('field') is None and proposal.get('value') is None
            quote=proposal['quote'];start=question.index(quote);end=start+len(quote)
            old='current_source_'+fingerprint([owner,self.program_source_id,start,end,'background',self.original_case,None,None])[:32]
            self.span_map[old]={'quote':quote,'kind':'background','start':start,'end':end,'message_id':self.program_source_id}
        citation_sets={frozenset(o['cited_fact_ids']) for o in self.original_outputs.values() if 'cited_fact_ids' in o}
        assert len(citation_sets)==1
        self.original_citations=next(iter(citation_sets))
        assert set(self.span_map)<=self.original_citations
        self.profile_citations=self.original_citations&original_profile_ids(owner)
        assert len(self.profile_citations)==6
        self.old_pair=self.original_citations-set(self.span_map)-self.profile_citations
        assert len(self.old_pair)==2 and all(i.startswith('fact_') for i in self.old_pair)
        # The pinned comparison seed creates exactly two case facts plus seven
        # global profile facts. Only the entire old case set has known meaning.
        assert all('引用了本轮有效范围之外的事实' not in v['issues']
                   for v in evidence['sample']['validation_attempts'])
        for output in self.original_outputs.values():
            body=json.dumps({k:v for k,v in output.items() if k!='cited_fact_ids'},ensure_ascii=False)
            assert all(old not in body for old in self.old_pair)

    def _bindings(self,data):
        if not data.get('facts'):return
        self.reference_data=data;self.case_pair=[]
        for kind,content in FACTS:
            actual=[f for f in data['facts'] if f['kind']==kind and f['content']==content and
                    f.get('case_id')==self.case_id and not f.get('context_only')]
            assert len(actual)==1
            self.case_pair.append(actual[0]['id'])
        assert self.profile_citations<={f['id'] for f in data['facts'] if f['kind']=='profile' and f.get('case_id') is None}
        for old,span in self.span_map.items():
            actual=[f for f in data['facts'] if f.get('context_only') and f['kind']==span['kind'] and
                    f['content']==span['quote'] and f['case_id']==self.case_id and f['owner_user_id']==self.owner and
                    f['subject_id']=='self' and any(all(ref.get(k)==span[k] for k in ('message_id','start','end'))
                    for ref in f['source_refs'])]
            assert len(actual)==1
            self.actual_spans[old]=actual[0]['id']

    def bind(self,value):
        def walk(item):
            if isinstance(item,dict):
                result={key:walk(child) for key,child in item.items()}
                if 'cited_fact_ids' in item:
                    cited=item['cited_fact_ids']
                    if len(cited)==len(self.original_citations) and set(cited)==self.original_citations:
                        projected=[];pair_added=False
                        for ident in cited:
                            if ident in self.old_pair:
                                if not pair_added:projected.extend(self.case_pair);pair_added=True
                            else:projected.append(self.actual_spans.get(ident,ident))
                        result['cited_fact_ids']=projected
                return result
            if isinstance(item,list):return [walk(child) for child in item]
            if isinstance(item,str):
                item=item.replace(self.original_case,self.case_id)
                for old,new in self.claim_map.items():item=item.replace(old,new)
                for old,new in self.actual_spans.items():item=item.replace(old,new)
            return item
        return walk(deepcopy(value))


class Original6dddSingleTarotDenials(unittest.TestCase):
    def setUp(self):
        helpers.RecordedComparisonRepairs.setUp(self)
        self.evidence=json.loads(FIXTURE.read_text(encoding='utf8'))
        self.model=CaseBoundRecordedHttpModel(self.evidence,self.owner,self.case)
        self.service.model=self.model
        draw=self.service.tarot.create_draw(self.owner,subject_id='self',case_id=self.case,
            question=self.evidence['questions']['tarot'],spread_id='reflect3',draw_source='manual',
            manual_cards=self.evidence['fixed_cards'],idempotency_key='fixed-manual-draw')['draw']
        self.draw=self.service.tarot.reveal(self.owner,draw['id'])

    tearDown=helpers.RecordedComparisonRepairs.tearDown

    def original(self):
        self.run=self.service.submit(owner=self.owner,message=self.evidence['questions']['tarot'],
            request_id='fixed-target',conversation_id='synthetic-conversation',case_ids=[self.case],depth='standard',
            selection={'date':'2026-10-11','systems':['tarot']},draw_id=self.draw['id'])
        original_client=httpx.Client
        def fake_client(*args,**kwargs):
            kwargs['transport']=httpx.MockTransport(self.model.handler)
            return original_client(*args,**kwargs)
        with patch('mingjing_core.adapters.model.httpx.Client',side_effect=fake_client):
            result=self.service.execute(self.owner,self.run['id'])
        return self.repo.fetch_run(self.owner,self.run['id']),result

    def test_full_original_unsafe_draft_then_original_repair_four_calls_and_exact_replay(self):
        before=hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertEqual(self.evidence['source_commit'],'6ddd9196c1e0230e3207071e4f2f0e396734f557')
        self.assertEqual((self.evidence['sample']['status'],self.evidence['sample']['provider_calls']),('failed',4))
        current,result=self.original()
        self.assertEqual((current['status'],current['calls'],current['call_limit'],current['repair_used']),('succeeded',4,6,True))
        self.assertEqual(self.model.trace,['intake','specialist:tarot','synthesis','repair'])
        self.assertEqual(self.service.validation_attempts,[[helpers.GUARANTEE_ISSUE],[]])
        self.assertEqual(result['plain_summary'],self.model.outputs['repair']['plain_summary'])
        self.assertEqual(result['decision_options'],self.model.outputs['repair']['decision_options'])
        self.assertEqual(result['explanation'],self.model.outputs['repair']['explanation'])
        self.assertIn(helpers.GUARANTEE_ISSUE,self.service._validate(self.owner,current,self.model.outputs['synthesis']))
        self.assertEqual(self.service._validate(self.owner,current,self.model.outputs['repair']),[])
        calculation=self.service._record(self.owner,current['id'],'calculation')
        self.assertTrue(self.service.knowledge.revalidate_claims(calculation['calculation'],calculation['claims'],calculation['tarot_provenance'])['eligible'])
        self.assertEqual({c['system'] for c in calculation['claims']},{'tarot'})
        snapshot=self.service._snapshot(self.owner,current)
        self.assertTrue(set(result['cited_fact_ids'])<={f['id'] for f in snapshot['facts']})
        self.assertEqual(len(snapshot['current_source_facts']),2)
        self.assertEqual(len(self.service.memory.facts(self.owner)),9)
        self.assertEqual([r['write_status'] for r in result['memory_receipts']],['pending_confirmation','pending_confirmation'])
        self.assertEqual(len([e for e in result['evidence'] if e.get('context_only')]),2)
        self.assertFalse(any(k.startswith('fact:current_source_') for k in current['dependencies']))
        self.assertEqual(card_projection(self.service.tarot.get(self.owner,self.draw['id'])),self.evidence['fixed_cards'])
        replay=self.service.submit(owner=self.owner,message=self.evidence['questions']['tarot'],request_id='fixed-target',
            conversation_id='synthetic-conversation',case_ids=[self.case],depth='standard',
            selection={'date':'2026-10-11','systems':['tarot']},draw_id=self.draw['id'])
        self.assertEqual(replay['id'],current['id']);self.assertEqual(self.service.execute(self.owner,replay['id']),result)
        self.assertEqual(len(self.model.trace),4)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),before)

    def test_partial_or_unknown_opaque_case_pair_is_not_projected(self):
        current,_=self.original()
        for cited in ([next(iter(self.model.old_pair))],list(self.model.old_pair)+['fact_unknown-not-observed']):
            answer=deepcopy(self.model.original_outputs['repair']);answer['cited_fact_ids']=cited
            bound=self.model.bind(answer)
            self.assertEqual(bound['cited_fact_ids'],cited)
            self.assertIn('引用了本轮有效范围之外的事实',self.service._validate(self.owner,current,bound))

    def test_current_quote_ids_do_not_become_facts_of_the_next_round(self):
        _,result=self.original();temporary=set(self.model.actual_spans.values())
        next_model=providers.LocalAnswerModel('先核实真实班次与费用。')
        self.service.model=next_model
        run=self.service.submit(owner=self.owner,message='现在只核实现实费用，不排盘。',request_id='6ddd-next-round',case_ids=[self.case])
        next_result=self.service.execute(self.owner,run['id'])
        self.assertFalse(temporary&set(next_result['cited_fact_ids']))
        self.assertEqual(self.service._snapshot(self.owner,self.repo.fetch_run(self.owner,run['id']))['current_source_facts'],[])
        self.assertEqual(len(self.service.memory.facts(self.owner)),9)
        self.assertEqual(len(self.model.trace),4)


if __name__=='__main__':unittest.main()
