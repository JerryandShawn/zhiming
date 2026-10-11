"""Full synthetic provider evidence replayed through real PG/Core/knowledge.

Only model responses are substituted. Original provider paragraphs are kept
whole in the fixture; only new local evidence IDs are bound during replay.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unittest
import uuid

from psycopg import sql

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import InvalidAnswer
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_memory import test_dsn as pg_dsn
from tests.test_core_pg_channels import FixtureModel


FIXTURE = Path(__file__).parent / 'fixtures' / '104_tarot_repairs.json'
GUARANTEE_ISSUE = '费用、退出和风险条件未经确认，不能承诺完全可逆或无损失'
WITHDRAWAL = '此前表述称行动"完全可逆、无损失"，此断语依据不足'
POSTPOSED = '不作无损失承诺'


class EvidenceProvider(FixtureModel):
    def __init__(self):
        super().__init__()
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.final_patch = None
        self.outputs = {}
        self.repair_errors = []

    def generate(self, **kwargs):
        self.requests.append({'purpose': kwargs['purpose'], 'payload': deepcopy(kwargs['payload'])})
        purpose = kwargs['purpose']
        data = kwargs['payload']['reference_data']
        if self.final_patch is not None:
            # Short guard cases still execute all real service stages. The
            # provider returns valid arrays and the actual current citations.
            response = FixtureModel.generate(self, **kwargs)
            self.requests.pop()
            if purpose == 'repair': self.repair_errors = deepcopy(kwargs['payload']['errors'])
            if purpose in ('synthesis', 'repair'):
                response['output'].update(plain_summary=self.final_patch, explanation='', actions=[],
                    follow_up='', professional_appendix='', caveats=[])
            return response
        output = deepcopy(self.evidence['outputs'][purpose])
        mappings = {}
        raw = self.evidence['outputs']['repair']
        if data.get('facts'):
            fact = next(f for f in data['facts'] if '不能上夜班' in f['content'])
            mappings.update({ident: fact['id'] for ident in raw['cited_fact_ids']})
        if data.get('claims'):
            claim = next(c for c in data['claims'] if c['system'] == 'tarot')
            mappings.update({ident: claim['claim_id'] for ident in raw['cited_claim_ids']})
            artifact = next(ref['artifact_id'] for ref in claim['feature_refs'] if 'artifact_id' in ref)
            mappings.update({ident: artifact for ident in re.findall(r'tarot-[a-z0-9]{20,}', raw['professional_appendix'])})
        def bind(value):
            if isinstance(value, dict): return {key: bind(item) for key, item in value.items()}
            if isinstance(value, list): return [bind(item) for item in value]
            if isinstance(value, str):
                for old, new in mappings.items(): value = value.replace(old, new)
            return value
        output = bind(output)
        self.outputs[purpose] = deepcopy(output)
        if purpose == 'repair': self.repair_errors = deepcopy(kwargs['payload']['errors'])
        return {'output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1}, 'model': 'synthetic-evidence-replay'}


class TarotRepairGuards(unittest.TestCase):
    def setUp(self):
        self.schema = 'test_tarot_repair_' + uuid.uuid4().hex[:16]
        self.repo = PostgresRepository(pg_dsn(), schema=self.schema, max_size=4)
        self.repo.ensure_owner('alpha')
        self.provider = EvidenceProvider()
        self.service = ConsultationService(self.repo, model=self.provider)
        source = self.service.memory.receive('alpha', content='请记住：我不能上夜班。', source_id='night-constraint')
        self.fact = self.service.memory.save_fact('alpha', 'self', source['id'], '我不能上夜班', 'constraint')
        self.case = self.service.memory.create_case('alpha', 'self', '合成学习反思', operation_id='synthetic-case')
        draw = self.service.tarot.create_draw('alpha', subject_id='self', case_id=self.case['id'],
            question='如何在白天安排学习？', spread_id='reflect3', draw_source='manual',
            manual_cards=[{'card_id': 'major-00', 'orientation': 'upright'},
                          {'card_id': 'major-02', 'orientation': 'reversed'},
                          {'card_id': 'major-08', 'orientation': 'upright'}],
            idempotency_key='fixed-evidence-cards')['draw']
        self.draw = self.service.tarot.reveal('alpha', draw['id'])

    def tearDown(self):
        with self.repo.connection() as connection:
            runs = connection.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for run in runs:
            for epoch in range(run['retry_epoch'] + 1): self.service.runtime.purge(run['id'], epoch)
        with self.repo.connection() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def consult(self, operation):
        run = self.service.submit(owner='alpha', message='请解释这次固定塔罗的学习反思，给一个现实行动。',
            request_id=operation, draw_id=self.draw['id'], depth='standard')
        return run, self.service.execute('alpha', run['id'])

    def test_full_original_provider_repair_commits_after_four_calls_and_stable_replay(self):
        evidence = self.provider.evidence
        self.assertTrue(evidence['synthetic_only'])
        self.assertEqual(evidence['source_commit'], '10436539036b63d77869afb2648e2478bad77362')
        self.assertEqual(evidence['original_calls'], 4)
        self.assertIn(WITHDRAWAL, evidence['outputs']['repair']['explanation'])
        self.assertIn(POSTPOSED, evidence['outputs']['repair']['professional_appendix'])
        raw_hash = hashlib.sha256(json.dumps(evidence['outputs']['repair'], ensure_ascii=False,
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        run, result = self.consult('actual-provider-repair')
        current = self.repo.fetch_run('alpha', run['id'])
        self.assertEqual((current['status'], current['calls'], current['repair_used']), ('succeeded', 4, True))
        self.assertEqual([request['purpose'] for request in self.provider.requests],
                         ['intake', 'specialist:tarot', 'synthesis', 'repair'])
        self.assertIn(GUARANTEE_ISSUE, self.provider.repair_errors)
        self.assertEqual(result['validation']['status'], 'validated')
        self.assertEqual(result['explanation'], self.provider.outputs['repair']['explanation'])
        self.assertIn(self.provider.outputs['repair']['professional_appendix'], result['professional_appendix'])
        self.assertEqual(result['cited_fact_ids'], [self.fact['id']])
        self.assertEqual(self.service.tarot.get('alpha', self.draw['id'])['cards'], self.draw['cards'])
        self.assertEqual(self.service.execute('alpha', run['id']), result)
        self.assertEqual(len(self.provider.requests), 4)
        self.assertEqual(hashlib.sha256(json.dumps(self.provider.evidence['outputs']['repair'], ensure_ascii=False,
            sort_keys=True, separators=(',', ':')).encode()).hexdigest(), raw_hash)

    def test_tight_local_denial_and_historical_withdrawal_need_no_repair(self):
        passages = (POSTPOSED + '。', '不作"无损失"承诺。', '不做无损失保证。',
            '不作"完全可逆、无损失"承诺。', WITHDRAWAL + '。',
            '此前表述称行动“完全可逆、无损失”，该断语依据不足。')
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                self.provider.final_patch = passage
                before = len(self.provider.requests)
                _, result = self.consult('local-denial-' + str(index))
                self.assertTrue(result['validation']['valid'])
                self.assertEqual(len(self.provider.requests) - before, 3)

    def test_double_denial_affirmation_contrast_and_unwithdrawn_quotes_still_fail(self):
        passages = (
            '不是不作无损失承诺。', '并非不作无损失承诺。', '不能不作无损失承诺。',
            '不作无损失承诺，但报名无损失。', '不作无损失承诺。事实上报名完全可逆。',
            WITHDRAWAL + '，但现在报名完全可逆。', WITHDRAWAL + '；不过这个课程无损失。',
            '此前表述称行动"完全可逆、无损失"，此断语并非依据不足。',
            '此前表述称行动"完全可逆、无损失"，此断语不是没有依据。',
            '此前表述称行动"完全可逆、无损失"，此断语仍可承诺。',
            '报名"完全可逆、无损失"。', '此前表述称行动"完全可逆、无损失"，请继续行动。',
            '不作记录，报名无损失。', '不作无损失承诺，实际上保证无损失。',
        )
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                self.provider.final_patch = passage
                with self.assertRaises(InvalidAnswer): self.consult('unsafe-denial-' + str(index))
                with self.repo.connection() as connection:
                    row = connection.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND operation_id=%s').format(
                        self.repo.table('core_runs')), ('alpha', 'unsafe-denial-' + str(index))).fetchone()
                self.assertEqual((row['status'], row['calls'], row['repair_used']), ('failed', 4, True))
                self.assertIsNone(row['result'])
                self.assertIn(GUARANTEE_ISSUE, self.provider.repair_errors)


if __name__ == '__main__':
    unittest.main()
