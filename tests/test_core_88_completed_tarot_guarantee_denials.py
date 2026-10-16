"""Sealed actual deep tarot contracts through PG, native charts and LangGraph.

Only model responses are replaced. Original fact IDs bind by known owner,
case, source and exact span; native claim IDs must reproduce as a set.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from mingjing_core.repositories.postgres import fingerprint
from tests import test_core_comparison_repairs as helpers
from tests import test_core_88_comparison_decision_denials as decisions
from tools.compare_core_providers import FACTS, PROFILE_ITEMS, card_projection


FIXTURE = Path(__file__).parent / 'fixtures' / '88_completed_comparison_tarot_guarantee_denials.json'
SAFE = ('不能把这些未知项当作零损失', '不能承诺该选项可逆或无损失')
SYSTEMS = ['tarot', 'bazi', 'ziwei', 'astro']
RUN_EVIDENCE = []


class RecordedDeep88TarotModel:
    def __init__(self, evidence, *, unsafe_review=False):
        self.evidence = evidence
        self.unsafe_review = unsafe_review
        self.raw = {c['purpose']: c['contract_output'] for c in evidence['sample']['calls']}
        self.mapping = {}; self.calls = []; self.outputs = {}
        owner = 'synthetic-comparison'
        cases = {p['case_id'] for p in self.raw['intake']['proposals']}
        assert len(cases) == 1 and None not in cases
        original_case = next(iter(cases))
        self.original_facts = {}
        for index, (kind, text) in enumerate(FACTS):
            source = 'msg_' + fingerprint([owner, 'web', 'fixed-fact-' + str(index), 'user'])[:32]
            old = 'fact_' + fingerprint([owner, source, 0, len(text), kind, original_case, None, None])[:32]
            self.original_facts[old] = {'kind': kind, 'content': text, 'case': True}
        for index, (field, value) in enumerate(PROFILE_ITEMS):
            text = '请保存 ' + field + '=' + str(value)
            source = 'msg_' + fingerprint([owner, 'web', 'fixed-profile-' + str(index), 'user'])[:32]
            old = 'fact_' + fingerprint([owner, source, 0, len(text), 'profile', None, field, value])[:32]
            self.original_facts[old] = {'field': field, 'value': value, 'case': False}
        source = 'msg_' + fingerprint([owner, 'web', 'fixed-target', 'user'])[:32]
        self.original_spans = {}
        question = evidence['questions']['tarot']
        for proposal in self.raw['intake']['proposals']:
            assert proposal['category'] == '背景' and proposal['field'] is None and proposal['value'] is None
            quote = proposal['quote']; start = question.index(quote); end = start + len(quote)
            old = 'current_source_' + fingerprint([owner, source, start, end, 'background', original_case, None, None])[:32]
            self.original_spans[old] = {'quote': quote, 'start': start, 'end': end}
        for output in self.raw.values():
            if 'cited_fact_ids' in output:
                assert set(output['cited_fact_ids']) == set(self.original_facts) | set(self.original_spans)

    def bind(self, value):
        if isinstance(value, dict): return {key: self.bind(item) for key, item in value.items()}
        if isinstance(value, list): return [self.bind(item) for item in value]
        if isinstance(value, str):
            for old, new in self.mapping.items(): value = value.replace(old, new)
        return value

    def generate(self, **kwargs):
        purpose = kwargs['purpose']; data = kwargs['payload']['reference_data']
        self.calls.append(purpose)
        for proposal in self.raw['intake']['proposals']:
            self.mapping[proposal['case_id']] = self.case_id
        if data.get('facts'):
            for old, fact in self.original_facts.items():
                if fact['case']:
                    matches = [f for f in data['facts'] if f.get('kind') == fact['kind']
                        and f.get('content') == fact['content'] and f.get('case_id') == self.case_id]
                else:
                    matches = [f for f in data['facts'] if f.get('field') == fact['field']
                        and f.get('value') == fact['value'] and f.get('case_id') is None]
                assert len(matches) == 1
                self.mapping[old] = matches[0]['id']
            for old, span in self.original_spans.items():
                matches = [f for f in data['facts'] if f.get('context_only')
                    and f.get('kind') == 'background' and f.get('content') == span['quote']
                    and f.get('case_id') == self.case_id and any(
                        ref['message_id'] == self.program_source_id
                        and ref['start'] == span['start'] and ref['end'] == span['end']
                        for ref in f['source_refs'])]
                assert len(matches) == 1
                self.mapping[old] = matches[0]['id']
        if purpose.startswith('specialist:'):
            system = purpose.split(':')[1]
            actual = [c for c in data['claims'] if c['system'] == system]
            old_ids = self.raw[purpose]['claim_ids']
            if system == 'tarot':
                assert len(old_ids) == len(actual) == 1
                assert actual[0]['rule_id'] == 'tarot.editorial.complete-deck.v1'
                assert actual[0]['time_scale'] == 'question'
                self.mapping[old_ids[0]] = actual[0]['claim_id']
            else:
                assert set(old_ids) == {c['claim_id'] for c in actual}
        output = self.bind(deepcopy(self.raw[purpose]))
        if purpose == 'review' and self.unsafe_review:
            output['plain_summary'] += '现在付款完全可逆。'
        self.outputs[purpose] = deepcopy(output)
        return {'output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1},
                'model': 'synthetic-original-88-completed-deep-tarot'}


class Actual88CompletedTarotGuaranteeDenials(unittest.TestCase):
    def setUp(self):
        helpers.RecordedComparisonRepairs.setUp(self)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.fixture_sha = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertTrue(self.evidence['source_verified_start'])
        self.assertTrue(self.evidence['source_verified_end'])
        self.assertEqual(self.evidence['source_commit'], '88f30cc113ab2fba203a77576eb633e2655ae6b8')
        sample = self.evidence['sample']
        self.assertEqual((sample['status'], sample['provider_calls'], sample['call_limit']), ('failed', 8, 10))
        self.assertEqual([a['issues'] for a in sample['validation_attempts']],
            [[helpers.GUARANTEE_ISSUE], [helpers.GUARANTEE_ISSUE]])

    tearDown = helpers.RecordedComparisonRepairs.tearDown

    def execute(self, operation, *, unsafe_review=False):
        self.model = RecordedDeep88TarotModel(self.evidence, unsafe_review=unsafe_review)
        self.model.case_id = self.case
        self.model.program_source_id = 'msg_' + fingerprint([self.owner, 'web', operation, 'user'])[:32]
        self.service.model = self.model
        self.draw = self.service.tarot.create_draw(self.owner, subject_id='self', case_id=self.case,
            question=self.evidence['questions']['tarot'], spread_id='reflect3', draw_source='manual',
            manual_cards=self.evidence['fixed_cards'], idempotency_key='fixed-manual-draw')['draw']
        self.draw = self.service.tarot.reveal(self.owner, self.draw['id'])
        facts = self.service.memory.facts(self.owner)
        run = self.service.submit(owner=self.owner, message=self.evidence['questions']['tarot'],
            conversation_id='synthetic-conversation', request_id=operation, case_ids=[self.case], depth='deep',
            selection={'date': '2026-10-11', 'systems': SYSTEMS}, draw_id=self.draw['id'])
        try:
            result = self.service.execute(self.owner, run['id'])
        finally:
            current = self.repo.fetch_run(self.owner, run['id'])
            RUN_EVIDENCE.append({'operation': operation, 'status': current['status'], 'calls': current['calls'],
                'limit': current['call_limit'], 'repair_used': current['repair_used'],
                'validation_attempts': deepcopy(self.service.validation_attempts), 'provider_purposes': self.model.calls})
        count = 8 if unsafe_review else 7
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']),
            ('succeeded', count, 10, unsafe_review))
        self.assertEqual(self.model.calls, ['intake'] + ['specialist:' + s for s in SYSTEMS]
            + ['synthesis', 'review'] + (['repair'] if unsafe_review else []))
        self.assertEqual(self.service.validation_attempts, [[helpers.GUARANTEE_ISSUE], []] if unsafe_review else [[]])
        self.assertEqual(self.service._record(self.owner, current['id'], 'validation')['final'],
            self.model.outputs['repair' if unsafe_review else 'review'])
        for key, value in self.model.outputs['repair' if unsafe_review else 'review'].items():
            # Commit adds verified rule details to the expandable appendix;
            # the durable validated model contract above remains exact.
            if key == 'professional_appendix': self.assertTrue(result[key].startswith(value))
            else: self.assertEqual(result[key], value)
        self.assertEqual(self.service.memory.facts(self.owner), facts)
        calculation = self.service._record(self.owner, current['id'], 'calculation')
        self.assertEqual({c['system'] for c in calculation['claims']}, set(SYSTEMS))
        self.assertTrue(self.service.knowledge.revalidate_claims(calculation['calculation'], calculation['claims'],
            calculation.get('tarot_provenance'))['eligible'])
        snapshot = self.service._snapshot(self.owner, current)
        self.assertTrue(set(result['cited_fact_ids']) <= {f['id'] for f in snapshot['facts']})
        self.assertTrue(set(result['cited_claim_ids']) <= {c['claim_id'] for c in calculation['claims']})
        self.assertEqual(card_projection(self.service.tarot.get(self.owner, self.draw['id'])), self.evidence['fixed_cards'])
        replay = self.service.submit(owner=self.owner, message=self.evidence['questions']['tarot'],
            conversation_id='synthetic-conversation', request_id=operation, case_ids=[self.case], depth='deep',
            selection={'date': '2026-10-11', 'systems': SYSTEMS}, draw_id=self.draw['id'])
        self.assertEqual(replay['id'], current['id'])
        self.assertEqual(self.service.execute(self.owner, current['id']), result)
        self.assertEqual(len(self.model.calls), count)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), self.fixture_sha)
        return current

    def test_complete_actual_review_commits_without_repair_and_all_original_finals_validate(self):
        current = self.execute('88-completed-tarot')
        for phase in ('synthesis', 'review', 'repair'):
            original = self.model.bind(self.model.raw[phase])
            self.assertEqual(self.service._validate(self.owner, current, original), [])

    def test_new_affirmative_review_requires_one_repair_and_original_repair_commits(self):
        self.execute('88-completed-tarot-forced-repair', unsafe_review=True)


class Finite88CompletedTarotGuaranteeDenials(unittest.TestCase):
    setUp = decisions.Recorded88ComparisonDecisionDenials.setUp
    tearDown = decisions.Recorded88ComparisonDecisionDenials.tearDown
    consult = decisions.Recorded88ComparisonDecisionDenials.consult
    execute = decisions.Recorded88ComparisonDecisionDenials.execute

    def test_two_observed_closed_denials_commit_without_repair(self):
        for index, passage in enumerate(SAFE):
            with self.subTest(passage=passage):
                self.execute('88-tarot-finite-safe-' + str(index), patch={'plain_summary': passage + '。'})

    def test_affirmatives_quotes_double_denials_and_renewed_promises_stay_rejected(self):
        for index, passage in enumerate(SAFE):
            mutations = ('不是' + passage, '不能说' + passage, '“' + passage + '”',
                '此前称“情况未知；' + passage + '。之后再决定”', '不能说：' + passage,
                passage + '，但报名完全可逆', passage + '。付款无损失', passage + '并保证报名无损失')
            for mutation_index, mutation in enumerate(mutations):
                with self.subTest(mutation=mutation):
                    self.execute('88-tarot-unsafe-' + str(index) + '-' + str(mutation_index),
                        patch={'plain_summary': mutation + '。'}, invalid=True)

    def test_new_objects_verbs_and_cross_fields_stay_rejected(self):
        passages = ('可以把这些未知项当作零损失', '承诺该选项可逆或无损失',
            '不能把这些未知项当作保证零损失', '不能把其他未知项当作零损失',
            '不能承诺该安排可逆或无损失', '不能承诺该选项可逆或保证无损失')
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                self.execute('88-tarot-boundary-' + str(index), patch={'plain_summary': passage + '。'}, invalid=True)
        for index, passage in enumerate(SAFE):
            with self.subTest(passage=passage):
                self.execute('88-tarot-cross-field-' + str(index), patch={'plain_summary': passage + '。',
                    'professional_appendix': '报名完全可逆，付款无损失。'}, invalid=True)


if __name__ == '__main__': unittest.main()
