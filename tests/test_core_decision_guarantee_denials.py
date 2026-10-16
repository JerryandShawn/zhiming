"""Full synthetic-only decision repair through real PostgreSQL/Core/knowledge.

Only model outputs are substituted. Initial positive promises remain invalid;
the full original repair must pass without excusing later positive promises.
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
from tests.test_core_memory import test_dsn as pg_dsn


FIXTURE = Path(__file__).parent / 'fixtures' / '9c_decision_guarantee_denials.json'
GUARANTEE_ISSUE = '费用、退出和风险条件未经确认，不能承诺完全可逆或无损失'


class RecordedDecisionModel:
    def __init__(self, evidence):
        self.evidence = evidence
        self.calls = []
        self.outputs = {}
        self.mapping = {}
        self.final_patch = None

    def bind(self, value):
        if isinstance(value, dict): return {key: self.bind(item) for key, item in value.items()}
        if isinstance(value, list): return [self.bind(item) for item in value]
        if isinstance(value, str):
            for old, new in self.mapping.items(): value = value.replace(old, new)
        return value

    def generate(self, **kwargs):
        purpose = kwargs['purpose']; data = kwargs['payload']['reference_data']
        self.calls.append(purpose)
        if data.get('facts'):
            fact = next(f for f in data['facts'] if f.get('content') == self.evidence['constraint'])
            for output in self.evidence['outputs'].values():
                for ident in output.get('cited_fact_ids', []): self.mapping[ident] = fact['id']
        if data.get('claims'): raise AssertionError('Ordinary decision must not force specialists')
        raw = self.evidence['outputs']['repair' if self.final_patch is not None and purpose in ('synthesis', 'repair') else purpose]
        output = self.bind(deepcopy(raw))
        if self.final_patch is not None and purpose in ('synthesis', 'repair'):
            output['plain_summary'] = self.final_patch
        self.outputs[purpose] = deepcopy(output)
        return {'output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1},
                'model': 'synthetic-recorded-decision-guarantee-denial'}


class ObservedDecisionService(ConsultationService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.validation_attempts = []

    def _validate(self, owner, run, final):
        issues = super()._validate(owner, run, final)
        self.validation_attempts.append(list(issues))
        return issues


class DecisionGuaranteeDenialRegression(unittest.TestCase):
    def setUp(self):
        self.schema = 'test_decision_denial_' + uuid.uuid4().hex[:16]
        self.repo = PostgresRepository(pg_dsn(), schema=self.schema, max_size=4)
        self.owner = 'synthetic-decision'; self.repo.ensure_owner(self.owner)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.model = RecordedDecisionModel(self.evidence)
        self.service = ObservedDecisionService(self.repo, model=self.model)
        source = self.service.memory.receive(self.owner, content='请记住：我不能上夜班。',
            source_id='synthetic-night-constraint')
        receipt = self.service.memory.save_fact(self.owner, 'self', source['id'],
            self.evidence['constraint'], 'constraint', operation_id='synthetic-night-save')
        self.assertEqual(receipt['write_status'], 'saved')
        self.fact_id = receipt['fact_id']

    def tearDown(self):
        with self.repo.connection() as connection:
            runs = connection.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(
                self.repo.table('core_runs'))).fetchall()
        for run in runs:
            for epoch in range(run['retry_epoch'] + 1): self.service.runtime.purge(run['id'], epoch)
        with self.repo.connection() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def consult(self, operation):
        run = self.service.submit(owner=self.owner, message=self.evidence['question'],
            request_id=operation, depth='standard')
        return run, self.service.execute(self.owner, run['id'])

    def run_by_operation(self, operation):
        with self.repo.connection() as connection:
            row = connection.execute(sql.SQL('SELECT id FROM {} WHERE owner=%s AND operation_id=%s').format(
                self.repo.table('core_runs')), (self.owner, operation)).fetchone()
        return self.repo.fetch_run(self.owner, row['id'])

    def test_original_positive_synthesis_rejected_full_repair_commits_and_replays(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertEqual(self.evidence['source_commit'], '9c46f7e3aa1f988dc7318d5ff597de2fab4925c0')
        self.assertEqual(self.evidence['original_calls'], 3)
        run, result = self.consult('original-decision-repair')
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['repair_used']), ('succeeded', 3, True))
        self.assertEqual(self.model.calls, ['intake', 'synthesis', 'repair'])
        self.assertEqual(self.service.validation_attempts, [[GUARANTEE_ISSUE], []])
        original = self.service._record(self.owner, run['id'], 'model:synthesis')
        self.assertIn('询问本身完全可逆', json.dumps(original, ensure_ascii=False))
        self.assertEqual(self.service._validate(self.owner, current, original), [GUARANTEE_ISSUE])
        repaired = self.service._record(self.owner, run['id'], 'model:repair')
        self.assertEqual(self.service._validate(self.owner, current, repaired), [])
        self.assertEqual(result['plain_summary'], self.model.outputs['repair']['plain_summary'])
        self.assertEqual(result['explanation'], self.model.outputs['repair']['explanation'])
        self.assertEqual(result['decision_options'], self.model.outputs['repair']['decision_options'])
        self.assertEqual(result['cited_fact_ids'], [self.fact_id])
        self.assertEqual(result['cited_claim_ids'], [])
        self.assertTrue(result['memory_receipts'])
        self.assertTrue(all(receipt['write_status'] == 'pending_confirmation' for receipt in result['memory_receipts']))
        self.assertEqual(len(self.service.memory.facts(self.owner)), 1)
        self.assertTrue(result['validation']['valid'])
        self.assertEqual(self.service._record(self.owner, run['id'], 'calculation')['claims'], [])
        self.assertEqual(self.service.execute(self.owner, run['id']), result)
        replay, same = self.consult('original-decision-repair')
        self.assertEqual(replay['id'], run['id']); self.assertEqual(same, result)
        self.assertEqual(len(self.model.calls), 3)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)

    def test_tight_passive_denials_and_exact_any_qualifier_do_not_need_repair(self):
        passages = ('未知退出条件不能被当作“随时可无损退出”。',
            '未知条件不能被当作零风险或可无损退出。',
            '未知条件不能被视为无损失。',
            '暂缓选项不再宣称任何完全可逆性。',
            '不能宣称为无损失。', '不能宣称任何完全可逆或无损失。')
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                self.model.final_patch = passage
                before = len(self.model.calls)
                run, result = self.consult('tight-denial-' + str(index))
                current = self.repo.fetch_run(self.owner, run['id'])
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('succeeded', 2, False))
                self.assertTrue(result['validation']['valid'])
                self.assertEqual(self.model.calls[before:], ['intake', 'synthesis'])

    def test_double_denials_cross_sentences_and_renewed_positives_still_fail(self):
        passages = ('询问本身完全可逆。', '未知退出条件可被当作“随时可无损退出”。',
            '不是不能被当作零风险。', '不能说不能被视为无损失。',
            '并非不再宣称任何完全可逆性。',
            '不能说不再宣称任何完全可逆性。',
            '不可能不能宣称为无损失。',
            '不能被当作零风险，但是实际上零风险。',
            '不能被视为无损失。实际安排无损失。',
            '不再宣称任何完全可逆性，但课程完全可逆。',
            '不能宣称为无损失，却保证无损失。',
            '不能被当作零风险或保证完全可逆。',
            '此前表述说“随时可无损退出”。',
            '不能被当作零风险，实际安排随时可无损退出。')
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                self.model.final_patch = passage
                before = len(self.model.calls)
                operation = 'unsafe-guarantee-' + str(index)
                with self.assertRaises(InvalidAnswer): self.consult(operation)
                current = self.run_by_operation(operation)
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('failed', 3, True))
                self.assertIsNone(current['result'])
                self.assertEqual(self.model.calls[before:], ['intake', 'synthesis', 'repair'])
                final = self.service._record(self.owner, current['id'], 'model:repair')
                self.assertEqual(self.service._validate(self.owner, current, final), [GUARANTEE_ISSUE])
        self.assertEqual(len(self.service.memory.facts(self.owner)), 1)


if __name__ == '__main__': unittest.main()
