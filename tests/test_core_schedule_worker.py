"""Calendar effects through real PostgreSQL, Core, HTTP and the report worker.

Only provider responses and the final external transport are synthetic. No
configured model or Feishu transport is constructed by these regressions.
"""
import asyncio
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mingjing_core.adapters.core_report_worker import CoreReportWorker
from mingjing_core.adapters.web import create_app
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.report_schedules import ReportScheduleService
from mingjing_core.domain.consultation import ModelUnavailable, ModelFailureReason
from mingjing_core.domain.report_schedules import SHANGHAI
from mingjing_core.repositories.postgres import PostgresRepository
from test_core_pg_channels import FixtureModel


def at(value):
    return datetime.fromisoformat(value).replace(tzinfo=SHANGHAI)


class ControlledModel(FixtureModel):
    """Failure and schedule races occur at the provider boundary only."""
    def __init__(self, *, fail_synthesis_once=False, on_synthesis=None):
        super().__init__()
        self.fail_synthesis_once = fail_synthesis_once
        self.on_synthesis = on_synthesis

    def generate(self, **kwargs):
        response = super().generate(**kwargs)
        if kwargs['purpose'] == 'synthesis':
            if self.on_synthesis:
                callback, self.on_synthesis = self.on_synthesis, None
                callback()
            if self.fail_synthesis_once:
                self.fail_synthesis_once = False
                raise ModelUnavailable('Synthetic network failure', reason=ModelFailureReason.NETWORK)
        return response


class RecordingTransport:
    def __init__(self, *, uncertain_once=False, on_send=None):
        self.calls = []
        self.uncertain_once = uncertain_once
        self.on_send = on_send

    def __call__(self, target, content, delivery_id):
        self.calls.append({'target': target, 'content': content, 'id': delivery_id})
        if self.on_send:
            self.on_send()
        if self.uncertain_once:
            self.uncertain_once = False
            raise TimeoutError('Synthetic ambiguous delivery')
        return 'synthetic-receipt-' + str(len(self.calls))


class CoreScheduleWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get('CORE_TEST_DSN')
        settings = ROOT.parent / 'dev-environment.json'
        if not cls.dsn and settings.is_file():
            cls.dsn = json.loads(settings.read_text(encoding='utf-8'))['dsn']
        if not cls.dsn:
            raise unittest.SkipTest('requires disposable PostgreSQL')

    def setUp(self):
        self.schema = 'test_schedule_worker_' + uuid.uuid4().hex[:16]
        self.repo = PostgresRepository(self.dsn, schema=self.schema, max_size=4, max_running=1)
        self.repo.ensure_owner('alice')
        self.repo.bind_channel('alice', 'feishu', 'ou_schedule_alice')
        self.schedules = ReportScheduleService(self.repo)
        self.model = ControlledModel()
        self.service = ConsultationService(self.repo, model=self.model)
        self.transport = RecordingTransport()
        self.worker = CoreReportWorker(self.service, self.transport)

    def tearDown(self):
        # Public LangGraph tables are shared by isolated test schemas; remove
        # only the uniquely identified threads belonging to this test's runs.
        for run in self.runs():
            for epoch in range(run['retry_epoch'] + 1):
                self.service.runtime.purge(run['id'], epoch)
        assert self.schema.startswith('test_schedule_worker_')
        with self.repo.transaction() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def configure(self, kind, *, external=None):
        self.external = external or kind + '-alice'
        self.kind = kind
        self.repo.bind_channel('alice', 'report', self.external, binding_kind='task')
        config = {'report_pipeline': {'enabled': True, 'jobs': [{
            'id': self.external, 'kind': kind, 'channel': 'feishu', 'target': 'ou_schedule_alice',
        }]}}
        with self.repo.transaction('alice') as connection:
            connection.execute(sql.SQL('UPDATE {} SET settings=%s WHERE id=%s').format(
                self.repo.table('core_owners')), (Jsonb(config), 'alice'))
        self.assertEqual(self.schedules.seed_defaults('alice'), {'created': 1, 'existing': 0, 'unconfigured': 3})
        self.assertEqual(self.schedules.effective('alice', kind)['revision'], 1)

    def change(self, *, now=None, **changes):
        return self.schedules.patch('alice', {
            'kind': self.kind, 'request_id': 'schedule-command-' + uuid.uuid4().hex,
            'expected_revision': self.schedules.effective('alice', self.kind)['revision'], **changes,
        }, now=now)

    def tick(self, value):
        return asyncio.run(self.worker.tick('alice', at(value)))

    def rows(self):
        with self.repo.connection() as connection:
            return connection.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s ORDER BY due,id').format(
                self.repo.table('delivery_outbox')), ('alice',)).fetchall()

    def runs(self):
        with self.repo.connection() as connection:
            return connection.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s ORDER BY created_at,id').format(
                self.repo.table('core_runs')), ('alice',)).fetchall()

    def business(self, day):
        return 'report:' + self.external + ':' + self.kind + ':' + day

    def test_time_change_invalidates_pending_and_rebuilds_exact_business_once(self):
        self.configure('daily')
        self.assertEqual(self.tick('2026-10-11T06:45')['prepared'], 1)
        before = self.rows()[0]
        old_run = self.runs()[0]
        self.assertEqual(before['status'], 'pending')
        self.assertEqual(before['due'], at('2026-10-11T07:00'))
        self.assertEqual(before['dependencies']['report_schedule:daily'], 1)
        self.change(time='08:00', now=at('2026-10-11T06:46'))
        invalid = self.rows()[0]
        self.assertEqual((invalid['id'], invalid['status'], invalid['payload'], invalid['attempts']),
                         (before['id'], 'stale', {}, 0))
        self.assertEqual(invalid['due'], before['due'])
        self.assertFalse(self.repo.verify_versions('alice', old_run['state_version']))
        self.assertEqual(self.tick('2026-10-11T07:00')['prepared'], 0)
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.tick('2026-10-11T07:45')['prepared'], 1)
        rebuilt = self.rows()[0]
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(rebuilt['id'], before['id'])
        self.assertNotEqual(rebuilt['run_id'], old_run['id'])
        self.assertEqual(rebuilt['due'], at('2026-10-11T08:00'))
        self.assertEqual(rebuilt['dependencies']['report_schedule:daily'], 2)
        self.assertEqual(self.tick('2026-10-11T08:00')['sent'], 1)
        sent = self.rows()[0]
        requests = len(self.model.requests)
        self.change(time='09:00', now=at('2026-10-11T08:01'))
        self.assertEqual(self.tick('2026-10-11T08:45')['prepared'], 0)
        self.assertEqual(self.tick('2026-10-11T09:00')['sent'], 0)
        self.assertEqual(len(self.model.requests), requests)
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(self.rows()[0]['receipt'], sent['receipt'])

    def test_disabled_policy_creates_no_run_or_delivery(self):
        self.configure('daily')
        policy = self.change(enabled=False, now=at('2026-10-11T06:00'))
        self.assertEqual(policy['status'], 'paused')
        self.assertIsNone(policy['next_delivery'])
        self.assertEqual(self.tick('2026-10-11T07:00'), {'enabled': False, 'prepared': 0, 'sent': 0, 'failures': 0})
        self.assertEqual(self.runs(), [])
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.model.requests, [])
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.repo.list('alice', 'draw'), [])

    def test_disabling_existing_pending_report_clears_payload_and_prevents_send(self):
        self.configure('daily')
        self.tick('2026-10-11T06:45')
        previous = self.rows()[0]
        requests = len(self.model.requests)
        self.change(enabled=False, now=at('2026-10-11T06:46'))
        self.assertEqual(self.tick('2026-10-11T07:00')['sent'], 0)
        row = self.rows()[0]
        self.assertEqual((row['id'], row['status'], row['payload'], row['due']),
                         (previous['id'], 'stale', {}, previous['due']))
        self.assertEqual(len(self.model.requests), requests)
        self.assertEqual(self.transport.calls, [])

    def test_midnight_preparation_uses_next_day_and_never_delivers_early(self):
        self.configure('daily')
        self.change(time='00:05', now=at('2026-11-01T20:00'))
        self.assertEqual(self.tick('2026-11-01T23:49')['prepared'], 0)
        self.assertEqual(self.tick('2026-11-01T23:50')['prepared'], 1)
        row = self.rows()[0]
        self.assertEqual(row['business_id'], self.business('2026-11-02'))
        self.assertEqual(row['due'], at('2026-11-02T00:05'))
        manifest = self.repo.get('alice', 'report', row['business_id'])
        self.assertEqual(manifest['prepare_at'], at('2026-11-01T23:50').isoformat())
        self.assertEqual(manifest['date'], '2026-11-02')
        self.assertEqual(manifest['timezone'], 'Asia/Shanghai')
        for value in ('2026-11-01T23:59', '2026-11-02T00:04'):
            self.assertEqual(self.tick(value)['sent'], 0)
            self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.tick('2026-11-02T00:05')['sent'], 1)
        self.assertEqual(self.tick('2026-11-02T00:06')['sent'], 0)
        self.assertEqual(len(self.runs()), 1)
        self.assertEqual(len(self.transport.calls), 1)

    def test_technical_retry_retains_run_call_limit_and_already_charged_calls(self):
        self.configure('daily')
        self.model.fail_synthesis_once = True
        self.assertEqual(self.tick('2026-10-11T06:45')['failures'], 1)
        initial = self.runs()[0]
        self.assertEqual((initial['status'], initial['calls'], initial['call_limit']), ('failed', 2, 6))
        self.assertEqual(initial['operation_id'], self.business('2026-10-11') + ':schedule:1')
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.tick('2026-10-11T06:54')['prepared'], 0)
        self.assertEqual(len(self.model.requests), 2)
        self.assertEqual(self.tick('2026-10-11T06:55')['prepared'], 1)
        retried = self.runs()[0]
        self.assertEqual(len(self.runs()), 1)
        self.assertEqual((retried['id'], retried['operation_id'], retried['call_limit']),
                         (initial['id'], initial['operation_id'], 6))
        self.assertEqual((retried['status'], retried['attempts'], retried['calls']), ('succeeded', 2, 3))
        self.assertEqual([item['purpose'] for item in self.model.requests], ['intake', 'synthesis', 'synthesis'])
        state = self.repo.get('alice', 'request', 'report-preparation:' + self.business('2026-10-11') + ':schedule:1')
        self.assertEqual((state['attempts'], state['generation_status']), (2, 'complete'))
        with self.repo.connection() as connection:
            charged = connection.execute(sql.SQL('SELECT count(*) AS count FROM {} WHERE owner=%s AND run_id=%s').format(
                self.repo.table('core_model_charges')), ('alice', initial['id'])).fetchone()['count']
        self.assertEqual(charged, 3)
        self.assertEqual(self.tick('2026-10-11T07:00')['sent'], 1)
        self.assertEqual(self.tick('2026-10-11T07:01')['sent'], 0)

    def test_change_during_generation_cannot_commit_result_manifest_or_outbox(self):
        self.configure('daily')
        self.model.on_synthesis = lambda: self.change(time='08:00', now=at('2026-10-11T06:46'))
        self.assertEqual(self.tick('2026-10-11T06:45')['failures'], 1)
        stale = self.runs()[0]
        self.assertEqual(stale['status'], 'stale')
        self.assertIsNone(stale['result'])
        self.assertFalse(self.repo.verify_versions('alice', stale['state_version']))
        self.assertEqual(self.repo.list('alice', 'report'), [])
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.tick('2026-10-11T07:45')['prepared'], 1)
        runs = self.runs()
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[1]['operation_id'], self.business('2026-10-11') + ':schedule:2')
        self.assertEqual(runs[1]['state_version']['report_schedule:daily'], 2)
        self.assertEqual(runs[0]['calls'], 2)
        self.assertEqual(self.rows()[0]['run_id'], runs[1]['id'])
        self.assertEqual(self.rows()[0]['due'], at('2026-10-11T08:00'))

    def test_schedule_patch_while_transport_sends_is_real_http_409_and_rolls_back(self):
        self.configure('daily')
        self.tick('2026-10-11T06:45')
        policy = self.schedules.effective('alice', 'daily')
        observed = []
        command = {'kind': 'daily', 'request_id': 'sending-change', 'expected_revision': policy['revision'], 'time': '08:00'}
        with patch.dict(os.environ, {'MINGJING_TOKEN': 'synthetic-schedule-token', 'MINGJING_OWNER_ID': 'alice', 'ZHIMING_TOKEN_OWNERS': '{}'}):
            # Avoid entering TestClient's lifespan: no recovery worker runs in
            # this test. Requests still use the genuine application routes.
            client = TestClient(create_app(self.service))
            try:
                def during_send():
                    self.assertEqual(self.rows()[0]['status'], 'sending')
                    response = client.patch('/api/reports/schedules', headers={'X-Token': 'synthetic-schedule-token'}, json=command)
                    observed.append(response.status_code)
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(self.schedules.effective('alice', 'daily')['revision'], policy['revision'])
                self.transport.on_send = during_send
                self.assertEqual(self.tick('2026-10-11T07:00')['sent'], 1)
            finally:
                client.close()
        self.assertEqual(observed, [409])
        self.assertEqual(self.schedules.effective('alice', 'daily')['time'], '07:00')
        self.assertEqual(self.rows()[0]['status'], 'sent')
        with self.repo.connection() as connection:
            receipt = connection.execute(sql.SQL('SELECT receipt FROM {} WHERE owner=%s AND request_key=%s').format(
                self.repo.table('core_mutation_requests')), ('alice', 'sending-change')).fetchone()
        self.assertIsNone(receipt)

    def test_weekday_change_runs_on_chosen_iso_weekday_and_once_per_week(self):
        self.configure('weekly')
        self.change(weekday=1, time='08:15', now=at('2026-11-01T12:00'))
        self.assertEqual(self.tick('2026-11-01T20:00')['prepared'], 0)
        self.assertEqual(self.tick('2026-11-02T08:00')['prepared'], 1)
        self.assertEqual(self.rows()[0]['due'], at('2026-11-02T08:15'))
        self.assertEqual(self.tick('2026-11-02T08:15')['sent'], 1)
        requests = len(self.model.requests)
        self.change(weekday=3, now=at('2026-11-02T08:16'))
        preview = self.schedules.get('alice', 'weekly', now=at('2026-11-03T12:00'))
        self.assertTrue(preview['blocked_current_period'])
        self.assertEqual(preview['next_delivery'], at('2026-11-11T08:15').isoformat())
        self.assertEqual(self.tick('2026-11-04T08:00')['prepared'], 0)
        self.assertEqual(self.tick('2026-11-04T08:15')['sent'], 0)
        self.assertEqual(len(self.model.requests), requests)
        self.assertEqual(self.tick('2026-11-11T08:00')['prepared'], 1)
        self.assertEqual(self.tick('2026-11-11T08:15')['sent'], 1)
        self.assertEqual(len(self.transport.calls), 2)
        self.assertEqual([row['business_id'] for row in self.rows()], [self.business('2026-11-02'), self.business('2026-11-11')])

    def test_month_last_day_handles_thirty_days_and_february(self):
        self.configure('monthly')
        self.change(day='last', time='09:30', now=at('2026-11-01T00:00'))
        for value in ('2026-11-01T09:30', '2026-11-29T09:30'):
            self.assertEqual(self.tick(value)['prepared'], 0)
        self.assertEqual(self.tick('2026-11-30T09:15')['prepared'], 1)
        self.assertEqual(self.tick('2026-11-30T09:30')['sent'], 1)
        self.assertEqual(self.tick('2027-02-27T09:30')['prepared'], 0)
        self.assertEqual(self.tick('2027-02-28T09:15')['prepared'], 1)
        self.assertEqual(self.tick('2027-02-28T09:30')['sent'], 1)
        self.assertEqual([row['due'] for row in self.rows()], [at('2026-11-30T09:30'), at('2027-02-28T09:30')])
        self.assertEqual(len(self.transport.calls), 2)

    def protected_month_or_quarter(self, kind, *, uncertain):
        self.configure(kind)
        hour = 9 if kind == 'monthly' else 10
        self.transport.uncertain_once = uncertain
        original_due = at(f'2026-10-01T{hour:02}:00')
        original_prepare = original_due - timedelta(minutes=15)
        self.assertEqual(asyncio.run(self.worker.tick('alice', original_prepare))['prepared'], 1)
        delivered = asyncio.run(self.worker.tick('alice', original_due))
        self.assertEqual(delivered['sent'], 0 if uncertain else 1)
        original = self.rows()[0]
        self.assertEqual(original['status'], 'uncertain' if uncertain else 'sent')
        calls = len(self.model.requests)
        self.change(day=15, now=at('2026-10-02T12:00'))
        preview = self.schedules.get('alice', kind, now=at('2026-10-14T12:00'))
        next_day = '2026-11-15' if kind == 'monthly' else '2027-01-15'
        self.assertTrue(preview['blocked_current_period'])
        self.assertEqual(preview['next_delivery'], at(f'{next_day}T{hour:02}:00').isoformat())
        self.assertEqual(self.tick(f'2026-10-15T{hour-1:02}:45')['prepared'], 0)
        self.assertEqual(self.tick(f'2026-10-15T{hour:02}:00')['sent'], 0)
        self.assertEqual(len(self.model.requests), calls)
        self.assertEqual(len(self.runs()), 1)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(self.rows()[0]['status'], original['status'])
        self.assertEqual(self.rows()[0]['receipt'], original['receipt'])
        self.assertEqual(self.tick(f'{next_day}T{hour-1:02}:45')['prepared'], 1)
        self.assertEqual(self.tick(f'{next_day}T{hour:02}:00')['sent'], 1)
        self.assertEqual(self.tick(f'{next_day}T{hour:02}:01')['sent'], 0)
        self.assertEqual(len(self.runs()), 2)
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(len(self.transport.calls), 2)
        self.assertEqual(self.rows()[0]['status'], original['status'])
        self.assertEqual(self.rows()[1]['business_id'], self.business(next_day))

    def test_sent_monthly_date_change_applies_only_to_next_month(self):
        self.protected_month_or_quarter('monthly', uncertain=False)

    def test_uncertain_monthly_date_change_never_evades_reconciliation(self):
        self.protected_month_or_quarter('monthly', uncertain=True)

    def test_sent_quarterly_date_change_applies_only_to_next_quarter(self):
        self.protected_month_or_quarter('quarterly', uncertain=False)

    def test_uncertain_quarterly_date_change_applies_only_to_next_quarter(self):
        self.protected_month_or_quarter('quarterly', uncertain=True)

    def test_setting_a_past_delivery_time_applies_tomorrow_without_catchup(self):
        self.configure('daily')
        self.change(time='08:00', now=at('2026-10-11T06:00'))
        command = {'kind': 'daily', 'request_id': 'afternoon-morning-change',
                   'expected_revision': self.schedules.effective('alice', 'daily')['revision'], 'time': '07:00'}
        first = self.schedules.patch('alice', command, now=at('2026-10-11T17:00'))
        self.assertEqual(first['policy_changed_at'], at('2026-10-11T17:00').isoformat())
        self.assertEqual(first['next_delivery'], at('2026-10-12T07:00').isoformat())
        self.assertEqual(self.tick('2026-10-11T17:00')['prepared'], 0)
        self.assertEqual(self.runs(), [])
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.model.requests, [])
        replay = self.schedules.patch('alice', command, now=at('2026-10-11T18:00'))
        self.assertEqual(replay['revision'], first['revision'])
        self.assertEqual(replay['policy_changed_at'], first['policy_changed_at'])
        self.assertEqual(self.repo.get('alice', 'report_schedule', 'daily')['effective_after'], first['policy_changed_at'])
        self.assertEqual(self.tick('2026-10-11T18:00')['sent'], 0)
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.tick('2026-10-12T06:45')['prepared'], 1)
        self.assertEqual(self.rows()[0]['business_id'], self.business('2026-10-12'))
        self.assertEqual(self.tick('2026-10-12T07:00')['sent'], 1)
        self.assertEqual(len(self.runs()), 1)
        self.assertEqual(len(self.transport.calls), 1)


if __name__ == '__main__':
    unittest.main()
