"""Original synthetic-only Bazi outputs through real Core, charts and PostgreSQL.

Only model responses are substituted. The fixture retains all four original
contract outputs; local fact/claim identifiers are the only replay changes.
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


FIXTURE = Path(__file__).parent / 'fixtures' / '9c_bazi_save_denials.json'
SAVE_ISSUE = '保存或删除提示必须由实际程序回执生成'


class RecordedBaziModel:
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
        purpose = kwargs['purpose']
        data = kwargs['payload']['reference_data']
        self.calls.append(purpose)
        if data.get('facts'):
            fact = next(f for f in data['facts'] if f.get('content') == self.evidence['constraint'])
            for output in self.evidence['outputs'].values():
                for ident in output.get('cited_fact_ids', []): self.mapping[ident] = fact['id']
        if data.get('claims'):
            claims = [claim for claim in data['claims'] if claim['system'] == 'bazi']
            original_ids = self.evidence['outputs']['specialist:bazi']['claim_ids']
            if len(original_ids) != len(claims):
                raise AssertionError('Original Bazi claim count differs from actual calculation')
            self.mapping.update((ident, claim['claim_id']) for ident, claim in zip(original_ids, claims))
        output = self.bind(deepcopy(self.evidence['outputs'][purpose]))
        if self.final_patch is not None and purpose in ('synthesis', 'repair'):
            output['plain_summary'] = self.final_patch
        self.outputs[purpose] = deepcopy(output)
        return {'output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1},
                'model': 'synthetic-recorded-bazi-save-denial'}


class BaziSaveDenialRegression(unittest.TestCase):
    def setUp(self):
        self.schema = 'test_bazi_save_denial_' + uuid.uuid4().hex[:16]
        self.repo = PostgresRepository(pg_dsn(), schema=self.schema, max_size=4)
        self.owner = 'synthetic-bazi'; self.repo.ensure_owner(self.owner)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.model = RecordedBaziModel(self.evidence)
        self.service = ConsultationService(self.repo, model=self.model)
        # This is the explicitly authorized fictional profile used by the real
        # provider evaluation, never a production subject or an inferred fact.
        profile = self.evidence['profile']
        text = '请保存我已核对并确认的合成出生资料：\n' + '\n'.join(
            f'{field}：{value}' for field, value in profile.items())
        source = self.service.memory.receive(self.owner, content=text, source_id='synthetic-profile')
        grant = self.service.memory.grant_authorization(self.owner, 'self', source['id'], text,
            kinds=['profile'], operation_id='synthetic-profile-consent')
        for field, value in profile.items():
            receipt = self.service.memory.save_fact(self.owner, 'self', source['id'],
                f'{field}：{value}', 'profile', field=field, value=value,
                authorization_id=grant['id'], operation_id='profile:' + field)
            self.assertEqual(receipt['write_status'], 'saved')
        constraint = self.service.memory.receive(self.owner, content='请记住：我不能上夜班。',
            source_id='synthetic-night-constraint')
        receipt = self.service.memory.save_fact(self.owner, 'self', constraint['id'],
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

    def test_original_full_synthesis_commits_three_calls_and_stable_replay(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only'])
        self.assertEqual(self.evidence['source_commit'], '9c46f7e3aa1f988dc7318d5ff597de2fab4925c0')
        self.assertEqual(self.evidence['original_calls'], 4)
        run, result = self.consult('original-full-synthesis')
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['repair_used']), ('succeeded', 3, False))
        self.assertEqual(self.model.calls, ['intake', 'specialist:bazi', 'synthesis'])
        self.assertEqual(result['plain_summary'], self.model.outputs['synthesis']['plain_summary'])
        self.assertEqual(result['explanation'], self.model.outputs['synthesis']['explanation'])
        self.assertTrue(result['professional_appendix'].startswith(self.model.outputs['synthesis']['professional_appendix']))
        validated = self.service._record(self.owner, run['id'], 'validation')['final']
        self.assertEqual(validated['professional_appendix'], self.model.outputs['synthesis']['professional_appendix'])
        self.assertEqual(result['cited_fact_ids'], [self.fact_id])
        self.assertTrue(result['validation']['valid'])
        self.assertEqual(result['memory_receipts'], [])
        self.assertEqual(len(self.service.memory.facts(self.owner)), 7)
        calculation = self.service._record(self.owner, run['id'], 'calculation')
        self.assertEqual(len(calculation['claims']), 1)
        self.assertEqual(calculation['claims'][0]['system'], 'bazi')
        verified = self.service.knowledge.revalidate_claims(calculation['calculation'], calculation['claims'])
        self.assertTrue(verified['eligible'])
        self.assertEqual(self.service.execute(self.owner, run['id']), result)
        replay, same = self.consult('original-full-synthesis')
        self.assertEqual(replay['id'], run['id']); self.assertEqual(same, result)
        self.assertEqual(len(self.model.calls), 3)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)

    def test_original_full_repair_and_exact_denied_objects_validate(self):
        run, _ = self.consult('original-full-repair-validation')
        current = self.repo.fetch_run(self.owner, run['id'])
        repair = self.model.bind(deepcopy(self.evidence['outputs']['repair']))
        self.assertEqual(self.service._validate(self.owner, current, repair), [])
        for passage in ('本轮不声称任何资料已被保存、更新或删除。',
                        '也不声称任何资料已被保存或更新。',
                        '不能声称任何资料“已被保存”。',
                        '不声称已保存或更新任何资料。'):
            with self.subTest(passage=passage):
                final = deepcopy(repair); final['plain_summary'] = passage
                self.assertEqual(self.service._validate(self.owner, current, final), [])
        self.assertEqual(len(self.model.calls), 3)

    def test_direct_save_double_denials_and_new_affirmatives_remain_rejected(self):
        passages = ('任何资料已被保存。', '仅来自已保存塔罗声明。',
            '不声称任何资料已被保存，但资料已保存。',
            '不声称任何资料已被保存。资料已保存。',
            '不是不声称任何资料已被保存。',
            '不能说不声称任何资料已被保存。',
            '不声称任何资料，档案已保存。',
            '不声称任何资料已保存并确认档案已保存。',
            '此前声称任何资料已被保存。',
            '不声称任何资料可能实际上已被保存。')
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                self.model.final_patch = passage
                before = len(self.model.calls)
                operation = 'unsafe-save-' + str(index)
                with self.assertRaises(InvalidAnswer): self.consult(operation)
                with self.repo.connection() as connection:
                    run = connection.execute(sql.SQL('SELECT id FROM {} WHERE owner=%s AND operation_id=%s').format(
                        self.repo.table('core_runs')), (self.owner, operation)).fetchone()
                current = self.repo.fetch_run(self.owner, run['id'])
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('failed', 4, True))
                self.assertIsNone(current['result'])
                self.assertEqual(self.model.calls[before:], ['intake', 'specialist:bazi', 'synthesis', 'repair'])
                repair = self.service._record(self.owner, run['id'], 'model:repair')
                self.assertEqual(self.service._validate(self.owner, current, repair), [SAVE_ISSUE])
        self.assertEqual(len(self.service.memory.facts(self.owner)), 7)


if __name__ == '__main__': unittest.main()
