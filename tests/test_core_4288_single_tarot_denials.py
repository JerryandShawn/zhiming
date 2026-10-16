"""Original frozen Tarot contracts through real PG, LangGraph and card service."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unittest

from mingjing_core.domain.consultation import InvalidAnswer
from mingjing_core.runtime import LangGraphRuntime
from tests import test_core_comparison_repairs as helpers
from tests.test_core_035_comparison_tarot_denials import original_profile_ids
from tools.compare_core_providers import FACTS, card_projection

FIXTURE = Path(__file__).parent / 'fixtures/4288_single_tarot_denials.json'
RUN_EVIDENCE = []
SAFE = ('不能当作零风险或完全可逆', '不能推断为零风险、免费或完全可逆',
        '不能从牌面推断为零风险或可忽略')


class RecordedTarotModel:
    def __init__(self, evidence, owner, case):
        self.evidence = evidence
        self.owner = owner
        self.case = case
        self.raw = {call['purpose']: call['contract_output'] for call in evidence['sample']['calls']}
        assert not self.raw['intake']['proposals']
        self.mapping = {}
        self.calls = []
        self.outputs = {}
        self.first = 'synthesis'
        self.patch = None
        self.force_repair = False
        prose = self.raw['synthesis']['explanation']
        self.old_facts = [re.search(pattern, prose).group(1) for pattern in (
            r'硬约束"我不能上夜班"（(fact_[a-f0-9]+)）',
            r'偏好先核实班次、费用和退出条件（(fact_[a-f0-9]+)）')]
        cited = set(self.raw['synthesis']['cited_fact_ids'])
        assert cited == set(self.old_facts) | original_profile_ids(owner)

    def bind(self, value):
        if isinstance(value, dict): return {key: self.bind(item) for key, item in value.items()}
        if isinstance(value, list): return [self.bind(item) for item in value]
        if isinstance(value, str):
            for old, new in self.mapping.items(): value = value.replace(old, new)
        return value

    def generate(self, **kwargs):
        purpose = kwargs['purpose']
        data = kwargs['payload']['reference_data']
        self.calls.append(purpose)
        if data.get('facts'):
            for old, (kind, content) in zip(self.old_facts, FACTS):
                matched = [fact for fact in data['facts'] if fact['kind'] == kind and
                    fact['content'] == content and fact.get('case_id') == self.case and not fact.get('context_only')]
                assert len(matched) == 1
                self.mapping[old] = matched[0]['id']
            assert original_profile_ids(self.owner) <= {fact['id'] for fact in data['facts']}
        if purpose == 'specialist:tarot':
            claim = data['claims'][0]
            assert len(data['claims']) == len(self.raw[purpose]['claim_ids']) == 1
            assert claim['system'] == 'tarot' and claim['rule_id'] == 'tarot.editorial.complete-deck.v1'
            self.mapping[self.raw[purpose]['claim_ids'][0]] = claim['claim_id']
        phase = self.first if purpose == 'synthesis' else purpose
        output = self.bind(deepcopy(self.raw[phase]))
        if self.patch is not None and purpose in ('synthesis', 'repair'):
            output.update(plain_summary='', explanation='', professional_appendix='', caveats=[],
                actions=['核实班次、费用与退出条款'], follow_up='', decision_options=[])
            output.update(deepcopy(self.patch))
        if self.force_repair and purpose == 'synthesis': output['plain_summary'] += '现在报名零风险。'
        self.outputs[purpose] = deepcopy(output)
        return {'output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1}, 'model': 'fixture-4288-tarot'}


class Recorded4288SingleTarotDenials(unittest.TestCase):
    def setUp(self):
        helpers.RecordedComparisonRepairs.setUp(self)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.fixture_hash = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.model = RecordedTarotModel(self.evidence, self.owner, self.case)
        self.service.model = self.model
        self.assertIsInstance(self.service.runtime, LangGraphRuntime)
        draw = self.service.tarot.create_draw(self.owner, subject_id='self', case_id=self.case,
            question=self.evidence['questions']['tarot'], spread_id='reflect3', draw_source='manual',
            manual_cards=self.evidence['fixed_cards'], idempotency_key='fixed-manual-draw')['draw']
        self.draw = self.service.tarot.reveal(self.owner, draw['id'])

    tearDown = helpers.RecordedComparisonRepairs.tearDown

    def execute(self, operation, *, first='synthesis', force_repair=False, patch=None, unsafe=False, message=None):
        self.model.first = first
        self.model.force_repair = force_repair
        self.model.patch = patch
        before = len(self.model.calls)
        attempt = len(self.service.validation_attempts)
        question = message or self.evidence['questions']['tarot']
        run = self.service.submit(owner=self.owner, message=question,
            conversation_id='synthetic-conversation', request_id=operation, case_ids=[self.case], depth='standard',
            selection={'date': '2026-10-11', 'systems': ['tarot']}, draw_id=self.draw['id'])
        try:
            if unsafe:
                with self.assertRaises(InvalidAnswer) as caught: self.service.execute(self.owner, run['id'])
                self.assertEqual(caught.exception.code, 'REFERENCE_ERROR')
                result = None
            else:
                result = self.service.execute(self.owner, run['id'])
            current = self.repo.fetch_run(self.owner, run['id'])
            repaired = unsafe or force_repair
            calls = 4 if repaired else 3
            self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']),
                ('failed' if unsafe else 'succeeded', calls, 6, repaired))
            self.assertEqual(self.model.calls[before:], ['intake', 'specialist:tarot', 'synthesis'] + (['repair'] if repaired else []))
            if unsafe:
                self.assertEqual(len(self.service.validation_attempts[attempt:]), 2)
                for issues in self.service.validation_attempts[attempt:]: self.assertIn(helpers.GUARANTEE_ISSUE, issues)
            else:
                self.assertEqual(self.service.validation_attempts[attempt:],
                    [[helpers.GUARANTEE_ISSUE], []] if force_repair else [[]])
            self.assertEqual(card_projection(self.service.tarot.get(self.owner, self.draw['id'])), self.evidence['fixed_cards'])
            if unsafe: self.assertIsNone(current['result'])
            else:
                self.assertTrue(result['validation']['valid'])
                calculation = self.service._record(self.owner, current['id'], 'calculation')
                self.assertTrue(self.service.knowledge.revalidate_claims(calculation['calculation'],
                    calculation['claims'], calculation['tarot_provenance'])['eligible'])
                snapshot = self.service._snapshot(self.owner, current)
                self.assertTrue(set(result['cited_fact_ids']) <= {fact['id'] for fact in snapshot['facts']})
                replay = self.service.submit(owner=self.owner, message=question,
                    conversation_id='synthetic-conversation', request_id=operation, case_ids=[self.case], depth='standard',
                    selection={'date': '2026-10-11', 'systems': ['tarot']}, draw_id=self.draw['id'])
                self.assertEqual(replay['id'], run['id'])
                self.assertEqual(self.service.execute(self.owner, replay['id']), result)
                self.assertEqual(len(self.model.calls) - before, calls)
            return result
        finally:
            current = self.repo.fetch_run(self.owner, run['id'])
            RUN_EVIDENCE.append({'operation': operation, 'run_id': run['id'], 'status': current['status'],
                'calls': current['calls'], 'limit': current['call_limit'], 'repair_used': current['repair_used'],
                'model_calls': self.model.calls[before:], 'validation_attempts': self.service.validation_attempts[attempt:],
                'fixed_cards_unchanged': card_projection(self.service.tarot.get(self.owner, self.draw['id'])) == self.evidence['fixed_cards'],
                'fixture_sha256': self.fixture_hash, 'runtime': 'LangGraphRuntime'})
            self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), self.fixture_hash)

    def test_complete_original_and_repair_validate_without_false_repair(self):
        self.assertEqual([attempt['issues'] for attempt in self.evidence['sample']['validation_attempts']],
            [[helpers.GUARANTEE_ISSUE], [helpers.GUARANTEE_ISSUE]])
        for phase in ('synthesis', 'repair'):
            with self.subTest(phase=phase):
                result = self.execute('original-' + phase, first=phase)
                expected = self.model.bind(self.model.raw[phase])
                for key in ('plain_summary', 'explanation', 'actions', 'decision_options', 'follow_up'):
                    self.assertEqual(result[key], expected[key])
                self.assertEqual(result['caveats'], expected.get('caveats', []))
                self.assertIn(expected['professional_appendix'], result['professional_appendix'])
                self.assertEqual(len(self.service.memory.facts(self.owner)), 9)

    def test_true_guarantee_uses_one_original_complete_repair_then_replay(self):
        result = self.execute('forced-original-repair', force_repair=True)
        self.assertEqual(result['plain_summary'], self.model.bind(self.model.raw['repair']['plain_summary']))
        self.assertEqual(result['explanation'], self.model.bind(self.model.raw['repair']['explanation']))

    def test_finite_local_lists_and_non_guarantee_tail(self):
        for index, passage in enumerate(SAFE):
            with self.subTest(passage=passage): self.execute('finite-' + str(index), patch={'plain_summary': passage + '。'})

    def test_quotes_double_denials_new_predicates_and_cross_fields_stay_rejected(self):
        patches = []
        for passage in SAFE:
            patches += [{'plain_summary': prefix + passage + '。'} for prefix in ('不是', '不能说', '并非')]
            patches += [{'plain_summary': quoted} for quoted in ('材料称“' + passage + '”。',
                '材料称“情况未知，' + passage + '”。', '材料称“情况未知；' + passage + '，须核实”。',
                '不是“情况未知。' + passage + '，须核实”。')]
            patches += [{'plain_summary': passage + '，但现在报名完全可逆。'},
                {'plain_summary': passage + '，现在报名零风险。'},
                {'plain_summary': passage + '或保证报名无损失。'},
                {'plain_summary': passage + '。', 'professional_appendix': '报名无损失。'}]
            patches += [{'plain_summary': '不能说：' + passage + '。'}]
        patches += [{'plain_summary': passage + '。'} for passage in ('推断为零风险、免费或完全可逆',
            '当作零风险或完全可逆', '不能推断为零风险、保证免费或完全可逆',
            '不能推断为零风险或忽略费用完全可逆', '不能从牌面推断为零风险或可以报名完全可逆')]
        for index, patch in enumerate(patches):
            with self.subTest(patch=patch): self.execute('unsafe-' + str(index), patch=patch, unsafe=True)

    def test_negative_saved_and_current_source_cannot_authorize_positive_guarantee(self):
        self.execute('negative-current-source', patch={'plain_summary': '现在报名零风险，报名完全可逆。'}, unsafe=True,
            message=self.evidence['questions']['tarot'] + '不能推断为零风险、免费或完全可逆。')
        text = '请记住：不能推断为零风险、免费或完全可逆。'
        source = self.service.memory.receive(self.owner, content=text, source_id='saved-negative', case_ids=[self.case])
        receipt = self.service.memory.save_fact(self.owner, 'self', source['id'],
            '不能推断为零风险、免费或完全可逆', 'constraint', case_id=self.case)
        self.assertEqual(receipt['write_status'], 'saved')
        self.execute('negative-saved-source', patch={'plain_summary': '现在报名零风险，报名完全可逆。'}, unsafe=True)
        self.execute('quoted-negative-current-source', patch={'plain_summary': '现在报名零风险，报名完全可逆。'}, unsafe=True,
            message=self.evidence['questions']['tarot'] + '材料称“情况未知；不能推断为零风险、免费或完全可逆，须核实”。')


if __name__ == '__main__': unittest.main()
