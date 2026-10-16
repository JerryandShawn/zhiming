"""Typed model proposals through real Core execution and disposable PostgreSQL."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
import uuid

from psycopg import sql
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from test_core_memory import test_dsn as pg_dsn
from test_core_pg_channels import FixtureModel
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import MemoryProposal, Intake, InvalidAnswer
from mingjing_core.repositories.postgres import PostgresRepository


SUPPORTED_FIELDS = {
    'name', 'gender', 'birth.solar_datetime', 'birth.location.lng',
    'birth.location.lat', 'birth.location.city', 'birth.location.name',
    'birth.timezone_offset', 'birth.time_unknown', 'birth.time_uncertainty_minutes',
    'birth.precision', 'birth.interval_start', 'birth.interval_end',
}


class ProposalProvider(FixtureModel):
    """Only generated model values are replaced; all business methods are real."""
    def __init__(self):
        super().__init__()
        self.proposal = None
        self.intake_schemas = []
        self.instructions = []

    def generate(self, **kwargs):
        result = super().generate(**kwargs)
        if kwargs['purpose'] == 'intake':
            self.intake_schemas.append(deepcopy(kwargs['schema']))
            self.instructions.append(kwargs['payload']['instruction'])
            result['output']['proposals'] = [deepcopy(self.proposal)] if self.proposal else []
        return result


class MemoryProposalContract(unittest.TestCase):
    def test_schema_uses_existing_field_enum_and_explains_plain_and_missing_inputs(self):
        schema = Intake.model_json_schema()
        field = schema['$defs']['MemoryProposal']['properties']['field']
        self.assertEqual(set(field['anyOf'][0]['enum']), SUPPORTED_FIELDS)
        self.assertEqual(field['anyOf'][1], {'type': 'null'})
        self.assertIn('field/value均为null', field['description'])
        self.assertIn('不得扩写', schema['$defs']['MemoryProposal']['properties']['value']['description'])
        missing = schema['$defs']['ConsultationPlan']['properties']['missing_inputs']['description']
        self.assertIn('无法执行', missing)
        self.assertIn('可选细化信息', missing)

    def test_ordinary_fields_and_values_are_null_not_silently_dropped(self):
        base = {'quote': '我不能上夜班', 'category': '约束'}
        accepted = MemoryProposal.model_validate(base)
        self.assertEqual((accepted.field, accepted.value), (None, None))
        for category in ('偏好', '约束', '背景', '目标', '事件', 'constraint'):
            for fields in ({'field': 'schedule.night_shift', 'value': '全天仅工作白班'},
                           {'field': None, 'value': '全天仅工作白班'}):
                with self.subTest(category=category, fields=fields):
                    with self.assertRaises(ValidationError):
                        MemoryProposal.model_validate(dict(base, category=category, **fields))
        profile = MemoryProposal.model_validate({'quote': '请保存：时区8', 'category': '出生资料',
                                                'field': 'birth.timezone_offset', 'value': 8})
        self.assertEqual(profile.value, 8)
        # Existing authorized profile facts may use the background category;
        # a model category does not replace the program's sensitive-data gate.
        compatible = MemoryProposal.model_validate({'quote': '请保存：时区8', 'category': '背景',
            'field': 'birth.timezone_offset', 'value': 8})
        self.assertEqual(compatible.value, 8)


class CoreMemoryProposalPG(unittest.TestCase):
    def setUp(self):
        self.schema = 'test_memory_proposal_' + uuid.uuid4().hex[:16]
        self.repo = PostgresRepository(pg_dsn(), schema=self.schema, max_size=4)
        self.repo.ensure_owner('alpha')
        self.repo.ensure_owner('beta')
        self.provider = ProposalProvider()
        self.service = ConsultationService(self.repo, model=self.provider)

    def tearDown(self):
        with self.repo.connection() as connection:
            runs = connection.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for run in runs:
            for epoch in range(run['retry_epoch'] + 1):
                self.service.runtime.purge(run['id'], epoch)
        with self.repo.connection() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def run_message(self, operation, message, proposal):
        self.provider.proposal = proposal
        run = self.service.submit(owner='alpha', request_id=operation, message=message, depth='fast')
        return run, self.service.execute('alpha', run['id'])

    def test_actual_failed_proposal_stops_at_typed_boundary_one_charge_no_fact(self):
        proposal = {'quote': '我不能上夜班', 'category': '约束', 'field': 'schedule.night_shift',
                    'value': '不能上夜班，安排需限定在白天时段'}
        self.provider.proposal = proposal
        run = self.service.submit(owner='alpha', request_id='invalid-real-shape',
            message='请记住：我不能上夜班，工作需限定在白天时段。', depth='fast')
        with self.assertRaises(InvalidAnswer):
            self.service.execute('alpha', run['id'])
        current = self.repo.fetch_run('alpha', run['id'])
        self.assertEqual((current['status'], current['calls'], current['attempts']), ('failed', 1, 1))
        self.assertIsNone(current['result'])
        self.assertEqual(self.repo.list('alpha', 'fact'), [])
        self.assertEqual(self.repo.list('alpha', 'consent'), [])
        self.assertEqual([request['purpose'] for request in self.provider.requests], ['intake'])
        diagnosis = self.repo.list('alpha', 'model_call')[0]
        self.assertEqual((diagnosis['status'], diagnosis['failure_code']), ('failed', 'MODEL_OUTPUT_CONTRACT'))
        self.assertNotIn(proposal['quote'], json.dumps(diagnosis, ensure_ascii=False))
        with self.repo.connection() as connection:
            count = connection.execute(sql.SQL('SELECT count(*) AS n FROM {} WHERE owner=%s AND run_id=%s').format(
                self.repo.table('core_model_charges')), ('alpha', run['id'])).fetchone()['n']
        self.assertEqual(count, 1)
        self.assertEqual(self.repo.list('beta', 'fact'), [])

    def test_plain_constraint_exact_quote_saved_receipt_and_stable_service_replay(self):
        message = '请记住：我不能上夜班。'
        proposal = {'quote': '我不能上夜班', 'category': '约束', 'field': None, 'value': None}
        run, result = self.run_message('valid-plain', message, proposal)
        self.assertEqual(result['validation']['status'], 'validated')
        receipt = result['memory_receipts'][0]
        self.assertEqual(receipt['write_status'], 'saved')
        facts = self.repo.list('alpha', 'fact')
        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertEqual((fact['content'], fact['field'], fact['value']), (proposal['quote'], None, None))
        self.assertEqual(fact['kind'], 'constraint')
        source = self.service.memory.get_source('alpha', fact['source_refs'][0]['message_id'])
        self.assertEqual(source['content'], message)
        self.assertEqual(fact['source_refs'][0]['quote'], proposal['quote'])
        repeated = self.service.submit(owner='alpha', request_id='valid-plain', message=message, depth='fast')
        self.assertEqual(repeated['id'], run['id'])
        self.assertEqual(self.service.execute('alpha', repeated['id']), result)
        self.assertEqual(len(self.repo.list('alpha', 'fact')), 1)
        self.assertEqual(len(self.repo.list('alpha', 'message')), 1)
        self.assertEqual(len(self.provider.requests), 2)
        schema = self.provider.intake_schemas[0]
        self.assertEqual(set(schema['$defs']['MemoryProposal']['properties']['field']['anyOf'][0]['enum']), SUPPORTED_FIELDS)
        instruction = self.provider.instructions[0]
        for phrase in ('历史既有资料仅作参考', '不得重复提取', '逐字连续原文',
                       'field和value必须均为null', '可选细化信息不列入', '现有信息足以继续时返回[]'):
            self.assertIn(phrase, instruction)

    def test_historical_quote_and_expanded_structured_value_keep_existing_reference_guards(self):
        old = self.service.memory.receive('alpha', content='我不能上夜班', source_id='historical-quote')
        for operation, message, proposal in (
            ('historical-only', '这轮只询问合成阅读计划', {'quote': old['content'], 'category': '约束', 'field': None, 'value': None}),
            ('expanded-profile', '请保存：姓名为合成甲', {'quote': '请保存：姓名为合成甲', 'category': '出生资料',
                'field': 'name', 'value': '合成甲，安排需限定白天'}),
        ):
            with self.subTest(operation=operation):
                self.provider.proposal = proposal
                run = self.service.submit(owner='alpha', message=message, request_id=operation, depth='fast')
                with self.assertRaises(InvalidAnswer):
                    self.service.execute('alpha', run['id'])
                self.assertEqual(self.repo.fetch_run('alpha', run['id'])['calls'], 1)
                self.assertEqual(self.repo.list('alpha', 'fact'), [])
                self.assertEqual(self.repo.list('alpha', 'consent'), [])
        self.assertEqual(self.service.memory.get_source('alpha', old['id'])['content'], old['content'])

    def test_sensitive_profile_pending_without_authorization_and_saved_with_exact_authorization(self):
        for operation, quote, expected in (
            ('pending-profile', '我的出生时间为1998-03-12 08:15', 'pending_confirmation'),
            ('authorized-profile', '请保存我的出生时间为1998-03-12 08:15', 'saved'),
        ):
            with self.subTest(operation=operation):
                proposal = {'quote': quote, 'category': '出生资料', 'field': 'birth.solar_datetime',
                            'value': '1998-03-12 08:15'}
                if expected == 'saved':
                    proposal['category'] = '背景'
                run, result = self.run_message(operation, quote, proposal)
                self.assertEqual(result['memory_receipts'][0]['write_status'], expected)
                self.assertEqual(self.repo.fetch_run('alpha', run['id'])['status'], 'succeeded')
                facts = self.repo.list('alpha', 'fact')
                self.assertEqual(len(facts), 1 if expected == 'saved' else 0)
                if facts:
                    self.assertEqual((facts[0]['field'], facts[0]['value']), ('birth.solar_datetime', '1998-03-12 08:15'))
        self.assertEqual(self.repo.list('beta', 'fact'), [])


if __name__ == '__main__':
    unittest.main()
