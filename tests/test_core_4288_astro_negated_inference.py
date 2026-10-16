"""Recorded astro outputs through real PostgreSQL, LangGraph and native charts.

Only model outputs are substituted. The original diagnosis is copied intact;
new local fact and claim IDs are bound without rewriting its prose.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

from psycopg import sql

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import InvalidAnswer
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.runtime import LangGraphRuntime
from tests.test_core_memory import test_dsn


FIXTURE = Path(__file__).parent / 'fixtures' / '4288_astro_negated_inference.json'
GUARANTEE = '费用、退出和风险条件未经确认，不能承诺完全可逆或无损失'
DENIAL = '均保持待核实而非推断为零风险'
RUN_EVIDENCE = []


class RecordedAstroModel:
    def __init__(self):
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.mapping = {}
        self.calls = []
        self.outputs = {}
        self.seen_fact_ids = set()
        self.patch = None
        self.force_repair = False
        self.first = 'synthesis'

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
            self.seen_fact_ids.update(fact['id'] for fact in data['facts'])
            old = self.evidence['outputs']['synthesis']['output']['cited_fact_ids']
            facts = sorted(data['facts'], key=lambda item: (item.get('field') or '', item['content']))
            assert len(facts) >= len(old)
            self.mapping.update({identifier: fact['id'] for identifier, fact in zip(old, facts)})
        if data.get('claims'):
            old = self.evidence['outputs']['calculation']['output']['claims'][0]
            current = next(claim for claim in data['claims'] if claim['system'] == 'astro')
            assert current['rule_id'] == old['rule_id']
            assert [ref['value'] for ref in current['feature_refs']] == [ref['value'] for ref in old['feature_refs']]
            self.mapping[old['claim_id']] = current['claim_id']
        if purpose == 'intake':
            output = {'plan': deepcopy(self.evidence['outputs']['plan']['output']),
                      'proposals': [], 'retire_fact_ids': []}
        elif purpose == 'specialist:astro':
            output = deepcopy(self.evidence['outputs']['specialists']['output']['specialists'][0])
        else:
            phase = 'model:repair' if purpose == 'repair' else self.first
            output = deepcopy(self.evidence['outputs'][phase]['output'])
            if self.patch is not None:
                output.update(deepcopy(self.patch))
            if self.force_repair and purpose == 'synthesis':
                output['plain_summary'] += '报名零风险。'
        output = self.bind(output)
        self.outputs[purpose] = deepcopy(output)
        return {'output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1},
                'model': 'fixture-recorded-4288-astro'}


class ObservedService(ConsultationService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.validation_attempts = []

    def _validate(self, owner, run, final):
        issues = super()._validate(owner, run, final)
        self.validation_attempts.append(list(issues))
        return issues


class AstroNegatedInferencePG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        chart = os.environ.get('CHART_PYTHON')
        assert chart and Path(chart).is_file(), 'requires configured native chart interpreter'
        version = subprocess.check_output([chart, '-c', 'import sys;print(sys.version_info[:2])'], text=True)
        assert version.strip() == '(3, 11)', version

    def setUp(self):
        self.fixture_hash = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.repo = PostgresRepository(test_dsn(), schema='test_4288_astro_' + uuid.uuid4().hex[:16], max_size=4)
        self.owner = 'synthetic-astro'
        self.repo.ensure_owner(self.owner)
        self.model = RecordedAstroModel()
        self.assertEqual(self.model.evidence['commit'], '4288d5aa3e23c7b2678b37b64462b9e1a91ac1df')
        self.assertTrue(self.model.evidence['synthetic_only'])
        self.assertEqual((self.model.evidence['calls'], self.model.evidence['repair_used']), (4, True))
        self.service = ObservedService(self.repo, model=self.model)
        self.addCleanup(self.cleanup)
        self.assertIsInstance(self.service.runtime, LangGraphRuntime)
        profile = {'gender': '男', 'birth.solar_datetime': '1990-05-03 13:18',
                   'birth.location.lng': 104.07, 'birth.location.lat': 30.67,
                   'birth.timezone_offset': 8, 'birth.precision': 'exact'}
        text = '请保存我已核对并确认的合成出生资料：\n' + '\n'.join(f'{key}：{value}' for key, value in profile.items())
        source = self.service.memory.receive(self.owner, content=text, source_id='synthetic-profile')
        grant = self.service.memory.grant_authorization(self.owner, 'self', source['id'], text,
            kinds=['profile'], operation_id='synthetic-profile-consent')
        for field, value in profile.items():
            receipt = self.service.memory.save_fact(self.owner, 'self', source['id'], f'{field}：{value}',
                'profile', field=field, value=value, authorization_id=grant['id'], operation_id='profile:' + field)
            self.assertEqual(receipt['write_status'], 'saved')
        source = self.service.memory.receive(self.owner, content='请记住：我不能上夜班。', source_id='night-constraint')
        self.service.memory.save_fact(self.owner, 'self', source['id'], '我不能上夜班', 'constraint')
        source = self.service.memory.receive(self.owner, content='合成学习决策。目标：在固定白天时间内学习',
            source_id='synthetic-case-source')
        self.case = self.service.memory.create_case(self.owner, 'self', '合成学习决策',
            goal='在固定白天时间内学习', message_id=source['id'], operation_id='synthetic-case')['id']

    def cleanup(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), self.fixture_hash)
        with self.repo.connection() as connection:
            runs = connection.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for run in runs:
            for epoch in range(run['retry_epoch'] + 1): self.service.runtime.purge(run['id'], epoch)
        with self.repo.connection() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.repo.schema)))
        self.repo.close()

    def execute(self, operation, *, unsafe=False, patch=None, force_repair=False, first='synthesis', message=None):
        self.model.patch = patch
        self.model.force_repair = force_repair
        self.model.first = first
        before = len(self.model.calls)
        attempt = len(self.service.validation_attempts)
        run = self.service.submit(owner=self.owner,
            message=message or '请依据西方星盘讨论2026-10-11的学习主题，保留专业字段和局限。',
            request_id=operation, case_ids=[self.case], depth='standard',
            selection={'date': '2026-10-11', 'systems': ['astro']})
        result = None
        try:
            if unsafe:
                with self.assertRaises(InvalidAnswer) as caught: self.service.execute(self.owner, run['id'])
                self.assertEqual(caught.exception.code, 'REFERENCE_ERROR')
            else:
                result = self.service.execute(self.owner, run['id'])
            row = self.repo.fetch_run(self.owner, run['id'])
            repaired = unsafe or force_repair
            self.assertEqual((row['status'], row['calls'], row['call_limit'], row['repair_used']),
                ('failed' if unsafe else 'succeeded', 4 if repaired else 3, 6, repaired))
            self.assertEqual(self.model.calls[before:],
                ['intake', 'specialist:astro', 'synthesis'] + (['repair'] if repaired else []))
            if unsafe:
                self.assertIsNone(row['result'])
                self.assertTrue(all(GUARANTEE in issues for issues in self.service.validation_attempts[attempt:]))
            else:
                self.assertTrue(result['validation']['valid'])
                self.assertEqual(self.service.execute(self.owner, run['id']), result)
                self.assertEqual(len(self.model.calls) - before, 4 if repaired else 3)
            return result
        finally:
            row = self.repo.fetch_run(self.owner, run['id'])
            RUN_EVIDENCE.append({'operation': operation, 'run_id': run['id'],
                'status': row['status'], 'calls': row['calls'], 'limit': row['call_limit'],
                'repair_used': row['repair_used'], 'model_calls': self.model.calls[before:],
                'validation_attempts': self.service.validation_attempts[attempt:],
                'fixture_sha256': self.fixture_hash, 'chart_native': '3.11', 'runtime': 'LangGraphRuntime'})

    def test_full_original_synthesis_and_repair_prose_validate_unchanged(self):
        for phase in ('synthesis', 'model:repair'):
            with self.subTest(phase=phase):
                raw = self.model.evidence['outputs'][phase]['output']
                self.assertIn(DENIAL, raw['explanation'])
                result = self.execute('original-' + phase, first=phase)
                self.assertEqual(result['explanation'], self.model.bind(raw['explanation']))
                self.assertIn(self.model.bind(raw['professional_appendix']), result['professional_appendix'])

    def test_full_repair_path_uses_original_complete_repair(self):
        result = self.execute('forced-complete-repair', force_repair=True)
        raw = self.model.evidence['outputs']['model:repair']['output']
        self.assertEqual(result['explanation'], self.model.bind(raw['explanation']))
        self.assertIn(GUARANTEE, self.service.validation_attempts[-2])
        self.assertEqual(self.service.validation_attempts[-1], [])

    def test_finite_local_denials_and_lists_validate(self):
        for index, passage in enumerate((DENIAL, '保持待核实而非推断为零风险',
                '非推断为零风险', DENIAL + '或无损失', DENIAL + '、完全可逆或无损失')):
            with self.subTest(passage=passage):
                self.execute('finite-' + str(index), patch={'plain_summary': passage + '。'})

    def test_double_denials_bare_quotes_renewed_claims_and_other_fields_fail(self):
        patches = [
            {'plain_summary': prefix + DENIAL + '。'} for prefix in ('不是', '并非', '不能说', '不代表', '不能保证', '不', '未')
        ] + [
            {'plain_summary': '不是非推断为零风险。'},
            {'plain_summary': '除非推断为零风险。'},
            {'plain_summary': '材料称“' + DENIAL + '”。'},
            {'plain_summary': '“未知条件，' + DENIAL + '”。'},
            {'plain_summary': '材料称"' + DENIAL + '"。'},
            {'plain_summary': DENIAL + '，但报名零风险。'},
            {'plain_summary': DENIAL + '。事实上报名完全可逆。'},
            {'plain_summary': DENIAL + '或保证无损失。'},
            {'plain_summary': DENIAL + '，报名无损失。'},
            {'plain_summary': DENIAL + '。', 'explanation': '报名零风险。'},
            {'plain_summary': DENIAL + '。', 'actions': ['报名完全可逆。']},
            {'plain_summary': DENIAL + '。', 'professional_appendix': '报名无损失。'},
        ]
        for index, patch in enumerate(patches):
            with self.subTest(patch=patch): self.execute('unsafe-' + str(index), unsafe=True, patch=patch)

    def test_current_source_and_saved_negative_fact_cannot_authorize_positive_guarantee(self):
        self.execute('negative-current-source-positive', unsafe=True,
            message='请依据西方星盘讨论2026-10-11的学习主题。未知条件，' + DENIAL + '。',
            patch={'plain_summary': '报名零风险。'})
        source = self.service.memory.receive(self.owner, content='请记住：' + DENIAL + '。',
            source_id='saved-negative-source', case_ids=[self.case])
        receipt = self.service.memory.save_fact(self.owner, 'self', source['id'], DENIAL,
            'background', case_id=self.case, operation_id='saved-negative-fact')
        self.assertEqual(receipt['write_status'], 'saved')
        self.execute('negative-saved-source-positive', unsafe=True,
            patch={'plain_summary': '报名零风险。'})
        self.assertIn(receipt['fact_id'], self.model.seen_fact_ids)


if __name__ == '__main__':
    unittest.main()
