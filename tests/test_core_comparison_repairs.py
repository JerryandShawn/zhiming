"""Recorded synthetic comparison repairs through real Core/PG; model-only substitution."""
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
from tools.compare_core_providers import FACTS, PROFILE_ITEMS, history_fixture, card_projection


FIXTURE = Path(__file__).parent / 'fixtures' / '104_comparison_repairs.json'
GUARANTEE_ISSUE = '费用、退出和风险条件未经确认，不能承诺完全可逆或无损失'
SAVE_ISSUE = '保存或删除提示必须由实际程序回执生成'


class RecordedComparisonModel:
    def __init__(self, evidence):
        self.evidence = evidence
        self.sample = evidence['samples'][0]
        self.mapping = {}
        self.calls = []
        self.outputs = {}
        self.final_patch = None

    def generate(self, **kwargs):
        purpose = kwargs['purpose']; data = kwargs['payload']['reference_data']
        self.calls.append(purpose)
        raw = self.sample['outputs']
        for output in raw.values():
            for proposal in output.get('proposals', []):
                if proposal.get('case_id'): self.mapping[proposal['case_id']] = self.case_id
        if data.get('facts'):
            chosen = [next(f for f in data['facts'] if f.get('content') == text) for _, text in FACTS]
            for output in raw.values():
                cited = output.get('cited_fact_ids', [])
                matched = data['facts'] if len(cited) == len(data['facts']) else chosen
                if len(cited) == 3:
                    matched = chosen + [next(f for f in data['facts'] if f.get('content', '').startswith('A班次尚未确认'))]
                for old, fact in zip(cited, matched): self.mapping[old] = fact['id']
        if purpose.startswith('specialist:'):
            system = purpose.split(':', 1)[1]
            claims = [c for c in data['claims'] if c['system'] == system]
            for old, claim in zip(raw[purpose]['claim_ids'], claims): self.mapping[old] = claim['claim_id']
        def bind(value):
            if isinstance(value, dict): return {key: bind(item) for key, item in value.items()}
            if isinstance(value, list): return [bind(item) for item in value]
            if isinstance(value, str):
                for old, new in self.mapping.items(): value = value.replace(old, new)
            return value
        output = bind(deepcopy(raw[purpose]))
        if self.final_patch is not None and purpose in ('synthesis', 'repair'):
            output.update(plain_summary=self.final_patch, explanation='', professional_appendix='', caveats=[],
                          actions=['核实实际条件'], follow_up='',
                          decision_options=[{key: '待核实' for key in option} for option in output['decision_options'][:2]])
        self.outputs[purpose] = deepcopy(output)
        return {'output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1}, 'model': 'synthetic-recorded-comparison'}


class ObservedService(ConsultationService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.validation_attempts = []

    def _validate(self, owner, run, final):
        issues = super()._validate(owner, run, final)
        self.validation_attempts.append(list(issues))
        return issues


class RecordedComparisonRepairs(unittest.TestCase):
    def setUp(self):
        self.schema = 'test_comparison_repair_' + uuid.uuid4().hex[:16]
        self.repo = PostgresRepository(pg_dsn(), schema=self.schema, max_size=4)
        self.owner = 'synthetic-comparison'; self.repo.ensure_owner(self.owner)
        self.evidence = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.model = RecordedComparisonModel(self.evidence)
        self.service = ObservedService(self.repo, model=self.model)
        self.case = self.service.memory.create_case(self.owner, 'self', '合成工作安排比较')['id']
        self.model.case_id = self.case
        for index, (kind, text) in enumerate(FACTS):
            source = self.service.memory.receive(self.owner, content=text, source_id='fixed-fact-' + str(index), case_ids=[self.case])
            self.service.memory.save_fact(self.owner, 'self', source['id'], text, kind, case_id=self.case)
        for index, (field, value) in enumerate(PROFILE_ITEMS):
            text = '请保存 ' + field + '=' + str(value)
            source = self.service.memory.receive(self.owner, content=text, source_id='fixed-profile-' + str(index))
            receipt = self.service.memory.save_fact(self.owner, 'self', source['id'], text, 'profile', field=field, value=value)
            self.assertEqual(receipt['write_status'], 'saved')
        for row in history_fixture():
            self.service.memory.receive(self.owner, content=row['content'], source_id=row['id'], role=row['role'],
                conversation_id='synthetic-conversation', case_ids=[self.case], at=row['at'])
        self.draw = None

    def tearDown(self):
        with self.repo.connection() as connection:
            runs = connection.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for run in runs:
            for epoch in range(run['retry_epoch'] + 1): self.service.runtime.purge(run['id'], epoch)
        with self.repo.connection() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def consult(self, request_id):
        tarot = self.model.sample['scenario'] == 'tarot'
        if tarot and self.draw is None:
            draw = self.service.tarot.create_draw(self.owner, subject_id='self', case_id=self.case,
                question=self.evidence['questions']['tarot'], spread_id='reflect3', draw_source='manual',
                manual_cards=self.evidence['fixed_cards'], idempotency_key='fixed-manual-draw')['draw']
            self.draw = self.service.tarot.reveal(self.owner, draw['id'])
        run = self.service.submit(owner=self.owner, message=self.evidence['questions']['tarot' if tarot else 'decision'],
            conversation_id='synthetic-conversation', request_id=request_id, case_ids=[self.case], depth='standard',
            selection={'date': '2026-10-11', 'systems': ['tarot'] if tarot else []},
            draw_id=self.draw['id'] if self.draw else None)
        return run, self.service.execute(self.owner, run['id'])

    def test_both_full_original_decision_repairs_commit_after_three_calls_and_replay(self):
        original_hash = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertTrue(self.evidence['synthetic_only'])
        for sample in self.evidence['samples'][:2]:
            with self.subTest(arm=sample['arm']):
                self.model.sample = sample
                before = len(self.model.calls)
                run, result = self.consult('recorded-' + sample['arm'])
                current = self.repo.fetch_run(self.owner, run['id'])
                self.assertEqual((current['status'], current['calls'], current['repair_used']), ('succeeded', 3, True))
                self.assertEqual(self.model.calls[before:], ['intake', 'synthesis', 'repair'])
                self.assertIn(GUARANTEE_ISSUE, self.service.validation_attempts[-2])
                self.assertEqual(self.service.validation_attempts[-1], [])
                self.assertEqual(result['explanation'], self.model.outputs['repair']['explanation'])
                self.assertEqual(result['plain_summary'], self.model.outputs['repair']['plain_summary'])
                self.assertTrue(result['validation']['valid'])
                self.assertEqual(self.service.execute(self.owner, run['id']), result)
                self.assertEqual(len(self.model.calls), before + 3)
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), original_hash)

    def test_original_single_tarot_save_assertion_remains_rejected_without_receipt(self):
        self.model.sample = self.evidence['samples'][2]
        with self.assertRaises(InvalidAnswer): self.consult('recorded-tarot-save')
        with self.repo.connection() as connection:
            run = connection.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND operation_id=%s').format(
                self.repo.table('core_runs')), (self.owner, 'recorded-tarot-save')).fetchone()
        self.assertEqual((run['status'], run['calls'], run['repair_used']), ('failed', 4, True))
        self.assertIsNone(run['result'])
        self.assertEqual(self.service.validation_attempts, [[SAVE_ISSUE], [SAVE_ISSUE]])
        self.assertEqual(card_projection(self.service.tarot.get(self.owner, self.draw['id'])), self.evidence['fixed_cards'])

    def test_bounded_adjacent_denials_and_explicit_old_wording_withdrawals(self):
        passages = (
            '不能保证"完全无损失"。', '等待核实并非保证无损失。',
            '本答复不再承诺任何选项"完全可逆"或"零成本"。',
            '不能假定为完全可逆。', "本答复不承诺任何路径'完全可逆'或'无损失'。",
            '此前表述中"完全可逆、不花钱、不锁定任何选项"过于绝对，本轮修正为低风险行动。',
            '已修复上轮错误：删除了"完全可逆""不花钱、不锁定任何选项"等绝对化表述。',
            '不能事先承诺无损失。', '不再承诺任何路径“完全可逆”或“无损失”。',
        )
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                self.model.final_patch = passage
                before = len(self.model.calls)
                run, result = self.consult('bounded-denial-' + str(index))
                self.assertTrue(result['validation']['valid'])
                self.assertEqual(len(self.model.calls) - before, 2)
                self.assertFalse(self.repo.fetch_run(self.owner, run['id'])['repair_used'])

    def test_direct_guarantees_double_denials_and_new_assertions_still_fail(self):
        passages = (
            '报名完全无损失。', '不是不能保证"完全无损失"。', '不是并非保证无损失。',
            '并非不再承诺任何选项"完全可逆"。', "不能不承诺任何路径'完全可逆'或'无损失'。",
            '不可能不能假定为完全可逆。', '不能假定为完全可逆，但事实上报名完全可逆。',
            "本答复不承诺任何路径'完全可逆'。当前报名完全可逆。",
            "本答复不承诺任何路径'完全可逆'或保证'无损失'。",
            '不能事先承诺无损失，但B无损失。', '并非保证无损失，却保证完全可逆。',
            '此前表述中"完全可逆"并非过于绝对。', '此前表述中"完全可逆"不是过于绝对。',
            '此前表述中"完全可逆"过于绝对，但现在报名完全可逆。',
            '未修复上轮错误：删除了"完全可逆"等表述。',
            '并非已修复上轮错误：删除了"完全可逆"等表述。',
            '已修复上轮错误：没有删除了"完全可逆"等表述。',
            '已修复上轮错误：并非删除了"完全可逆"等表述。',
            '删除了"完全可逆"。', '已修复上轮错误：删除了报价"完全可逆"。',
            '已修复上轮错误：删除了"完全可逆"，但现在完全可逆。',
        )
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                self.model.final_patch = passage
                before = len(self.model.calls)
                with self.assertRaises(InvalidAnswer): self.consult('unsafe-denial-' + str(index))
                self.assertEqual(len(self.model.calls) - before, 3)
                self.assertIn(GUARANTEE_ISSUE, self.service.validation_attempts[-1])


if __name__ == '__main__':
    unittest.main()
