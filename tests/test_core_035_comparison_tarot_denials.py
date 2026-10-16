"""Immutable synthetic contracts through PG/Card/LangGraph and native charts.

Only HTTP model responses are substituted. Two old case citations lack their
random case identity: the complete two-element set is projected as a set only.
No single opaque case fact ID is assigned a meaning or resolved by array order.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.domain.consultation import InvalidAnswer
from mingjing_core.repositories.postgres import fingerprint
from tests import test_core_comparison_repairs as helpers
from tests import test_core_76b_provider_denials as providers
from tools.compare_core_providers import FACTS, PROFILE_ITEMS, card_projection, execute_core_with_recovery

FIXTURES = Path(__file__).parent / 'fixtures'
SYMBOLIC = '象征解释被提升为现实确定性或概率'


def original_profile_ids(owner):
    result = set()
    for index, (field, value) in enumerate(PROFILE_ITEMS):
        text = '请保存 ' + field + '=' + str(value)
        source = 'msg_' + fingerprint([owner, 'web', 'fixed-profile-' + str(index), 'user'])[:32]
        result.add('fact_' + fingerprint([owner, source, 0, len(text), 'profile', None, field, value])[:32])
    return result


class RecordedHttpModel(ConfiguredModel):
    """Actual provider parser with recorded tool payloads and a fake HTTP peer."""
    def __init__(self, evidence, owner, *, unsafe_review=False, invalid_fact=None, natural_ids=False):
        super().__init__(key='synthetic-test-key', base='https://synthetic.invalid/v1', model='synthetic-recorded-k3')
        self.evidence = evidence; self.owner = owner
        self.records = evidence['sample']['calls']
        self.original_outputs = {c['purpose']: c['contract_output'] for c in self.records if c.get('contract_output')}
        self.trace = []; self.outputs = {}; self.claim_map = {}; self.span_map = {}
        self.unsafe_review = unsafe_review; self.invalid_fact = invalid_fact; self.natural_ids = natural_ids
        self.failed_astro = False; self.reference_data = None; self.purpose = None
        source = 'msg_' + fingerprint([owner, 'web', 'fixed-target', 'user'])[:32]
        question = evidence['questions']['tarot']
        for proposal in self.original_outputs['intake']['proposals']:
            assert proposal.get('field') is None and proposal.get('value') is None and proposal.get('case_id') is None
            quote = proposal['quote']; start = question.index(quote); end = start + len(quote)
            kind = {'背景':'background'}[proposal['category']]
            old = 'fact_' + fingerprint([owner, source, start, end, kind, None, None, None])[:32]
            self.span_map[old] = {'quote':quote, 'kind':kind, 'start':start, 'end':end, 'message_id':source}
        citation_sets = {frozenset(o['cited_fact_ids']) for o in self.original_outputs.values() if 'cited_fact_ids' in o}
        assert len(citation_sets) == 1
        self.original_citations = next(iter(citation_sets))
        self.old_pair = self.original_citations - set(self.span_map)
        assert len(self.old_pair) == 2 and not self.old_pair & original_profile_ids(owner)
        # The source program seeds exactly this known pair before seven profile
        # facts; original validation had no out-of-scope-reference issue.
        assert evidence['sample']['validation_attempts']
        assert all('引用了本轮有效范围之外的事实' not in a['issues'] for a in evidence['sample']['validation_attempts'])
        for output in self.original_outputs.values():
            body = json.dumps({k:v for k,v in output.items() if k != 'cited_fact_ids'}, ensure_ascii=False)
            assert all(old not in body for old in self.old_pair)

    def _bindings(self, data):
        if not data.get('facts'): return
        self.reference_data = data
        self.case_pair = []
        for kind, content in FACTS:
            matches = [f for f in data['facts'] if f['kind'] == kind and f['content'] == content and
                       f.get('case_id') == self.case_id and not f.get('context_only')]
            assert len(matches) == 1
            self.case_pair.append(matches[0]['id'])
        self.actual_spans = {}
        for old, span in self.span_map.items():
            matches = [f for f in data['facts'] if f.get('context_only') and f['kind'] == span['kind'] and
                       f['content'] == span['quote'] and f.get('case_id') is None and any(
                       all(ref.get(key) == (self.program_source_id if key == 'message_id' else span[key]) for key in ('start', 'end', 'message_id'))
                       for ref in f['source_refs'])]
            assert len(matches) == 1, 'Only the exact original proposal span can bind a current-source ID'
            self.actual_spans[old] = matches[0]['id']

    def bind(self, value):
        def walk(item):
            if isinstance(item, dict):
                result = {key:walk(child) for key,child in item.items()}
                if 'cited_fact_ids' in item:
                    cited = item['cited_fact_ids']
                    # No partial/unknown citation set receives this projection.
                    if self.natural_ids:
                        result['cited_fact_ids'] = list(self.case_pair) + list(self.actual_spans.values())
                    elif len(cited) == len(self.original_citations) and set(cited) == self.original_citations:
                        result['cited_fact_ids'] = list(self.case_pair) + list(self.actual_spans.values())
                return result
            if isinstance(item,list): return [walk(child) for child in item]
            if isinstance(item,str):
                for old,new in self.claim_map.items(): item = item.replace(old,new)
            return item
        return walk(deepcopy(value))

    def handler(self, request):
        body = json.loads(request.content)
        payload = json.loads(body['messages'][0]['content'][0]['text'])
        data = payload['reference_data']; purpose = self.purpose
        self._bindings(data)
        records = [r for r in self.records if r['purpose'] == purpose]
        self.trace.append(purpose)
        if purpose == 'specialist:astro' and any(r.get('reason') == 'tool_count' for r in records) and not self.failed_astro:
            self.failed_astro = True
            failed = next(r for r in records if r.get('reason') == 'tool_count')
            return httpx.Response(200,json={'content':[],'stop_reason':'end_turn','usage':failed['usage']})
        record = next(r for r in records if r.get('contract_output'))
        if purpose.startswith('specialist:'):
            system = purpose.split(':')[1]; old_ids = set(record['contract_output']['claim_ids'])
            actual = [c for c in data['claims'] if c['system'] == system]
            if system == 'tarot':
                assert len(old_ids) == len(actual) == 1
                assert actual[0]['rule_id'] == 'tarot.editorial.complete-deck.v1' and actual[0]['time_scale'] == 'question'
                assert card_projection(payload['reference_data']['tarot_draw']) == self.evidence['fixed_cards'] if 'tarot_draw' in payload['reference_data'] else True
                self.claim_map[next(iter(old_ids))] = actual[0]['claim_id']
            else:
                # Six original native IDs reproduce exactly, including two
                # Astro rules whose source citation order differs from registry.
                assert old_ids == {c['claim_id'] for c in actual}
        output = self.bind(record['contract_output'])
        if purpose == 'review' and self.unsafe_review:
            output['plain_summary'] += '现在付款完全可逆。'
        if purpose in ('synthesis','review','repair') and self.invalid_fact:
            output['cited_fact_ids'].append(self.invalid_fact)
        self.outputs[purpose] = deepcopy(output)
        return httpx.Response(200,json={'content':[{'type':'tool_use','name':'submit','input':output}],
                                      'stop_reason':'tool_use','usage':record['usage']})

    def generate(self, **kwargs):
        self.purpose = kwargs['purpose']
        return super().generate(**kwargs)


class Original035ComparisonTarotDenials(unittest.TestCase):
    def setUp(self):
        helpers.RecordedComparisonRepairs.setUp(self)
        self.evidence = None; self.draw = None; self.model = None

    tearDown = helpers.RecordedComparisonRepairs.tearDown

    def execute(self, deep=False, *, unsafe_review=False, invalid_fact=None, natural_ids=False, request_mode='chat'):
        name = '035_second_comparison_' + ('deep' if deep else 'single') + '_tarot_denials.json'
        self.fixture = FIXTURES / name; self.original_sha = hashlib.sha256(self.fixture.read_bytes()).hexdigest()
        self.evidence = json.loads(self.fixture.read_text(encoding='utf-8'))
        self.model = RecordedHttpModel(self.evidence,self.owner,unsafe_review=unsafe_review,
                                       invalid_fact=invalid_fact,natural_ids=natural_ids)
        self.model.case_id = self.case
        self.model.program_source_id = 'msg_' + fingerprint([self.owner,'web' if request_mode=='chat' else request_mode,'fixed-target','user'])[:32]
        self.service.model = self.model
        self.draw = self.service.tarot.create_draw(self.owner,subject_id='self',case_id=self.case,
            question=self.evidence['questions']['tarot'],spread_id='reflect3',draw_source='manual',
            manual_cards=self.evidence['fixed_cards'],idempotency_key='fixed-manual-draw')['draw']
        self.draw = self.service.tarot.reveal(self.owner,self.draw['id'])
        self.run = self.service.submit(owner=self.owner,message=self.evidence['questions']['tarot'],
            request_id='fixed-target',conversation_id='synthetic-conversation',case_ids=[self.case],
            mode=request_mode,depth='deep' if deep else 'standard',selection={'date':'2026-10-11',
            'systems':['tarot','bazi','ziwei','astro'] if deep else ['tarot']},draw_id=self.draw['id'])
        self.attempts = []
        original_client = httpx.Client
        def fake_client(*args, **kwargs):
            kwargs['transport'] = httpx.MockTransport(self.model.handler)
            return original_client(*args,**kwargs)
        chart_python = os.environ.get('CHART_PYTHON') or str(Path(__file__).resolve().parents[2] / 'chart311-venv/Scripts/python.exe')
        with patch.dict(os.environ,{'CHART_PYTHON':chart_python}), \
             patch('mingjing_core.adapters.model.httpx.Client',side_effect=fake_client):
            self.result = execute_core_with_recovery(self.service,self.owner,self.run['id'],None,self.attempts)
        return self.repo.fetch_run(self.owner,self.run['id'])

    def assert_references_and_replay(self, current, expected_calls):
        calculation = self.service._record(self.owner,current['id'],'calculation')
        self.assertTrue(self.service.knowledge.revalidate_claims(calculation['calculation'],calculation['claims'],
                        calculation.get('tarot_provenance'))['eligible'])
        self.assertEqual(len(self.service.memory.facts(self.owner)),9)
        self.assertTrue(set(self.result['cited_fact_ids']) <= {f['id'] for f in self.service._snapshot(self.owner,current)['facts']})
        self.assertTrue(set(self.result['cited_claim_ids']) <= {c['claim_id'] for c in calculation['claims']})
        self.assertEqual(card_projection(self.service.tarot.get(self.owner,self.draw['id'])),self.evidence['fixed_cards'])
        replay = self.service.submit(owner=self.owner,message=self.evidence['questions']['tarot'],
            request_id='fixed-target',conversation_id='synthetic-conversation',case_ids=[self.case],
            depth=current['request']['depth'],selection=current['request']['selection'],draw_id=self.draw['id'])
        self.assertEqual(replay['id'],current['id']); self.assertEqual(self.service.execute(self.owner,current['id']),self.result)
        self.assertEqual(len(self.model.trace),expected_calls)
        self.assertEqual(hashlib.sha256(self.fixture.read_bytes()).hexdigest(),self.original_sha)
        return calculation

    def test_single_full_original_true_guarantee_uses_unique_repair_four_calls(self):
        current = self.execute()
        self.assertEqual((current['status'],current['calls'],current['repair_used']),('succeeded',4,True))
        self.assertEqual(self.model.trace,['intake','specialist:tarot','synthesis','repair'])
        self.assertEqual(self.service.validation_attempts,[[helpers.GUARANTEE_ISSUE],[]])
        self.assertEqual(self.result['plain_summary'],self.model.outputs['repair']['plain_summary'])
        self.assertEqual(len(self.result['memory_receipts']),2)
        self.assertTrue(all(r['write_status']=='pending_confirmation' for r in self.result['memory_receipts']))
        source_evidence = [e for e in self.result['evidence'] if e.get('context_only')]
        self.assertEqual(len(source_evidence),2)
        self.assertTrue(all(e['source']=='current_user_statement_not_saved' for e in source_evidence))
        self.assertTrue(all('message:'+ref['message_id'] in current['dependencies'] for e in source_evidence for ref in e['source_refs']))
        self.assertFalse(any(key.startswith('fact:current_source_') for key in current['dependencies']))
        self.assert_references_and_replay(current,4)

    def test_single_naturally_generated_current_ids_are_valid_end_to_end(self):
        current = self.execute(natural_ids=True)
        self.assertEqual((current['status'],current['calls']),('succeeded',4))
        self.assertEqual(set(self.result['cited_fact_ids']),set(self.model.case_pair+list(self.model.actual_spans.values())))
        self.assert_references_and_replay(current,4)
        temporary_ids = set(self.model.actual_spans.values())
        self.service.model = providers.LocalAnswerModel('先核实书面班次与费用。')
        next_run = self.service.submit(owner=self.owner,message='现在仅核对费用，原话背景不保存。',
            request_id='035-next-round',case_ids=[self.case])
        next_result = self.service.execute(self.owner,next_run['id'])
        next_snapshot = self.service._snapshot(self.owner,self.repo.fetch_run(self.owner,next_run['id']))
        self.assertEqual(next_snapshot.get('current_source_facts'),[])
        self.assertFalse(temporary_ids & set(next_result['cited_fact_ids']))
        other_case = self.service.memory.create_case(self.owner,'self','合成独立事项')['id']
        other_run = self.service.submit(owner=self.owner,message='只讨论这一独立事项的现实条件。',
            request_id='035-independent-case',case_ids=[other_case])
        other_result = self.service.execute(self.owner,other_run['id'])
        other_snapshot = self.service._snapshot(self.owner,self.repo.fetch_run(self.owner,other_run['id']))
        self.assertEqual(other_snapshot.get('current_source_facts'),[])
        self.assertFalse(temporary_ids & set(other_result['cited_fact_ids']))
        self.assertEqual(len(self.service.memory.facts(self.owner)),9)

    def test_website_tarot_mode_accepts_current_original_background_without_long_save(self):
        current = self.execute(natural_ids=True,request_mode='tarot')
        self.assertEqual((current['status'],current['calls']),('succeeded',4))
        self.assertEqual(len(self.service.memory.facts(self.owner)),9)
        snapshot = self.service._snapshot(self.owner,current)
        self.assertEqual(len(snapshot['current_source_facts']),2)
        source_id = self.service._record(self.owner,current['id'],'intake')['source_id']
        source = self.service.memory.get_source(self.owner,source_id)
        self.assertEqual((source['channel'],source['policy']['origin'],source['policy']['run_context']),('tarot','current_user',True))
        self.assertTrue(set(self.model.actual_spans.values()) <= set(self.result['cited_fact_ids']))
        self.assertTrue(all(r['write_status']=='pending_confirmation' for r in self.result['memory_receipts']))

    def test_deep_original_denials_naturally_commit_eight_attempts_without_semantic_repair(self):
        current = self.execute(deep=True)
        self.assertEqual((current['status'],current['calls'],current['call_limit'],current['repair_used']),('succeeded',8,10,False))
        self.assertEqual(self.model.trace,['intake','specialist:tarot','specialist:bazi','specialist:ziwei',
                                          'specialist:astro','specialist:astro','synthesis','review'])
        self.assertEqual([a['calls'] for a in self.attempts],[5,8])
        self.assertEqual(len({a['run_id'] for a in self.attempts}),1)
        self.assertEqual({a['operation_id'] for a in self.attempts},{'fixed-target'})
        self.assertEqual(self.attempts[0]['failure_code'],'MODEL_TOOL_COUNT')
        self.assertEqual(self.service.validation_attempts,[[]])
        calculation = self.assert_references_and_replay(current,8)
        self.assertEqual({c['system'] for c in calculation['claims']},{'bazi','ziwei','astro','tarot'})
        self.assertEqual(len([c for c in calculation['claims'] if c['system']!='tarot']),6)
        self.assertEqual(self.service._validate(self.owner,current,self.model.bind(self.model.original_outputs['repair'])),[])

    def test_deep_new_unsafe_review_uses_one_repair_and_cumulative_nine_attempts(self):
        current = self.execute(deep=True,unsafe_review=True)
        self.assertEqual((current['status'],current['calls'],current['call_limit'],current['repair_used']),('succeeded',9,10,True))
        self.assertEqual([a['calls'] for a in self.attempts],[5,9])
        self.assertEqual(self.model.trace.count('specialist:astro'),2)
        self.assertEqual(self.model.trace.count('repair'),1)
        self.assertEqual(self.service.validation_attempts,[[helpers.GUARANTEE_ISSUE],[]])
        self.assert_references_and_replay(current,9)

    def test_partial_or_unknown_opaque_citation_sets_are_never_projected(self):
        current = self.execute()
        for citations in ([next(iter(self.model.old_pair))],list(self.model.old_pair)+['fact_unknown-original']):
            answer = deepcopy(self.model.original_outputs['repair']); answer['cited_fact_ids']=citations
            bound = self.model.bind(answer)
            self.assertEqual(bound['cited_fact_ids'],citations)
            self.assertIn('引用了本轮有效范围之外的事实',self.service._validate(self.owner,current,bound))

    def test_new_unknown_citation_remains_rejected_by_real_business(self):
        with self.assertRaises(InvalidAnswer): self.execute(invalid_fact='current_source_unknown_not_supplied')
        current = self.repo.fetch_run(self.owner,self.run['id'])
        self.assertEqual((current['status'],current['calls'],current['repair_used']),('failed',4,True))
        self.assertIsNone(current['result'])
        self.assertIn('引用了本轮有效范围之外的事实',self.service.validation_attempts[-1])
        self.assertEqual(len(self.service.memory.facts(self.owner)),9)


if __name__ == '__main__': unittest.main()
