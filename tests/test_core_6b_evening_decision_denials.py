"""Complete evening repair contracts through actual PostgreSQL/Core/runtime.

Only model outputs are fixtures. The original affirmative drafts still require
one repair; finite negative predicates cannot excuse a new positive guarantee.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
import uuid

from psycopg import sql

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import InvalidAnswer
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_memory import test_dsn


FIXTURE = Path(__file__).parent / 'fixtures' / '6b_evening_decision_denials.json'
GUARANTEE = '费用、退出和风险条件未经确认，不能承诺完全可逆或无损失'
SAFE = (
    '也不要假设付费后可以无损失退出',
    '不能假设可以无损失退出',
    '不能推断为零费用、免费退出或无损失',
    '两条都不能被描述为完全可逆或无损失',
    '未对任何费用、退出或可逆性做零成本、完全可逆或无损失的假设',
    '两方案是否允许无损失退出、是否有答复时限或名额限制均待核实',
)
RUN_EVIDENCE = []


class RecordedEveningModel:
    def __init__(self, sample, case_id):
        self.sample = sample
        self.case_id = case_id
        self.mapping = {}
        self.calls = []
        self.outputs = {}
        self.patch = None

    def bind(self, value):
        if isinstance(value, dict): return {key: self.bind(item) for key, item in value.items()}
        if isinstance(value, list): return [self.bind(item) for item in value]
        if isinstance(value, str):
            for old, new in self.mapping.items(): value = value.replace(old, new)
        return value

    def generate(self, **kwargs):
        purpose = kwargs['purpose']; data = kwargs['payload']['reference_data']
        self.calls.append(purpose)
        if purpose.startswith('specialist:') or data.get('claims'):
            raise AssertionError('Reality-only decision must not acquire symbolic claims')
        for fact in data.get('facts', []):
            for old, content in self.sample['id_bindings'].items():
                if str(fact.get('content', '')).rstrip('。') == content.rstrip('。'):
                    self.mapping[old] = fact['id']
        for proposal in self.sample['outputs']['intake'].get('proposals', []):
            if proposal.get('case_id'): self.mapping[proposal['case_id']] = self.case_id
        phase = 'repair' if self.patch is not None and purpose in ('synthesis', 'repair') else purpose
        output = self.bind(deepcopy(self.sample['outputs'][phase]))
        if self.patch is not None and purpose in ('synthesis', 'repair'):
            output.update(deepcopy(self.patch))
        self.outputs[purpose] = deepcopy(output)
        return {'output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1},
                'model': 'synthetic-recorded-evening-decision'}


class ObservedService(ConsultationService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.validation_attempts = []

    def _validate(self, owner, run, final):
        issues = super()._validate(owner, run, final)
        self.validation_attempts.append(list(issues))
        return issues


class EveningDecisionDenialsPG(unittest.TestCase):
    def setUp(self):
        self.repo = PostgresRepository(test_dsn(), schema='test_6b_evening_' + uuid.uuid4().hex[:16], max_size=4)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.service = ObservedService(self.repo)
        self.configure(self.evidence['samples'][0])

    def configure(self, sample):
        self.owner = 'synthetic-evening-' + sample['name']
        self.repo.ensure_owner(self.owner)
        self.case = self.service.memory.create_case(self.owner, 'self', '合成有限否定回归')['id']
        self.receipts = []
        for index, fact in enumerate(sample['saved_facts']):
            source = self.service.memory.receive(self.owner, content='请记住：' + fact['content'],
                source_id='saved-source-' + str(index), case_ids=[self.case])
            receipt = self.service.memory.save_fact(self.owner, 'self', source['id'], fact['content'],
                fact['kind'], case_id=self.case, operation_id='saved-fact-' + str(index))
            self.assertEqual(receipt['write_status'], 'saved'); self.receipts.append(receipt)
        self.model = RecordedEveningModel(sample, self.case)
        self.service.model = self.model
        self.sample = sample

    def tearDown(self):
        with self.repo.connection() as connection:
            runs = connection.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for run in runs:
            for epoch in range(run['retry_epoch'] + 1): self.service.runtime.purge(run['id'], epoch)
        with self.repo.connection() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.repo.schema)))
        self.repo.close()

    def execute(self, operation, *, issue=None, patch=None):
        self.model.patch = patch
        run = self.service.submit(owner=self.owner, message=self.sample['question'], request_id=operation,
            case_ids=[self.case], depth='standard', selection={'date': '2026-10-11', 'systems': []})
        result = None
        try:
            if issue:
                with self.assertRaises(InvalidAnswer) as caught: self.service.execute(self.owner, run['id'])
                self.assertEqual(caught.exception.code, 'REFERENCE_ERROR')
                self.assertIn(issue, self.service.validation_attempts[-1])
            else:
                try: result = self.service.execute(self.owner, run['id'])
                except InvalidAnswer as error:
                    error.add_note(repr(self.service.validation_attempts[-1])); raise
                self.assertTrue(result['validation']['valid'])
            current = self.repo.fetch_run(self.owner, run['id'])
            repaired = issue is not None or patch is None
            self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']),
                ('failed' if issue else 'succeeded', 3 if repaired else 2, 6, repaired))
            if issue: self.assertIsNone(current['result'])
            self.assertEqual(len(self.service.memory.facts(self.owner)), len(self.sample['saved_facts']))
            return run, result
        finally:
            current = self.repo.fetch_run(self.owner, run['id'])
            RUN_EVIDENCE.append({'sample': self.sample['name'], 'status': current['status'],
                'calls': current['calls'], 'call_limit': current['call_limit'], 'repair_used': current['repair_used']})

    def test_both_complete_original_drafts_repair_once_commit_and_replay_without_new_calls(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertEqual(self.evidence['source_commit'], '6b96ba3de91c262589b5f77f11f61e1ec1c5c3f6')
        for index, sample in enumerate(self.evidence['samples']):
            with self.subTest(sample=sample['name']):
                if index: self.configure(sample)
                self.assertEqual(sample['original_status'], 'failed'); self.assertEqual(sample['original_calls'], 3)
                start = len(self.service.validation_attempts)
                run, result = self.execute('complete-recorded-' + sample['name'])
                current = self.repo.fetch_run(self.owner, run['id'])
                self.assertEqual(self.model.calls, ['intake', 'synthesis', 'repair'])
                self.assertEqual(self.service.validation_attempts[start:], [[GUARANTEE], []])
                original = self.service._record(self.owner, run['id'], 'model:synthesis')
                self.assertEqual(self.service._validate(self.owner, current, original), [GUARANTEE])
                repair = self.service._record(self.owner, run['id'], 'model:repair')
                self.assertEqual(self.service._validate(self.owner, current, repair), [])
                for key in sample['outputs']['repair']:
                    self.assertEqual(result[key], self.model.outputs['repair'][key])
                self.assertEqual(result['cited_claim_ids'], [])
                self.assertTrue(all(r['write_status'] == 'pending_confirmation' for r in result['memory_receipts']))
                for receipt in self.receipts:
                    self.assertEqual(current['dependencies']['fact:' + receipt['fact_id']], receipt['revision'])
                calculation = self.service._record(self.owner, run['id'], 'calculation')
                self.assertEqual(calculation['claims'], [])
                self.assertTrue(self.service.knowledge.revalidate_claims(calculation['calculation'], calculation['claims'])['eligible'])
                replay = self.service.submit(owner=self.owner, message=sample['question'],
                    request_id='complete-recorded-' + sample['name'], case_ids=[self.case], depth='standard',
                    selection={'date': '2026-10-11', 'systems': []})
                self.assertEqual(replay['id'], run['id']); self.assertEqual(self.service.execute(self.owner, replay['id']), result)
                self.assertEqual(len(self.model.calls), 3)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)

    def test_each_finite_negative_or_unverified_question_commits_without_repair(self):
        for index, passage in enumerate(SAFE):
            with self.subTest(passage=passage):
                self.execute('finite-safe-' + str(index), patch={'plain_summary': passage + '。'})

    def test_each_finite_scope_rejects_double_denial_quotes_and_new_positive_assertion(self):
        for index, passage in enumerate(SAFE):
            mutations = ('不是' + passage, '不能说' + passage, '“' + passage + '”',
                '此前称“' + passage + '”', passage + '，但报名完全可逆',
                passage + '。付款无损失', passage + '并保证报名无损失',
                '“此前答复中，' + passage + '”')
            for mutation_index, mutation in enumerate(mutations):
                with self.subTest(mutation=mutation):
                    self.execute('finite-unsafe-' + str(index) + '-' + str(mutation_index), issue=GUARANTEE,
                        patch={'plain_summary': mutation + '。'})

    def test_new_objects_verbs_and_question_conditions_do_not_inherit_the_finite_scope(self):
        passages = ('假设可以无损失退出', '不要假设付费后可以A无损失退出',
            '不能假设可以无损失退出并确认完全可逆', '不能推断为零费用、免费退出或保证无损失',
            '不能推断为零费用、免费退出或A无损失', '两条都被描述为完全可逆或无损失',
            '两条都不能被描述为完全可逆或承诺无损失',
            '未对任何费用、退出或可逆性做零成本、完全可逆或无损失的报价',
            '未对任何费用、退出或可逆性做零成本、完全可逆或保证无损失的假设',
            '两方案允许无损失退出、是否有答复时限或名额限制均待核实',
            '两方案是否允许无损失退出、是否有答复时限或名额限制均已核实',
            '两方案是否允许无损失退出、名额限制均待核实')
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                self.execute('finite-boundary-' + str(index), issue=GUARANTEE, patch={'plain_summary': passage + '。'})

    def test_finite_negative_field_and_saved_negative_source_never_authorize_a_positive(self):
        for index, passage in enumerate(SAFE):
            with self.subTest(cross_field=passage):
                self.execute('finite-cross-field-' + str(index), issue=GUARANTEE,
                    patch={'plain_summary': passage + '。', 'professional_appendix': '报名完全可逆，付款无损失。'})
        for index, passage in enumerate(SAFE[:5]):
            quoted = '请保存以下资料：“' + passage + '”。'
            source = self.service.memory.receive(self.owner, content=quoted,
                source_id='negative-source-' + str(index), case_ids=[self.case])
            consent = self.service.memory.grant_authorization(self.owner, 'self', source['id'], quoted,
                kinds=['hypothesis'], operation_id='negative-consent-' + str(index))
            receipt = self.service.memory.save_fact(self.owner, 'self', source['id'], passage, 'hypothesis',
                authorization_id=consent['id'], case_id=self.case, operation_id='negative-fact-' + str(index))
            self.assertEqual(receipt['write_status'], 'saved', repr(receipt))
        self.sample = deepcopy(self.sample)
        self.sample['saved_facts'].extend([{'kind': 'background', 'content': passage} for passage in SAFE[:5]])
        self.execute('finite-negative-source-positive', issue=GUARANTEE,
            patch={'plain_summary': '报名完全可逆，付款无损失。'})


if __name__ == '__main__': unittest.main()
