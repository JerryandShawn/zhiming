"""Full synthetic provider objects through real PG/Core/LangGraph/calculators.

Only model responses are substituted. The original decision synthesis remains
unsafe and must consume the single semantic repair before committing.
"""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
import uuid

from psycopg import sql
from mingjing_core.adapters.channels.reports import CoreReportAdapter
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import InvalidAnswer
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_memory import test_dsn

FIXTURE = Path(__file__).parent / 'fixtures' / '76b_provider_denials.json'
GUARANTEE = '费用、退出和风险条件未经确认，不能承诺完全可逆或无损失'
SAVE = '保存或删除提示必须由实际程序回执生成'


class ObservedService(ConsultationService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.validation_attempts = []

    def _validate(self, owner, run, final):
        issues = super()._validate(owner, run, final)
        self.validation_attempts.append(list(issues))
        return issues


class RecordedProvider:
    def __init__(self, sample, evidence):
        self.sample = sample
        self.evidence = evidence
        self.mapping = {}
        self.calls = []
        self.outputs = {}
        self.unsafe_review = False
        self.invalid_reference = None

    def bind(self, value):
        if isinstance(value, dict): return {key: self.bind(item) for key, item in value.items()}
        if isinstance(value, list): return [self.bind(item) for item in value]
        if isinstance(value, str):
            for old, new in self.mapping.items(): value = value.replace(old, new)
        return value

    def generate(self, **kwargs):
        purpose = kwargs['purpose']; self.calls.append(purpose)
        data = kwargs['payload']['reference_data']
        facts = data.get('facts', [])
        if facts:
            for old, field in self.sample['profile_fact_fields'].items():
                actual = next(f for f in facts if f.get('field') == field)
                self.mapping[old] = actual['id']
            constraint = next(f for f in facts if f.get('content') == self.evidence['constraint'])
            self.mapping[self.sample['constraint_fact_id']] = constraint['id']
        for old in self.sample['original_claims']:
            if purpose.startswith('specialist:') and old['system'] != purpose.split(':', 1)[1]:
                continue
            claims = [c for c in data.get('claims', []) if all(c[k] == old[k]
                      for k in ('system', 'rule_id', 'time_scale'))]
            if data.get('claims'):
                if len(claims) != 1: raise AssertionError('Original claim has no unique actual released rule')
                self.mapping[old['claim_id']] = claims[0]['claim_id']
        output = self.bind(deepcopy(self.sample['outputs'][purpose]))
        if purpose == 'review' and self.unsafe_review:
            output['plain_summary'] += '但现在报名完全可逆。'
        if purpose in ('synthesis', 'review', 'repair') and self.invalid_reference:
            key = 'cited_fact_ids' if self.invalid_reference == 'fact' else 'cited_claim_ids'
            output[key].append('invented-synthetic-' + self.invalid_reference)
        self.outputs[purpose] = deepcopy(output)
        return {'output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1},
                'model': 'synthetic-original-76b-denial-replay'}


class LocalAnswerModel:
    """Synthetic wording only; actual service chooses and verifies references."""
    def __init__(self, passage): self.passage = passage; self.calls = []

    def generate(self, **kwargs):
        purpose = kwargs['purpose']; self.calls.append(purpose)
        data = kwargs['payload']['reference_data']
        if purpose == 'intake':
            output = {'plan': {'mode': 'decision', 'topic': 'study', 'systems': [], 'decision': True,
                'rationale': '合成局部否定测试', 'time_scale': 'natal', 'target_date': '2026-10-11', 'missing_inputs': []},
                'proposals': [], 'retire_fact_ids': [], 'attachment_observations': []}
        else:
            output = {'plain_summary': self.passage, 'explanation': '实际费用和退出条件仍待核实。',
                'actions': ['核对书面条件。'], 'follow_up': '', 'professional_appendix': '', 'caveats': [],
                'decision_options': [{'option': name, 'benefit': '补齐实际信息', 'cost': '查询时间',
                    'risk': '条件未知', 'reversibility': '合同退出规则待确认', 'first_step': '索取书面条款'}
                    for name in ('先核实A', '先核实B')],
                'cited_fact_ids': [f['id'] for f in data.get('facts', [])], 'cited_claim_ids': []}
        return {'output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1}, 'model': 'synthetic-boundary-wording'}


class Provider76bDenialRegression(unittest.TestCase):
    def setUp(self):
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.schema = 'test_76b_provider_denial_' + uuid.uuid4().hex[:16]
        self.repo = PostgresRepository(test_dsn(), schema=self.schema, max_size=4)
        self.owner = 'synthetic-76b'; self.repo.ensure_owner(self.owner)
        self.service = ObservedService(self.repo, model=LocalAnswerModel('先核实真实条件。'))
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
        source = self.service.memory.receive(self.owner, content='请记住：我不能上夜班。', source_id='synthetic-night')
        receipt = self.service.memory.save_fact(self.owner, 'self', source['id'], self.evidence['constraint'],
            'constraint', operation_id='synthetic-night-save')
        self.assertEqual(receipt['write_status'], 'saved'); self.fact_id = receipt['fact_id']

    def tearDown(self):
        with self.repo.connection() as connection:
            runs = connection.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for run in runs:
            for epoch in range(run['retry_epoch'] + 1): self.service.runtime.purge(run['id'], epoch)
        self.assertTrue(self.schema.startswith('test_76b_provider_denial_'))
        with self.repo.connection() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def select(self, scenario):
        sample = next(s for s in self.evidence['samples'] if s['scenario'] == scenario)
        self.model = RecordedProvider(sample, self.evidence); self.service.model = self.model
        return sample

    def consult(self, scenario, operation):
        sample = self.model.sample
        run = self.service.submit(owner=self.owner, message=sample['question'], request_id=operation,
            depth='deep' if scenario == 'fusion' else 'standard')
        return run, self.service.execute(self.owner, run['id'])

    def run_for(self, operation):
        with self.repo.connection() as connection:
            row = connection.execute(sql.SQL('SELECT id FROM {} WHERE owner=%s AND operation_id=%s').format(
                self.repo.table('core_runs')), (self.owner, operation)).fetchone()
        return self.repo.fetch_run(self.owner, row['id'])

    def assert_actual_references(self, run, result, expected_systems):
        calculation = self.service._record(self.owner, run['id'], 'calculation')
        self.assertEqual({c['system'] for c in calculation['claims']}, expected_systems)
        checked = self.service.knowledge.revalidate_claims(calculation['calculation'], calculation['claims'],
            calculation.get('tarot_provenance'))
        self.assertTrue(checked['eligible'])
        self.assertTrue(set(result['cited_fact_ids']) <= {f['id'] for f in self.service.memory.facts(self.owner)})
        self.assertTrue(set(result['cited_claim_ids']) <= {c['claim_id'] for c in calculation['claims']})
        self.assertTrue(result['validation']['valid'])
        self.assertEqual(len(self.service.memory.facts(self.owner)), 7)

    def test_full_original_fusion_review_commits_six_calls_and_all_original_final_stages_validate(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest(); sample = self.select('fusion')
        self.assertTrue(self.evidence['synthetic_only']); self.assertEqual(sample['original_calls'], 7)
        run, result = self.consult('fusion', 'full-original-fusion')
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']), ('succeeded', 6, 10, False))
        self.assertEqual(self.model.calls, ['intake', 'specialist:bazi', 'specialist:ziwei', 'specialist:astro', 'synthesis', 'review'])
        self.assertEqual(self.service.validation_attempts, [[]])
        self.assertEqual(result['plain_summary'], self.model.outputs['review']['plain_summary'])
        self.assert_actual_references(run, result, {'bazi', 'ziwei', 'astro'})
        for purpose in ('synthesis', 'review', 'repair'):
            self.assertEqual(self.service._validate(self.owner, current, self.model.bind(deepcopy(sample['outputs'][purpose]))), [])
        self.assertEqual(self.service.execute(self.owner, run['id']), result); self.assertEqual(len(self.model.calls), 6)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), before)

    def test_unsafe_fusion_review_uses_original_full_repair_once_without_resetting_budget(self):
        self.select('fusion'); self.model.unsafe_review = True
        run, result = self.consult('fusion', 'unsafe-fusion-review')
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['call_limit'], current['repair_used']), ('succeeded', 7, 10, True))
        self.assertEqual(self.service.validation_attempts, [[GUARANTEE], []])
        self.assertEqual(result['plain_summary'], self.model.outputs['repair']['plain_summary'])
        self.assert_actual_references(run, result, {'bazi', 'ziwei', 'astro'})
        self.assertEqual(self.service.execute(self.owner, run['id']), result); self.assertEqual(len(self.model.calls), 7)

    def test_original_decision_true_positive_still_requires_full_original_repair(self):
        self.select('decision'); run, result = self.consult('decision', 'full-original-decision')
        current = self.repo.fetch_run(self.owner, run['id'])
        self.assertEqual((current['status'], current['calls'], current['repair_used']), ('succeeded', 3, True))
        self.assertEqual(self.model.calls, ['intake', 'synthesis', 'repair'])
        self.assertEqual(self.service.validation_attempts, [[GUARANTEE], []])
        self.assertEqual(result['plain_summary'], self.model.outputs['repair']['plain_summary'])
        self.assertEqual(result['cited_fact_ids'], [self.fact_id])
        self.assert_actual_references(run, result, set())
        self.assertIn(GUARANTEE, self.service._validate(self.owner, current, self.model.outputs['synthesis']))
        self.assertEqual(self.service.execute(self.owner, run['id']), result); self.assertEqual(len(self.model.calls), 3)

    def test_original_report_uses_trusted_task_and_real_bazi_without_save_receipt_fabrication(self):
        sample = self.select('report'); self.assertEqual(sample['original_calls'], 4)
        external = 'synthetic-76b-report'; self.repo.bind_channel(self.owner, 'report', external, binding_kind='task')
        adapter = CoreReportAdapter('.', service=self.service)
        result = asyncio.run(adapter.prepare(external_id=external, kind='daily', day='2026-10-12'))
        current = self.repo.fetch_run(self.owner, result['meta']['core_run']['run_id'])
        self.assertEqual((current['status'], current['calls'], current['repair_used']), ('succeeded', 3, False))
        self.assertEqual(self.model.calls, ['intake', 'specialist:bazi', 'synthesis'])
        self.assertEqual(result['plain_summary'], self.model.outputs['synthesis']['plain_summary'])
        self.assertEqual(result['memory_receipts'], [])
        self.assert_actual_references(current, result, {'bazi'})
        self.assertEqual(self.service._validate(self.owner, current, self.model.bind(deepcopy(sample['outputs']['repair']))), [])
        manifest = self.repo.get(self.owner, 'report', result['report']['business_id'])
        self.assertEqual(manifest['content'], result['answer']); self.assertEqual(manifest['run_id'], current['id'])
        self.assertEqual(asyncio.run(adapter.prepare(external_id=external, kind='daily', day='2026-10-12')), result)
        self.assertEqual(len(self.model.calls), 3); self.assertEqual(self.service.outbox.status(self.owner)['rows'], [])

    def local(self, passage, operation):
        self.service.model = LocalAnswerModel(passage)
        run = self.service.submit(owner=self.owner, message='只比较现实条件，不排盘。', request_id=operation, depth='standard')
        return run, self.service.execute(self.owner, run['id'])

    def test_finite_denials_pass_real_service_without_semantic_repair(self):
        passages = ('均不推断为零风险。', '不能推断为零成本或无损失。',
            "任何'可逆''无损失'的判断在条款确认前都不成立。",
            '未声称任何资料已长期保存。', '不暗示任何资料已长期保存。',
            '本答复不包含任何“已记住/已保存/已更新/已删除”状态的声称。')
        for i, passage in enumerate(passages):
            with self.subTest(passage=passage):
                run, result = self.local(passage, 'valid-local-' + str(i)); current = self.repo.fetch_run(self.owner, run['id'])
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('succeeded', 2, False))
                self.assertTrue(result['validation']['valid']); self.assertEqual(result['memory_receipts'], [])

    def test_positive_double_denial_new_object_cross_field_and_malformed_quotes_are_rejected(self):
        passages = ('推断为零风险。', '不是不能推断为无损失。', '不能不推断为完全可逆。',
            '不能推断费用。报名无损失。', '不能推断为无损失，但报名完全可逆。',
            '不能推断费用现在无损失。', '无损失的判断在条款确认前都不是不成立。',
            '无损失的判断在条款确认前都不成立，但现在报名完全可逆。',
            '资料已长期保存。', '不是未声称任何资料已长期保存。',
            '不能不暗示任何资料已长期保存。', '不暗示任何资料，但其他档案已保存。',
            '不暗示任何资料已长期保存，但我已经保存资料。',
            '不暗示任何资料\n资料已长期保存。',
            '本答复不是不包含任何“已记住/已保存/已更新/已删除”状态的声称。',
            '本答复不能不包含任何“已记住/已保存/已更新/已删除”状态的声称。',
            '本答复不包含任何“已记住/已保存资料/已更新/已删除”状态的声称。',
            '本答复不包含任何“已记住/已保存/已更新/已删除”状态的真实证明。',
            '本答复不包含任何\n“已记住/已保存/已更新/已删除”状态的声称。',
            '本答复不包含任何“已记住/已保存/已更新/已删除”状态的声称，但资料已保存。',
            '本答复不包含任何“已记住/已保存/已更新/已删除”状态的声称。仅来自已保存塔罗声明。')
        for i, passage in enumerate(passages):
            with self.subTest(passage=passage):
                operation = 'unsafe-local-' + str(i)
                with self.assertRaises(InvalidAnswer): self.local(passage, operation)
                current = self.run_for(operation)
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('failed', 3, True))
                self.assertIsNone(current['result']); self.assertTrue(self.service.validation_attempts[-1])

    def test_denials_do_not_excuse_invalid_fact_or_claim_ids(self):
        for kind, issue in (('fact', '引用了本轮有效范围之外的事实'), ('claim', '引用了未通过规则核验的声明')):
            with self.subTest(kind=kind):
                self.select('report'); self.model.invalid_reference = kind
                operation = 'invalid-reference-' + kind
                with self.assertRaises(InvalidAnswer): self.consult('report', operation)
                current = self.run_for(operation)
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('failed', 4, True))
                self.assertIn(issue, self.service.validation_attempts[-1]); self.assertIsNone(current['result'])


if __name__ == '__main__': unittest.main()
