"""Report policy/calendar and authenticated mutation tests on real PostgreSQL."""
import json
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.report_schedules import ReportScheduleService
from mingjing_core.adapters.web import create_app
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, RevisionConflict
from mingjing_core.domain.report_schedules import KINDS, SHANGHAI, default_policy, next_schedule, report_period, schedule_on_day
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_memory import test_dsn
from tests.test_core_pg_channels import FixtureModel


class ReportCalendarTests(unittest.TestCase):
    def test_defaults_preserve_all_original_occurrences(self):
        for kind, expected in (('daily','07:00'),('weekly','20:00'),('monthly','09:00'),('quarterly','10:00')):
            day = date(2026,11,1) if kind!='quarterly' else date(2027,1,1)
            result = schedule_on_day(kind,day)
            self.assertEqual(result['deliver_at'].strftime('%H:%M'), expected)
            self.assertEqual((result['deliver_at']-result['prepare_at']).total_seconds(), 900)
            self.assertEqual(result['timezone'], 'Asia/Shanghai')
        self.assertIsNone(schedule_on_day('weekly',date(2026,10,12)))
        self.assertIsNone(schedule_on_day('monthly',date(2026,10,2)))
        self.assertIsNone(schedule_on_day('quarterly',date(2026,11,1)))

    def test_midnight_month_end_leap_year_and_fixed_quarter_frequency(self):
        policy = dict(default_policy('daily'),time='00:05')
        preview = next_schedule('daily',policy,now=datetime(2026,10,10,15,40,tzinfo=timezone.utc))
        self.assertEqual(preview['deliver_at'].isoformat(), '2026-10-11T00:05:00+08:00')
        self.assertEqual(preview['prepare_at'].isoformat(), '2026-10-10T23:50:00+08:00')
        monthly = dict(default_policy('monthly'),day='last')
        self.assertIsNotNone(schedule_on_day('monthly',date(2028,2,29),monthly))
        self.assertIsNone(schedule_on_day('monthly',date(2028,2,28),monthly))
        self.assertIsNotNone(schedule_on_day('monthly',date(2027,2,28),monthly))
        quarterly = dict(default_policy('quarterly'),day='last')
        self.assertIsNotNone(schedule_on_day('quarterly',date(2027,4,30),quarterly))
        self.assertIsNone(schedule_on_day('quarterly',date(2027,5,31),quarterly))
        weekly = dict(default_policy('weekly'),weekday=1,time='00:05')
        monday = next_schedule('weekly',weekly,now=datetime(2026,10,11,22,tzinfo=SHANGHAI))
        self.assertEqual(monday['deliver_at'].date(),date(2026,10,12))
        self.assertEqual(monday['prepare_at'].date(),date(2026,10,11))
        self.assertEqual(report_period('weekly',date(2027,1,1)),report_period('weekly',date(2026,12,31)))
        self.assertEqual(report_period('quarterly',date(2026,10,1)),report_period('quarterly',date(2026,12,31)))


class ReportSchedulesPostgresTests(unittest.TestCase):
    def setUp(self):
        self.schema = 'test_schedule_' + uuid.uuid4().hex[:16]
        self.repo = PostgresRepository(test_dsn(),schema=self.schema)
        self.addCleanup(self.cleanup)
        self.repo.ensure_owner('alpha');self.repo.ensure_owner('beta')
        self.service = ConsultationService(self.repo,model=FixtureModel())
        self.schedules = ReportScheduleService(self.repo)
        self.environ = patch.dict(os.environ,{'MINGJING_TOKEN':'schedule-alpha', 'MINGJING_OWNER_ID':'alpha',
                                               'ZHIMING_TOKEN_OWNERS':'{"schedule-beta":"beta"}'})
        self.environ.start();self.addCleanup(self.environ.stop)
        self.client = TestClient(create_app(self.service));self.addCleanup(self.client.close)
        self.headers = {'X-Token':'schedule-alpha'}

    def cleanup(self):
        self.assertTrue(self.schema.startswith('test_schedule_'))
        with self.repo.transaction() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def configure(self, *, enabled=True, kinds=KINDS, target='ou_alpha', bind_target=True):
        jobs = [{'id':'schedule-'+kind,'kind':kind,'channel':'feishu','target':target} for kind in kinds]
        with self.repo.transaction('alpha') as connection:
            settings = self.repo.assert_scope('alpha')['settings']
            settings['report_pipeline'] = {'enabled':enabled,'jobs':jobs,'start_at':'2026-10-11T00:00:00+08:00'}
            connection.execute(sql.SQL('UPDATE {} SET settings=%s WHERE id=%s').format(self.repo.table('core_owners')),
                               (Jsonb(settings),'alpha'))
        for job in jobs:self.repo.bind_channel('alpha','report',job['id'],binding_kind='task')
        if bind_target:self.repo.bind_channel('alpha','feishu',target,binding_kind='chat' if target.startswith('oc_') else 'user')

    def command(self, *, kind='daily', revision=1, key=None, **changes):
        return dict(kind=kind,expected_revision=revision,request_id=key or uuid.uuid4().hex,**changes)

    def mutate(self, payload, headers=None):
        return self.client.patch('/api/reports/schedules',json=payload,headers=headers or self.headers)

    def outbox(self, status, *, kind='daily', owner='alpha', day=None):
        """Direct PG state fixture for the schedule transition, never transmitted."""
        ident = uuid.uuid4().hex
        self.outbox_count = getattr(self,'outbox_count',0)+1
        day = day or date(2026,10,11)+timedelta(days=self.outbox_count)
        business = 'report:schedule-'+kind+':'+kind+':'+day.isoformat()
        with self.repo.transaction(owner) as connection:
            connection.execute(sql.SQL('INSERT INTO {}(id,owner,subject,business_id,channel,target,run_id,payload,dependencies,status,due,receipt) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)').format(
                self.repo.table('delivery_outbox')), (ident,owner,'self',business,'feishu','ou_'+owner,
                'synthetic-ledger-only',Jsonb({'body':'SYNTHETIC_PENDING_BODY'}),Jsonb({}),status,
                datetime(2026,10,11,7,tzinfo=SHANGHAI),'synthetic-receipt' if status=='sent' else ''))
        return ident

    def row(self, ident):
        with self.repo.transaction() as connection:
            return connection.execute(sql.SQL('SELECT * FROM {} WHERE id=%s').format(self.repo.table('delivery_outbox')),(ident,)).fetchone()

    def test_read_is_nonmutating_and_unconfigured_owner_cannot_enable_or_bind(self):
        revision = self.repo.get_revision('alpha')
        self.assertEqual(self.client.get('/api/reports/schedules').status_code,401)
        response = self.client.get('/api/reports/schedules',headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        value = response.json()
        self.assertEqual((value['timezone'],value['prepare_minutes']),('Asia/Shanghai',15))
        self.assertEqual(len(value['schedules']),4)
        for item in value['schedules']:
            self.assertEqual((item['configured'],item['initialized'],item['revision'],item['enabled']), (False,False,0,False))
            self.assertEqual(item['status'],'unconfigured')
            self.assertFalse(item['can_modify'])
        denied = self.mutate(self.command(revision=0,enabled=True))
        self.assertEqual(denied.status_code,403,denied.text)
        self.assertEqual(self.repo.get_revision('alpha'),revision)
        self.assertEqual(self.repo.list('alpha','report_schedule'),[])
        with self.repo.transaction() as connection:
            self.assertEqual(connection.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(self.repo.table('core_channels'))).fetchone()['n'],0)

    def test_deployment_seed_is_idempotent_and_preserves_original_paused_defaults(self):
        self.configure(enabled=False)
        self.assertEqual(self.schedules.seed_defaults('alpha'),{'created':4,'existing':0,'unconfigured':0})
        before = self.repo.get_revision('alpha')
        self.assertEqual(self.schedules.seed_defaults('alpha'),{'created':0,'existing':4,'unconfigured':0})
        self.assertEqual(self.repo.get_revision('alpha'),before)
        for item in self.schedules.list('alpha')['schedules']:
            self.assertEqual(item['status'],'paused')
            self.assertEqual(item['time'],default_policy(item['kind'])['time'])
        enabled = self.schedules.patch('alpha',self.command(enabled=True))
        self.assertEqual(enabled['status'],'active')
        self.assertFalse(self.repo.assert_scope('alpha')['settings']['report_pipeline']['enabled'])
        self.assertEqual(self.schedules.seed_defaults('beta'),{'created':0,'existing':0,'unconfigured':4})

    def test_unseeded_verified_binding_can_save_revision_zero_and_foreign_target_cannot(self):
        self.configure(kinds=('daily',),bind_target=False)
        self.assertFalse(self.schedules.effective('alpha','daily')['configured'])
        self.repo.bind_channel('beta','feishu','ou_alpha')
        denied = self.mutate(self.command(revision=0,enabled=True))
        self.assertEqual(denied.status_code,403,denied.text)
        self.assertEqual(self.repo.list('alpha','report_schedule'),[])
        self.configure(kinds=('daily',),target='oc_alpha',bind_target=True)
        self.assertTrue(self.schedules.get('alpha','daily')['can_modify'])
        saved = self.mutate(self.command(revision=0,time='06:55'))
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual((saved.json()['initialized'],saved.json()['revision']),(True,1))
        beta = self.mutate(self.command(revision=0,enabled=True),headers={'X-Token':'schedule-beta'})
        self.assertEqual(beta.status_code,403,beta.text)

    def test_field_permissions_reject_invalid_time_calendar_and_ownership_input(self):
        self.configure();self.schedules.seed_defaults('alpha')
        invalid = ({'time':'24:00'},{'time':'7:00'},{'weekday':True},{'weekday':1},
                   {'day':1},{'owner':'beta'},{'target':'ou_beta'},{'channel':'feishu'},
                   {'frequency':'hourly'},{'timezone':'UTC'},{'enabled':'false'})
        for change in invalid:
            with self.subTest(change=change):
                response = self.mutate(self.command(**change))
                self.assertEqual(response.status_code,422,response.text)
        for day in (29,31,True,'29'):
            response = self.mutate(self.command(kind='monthly',day=day))
            self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.repo.get('alpha','report_schedule','daily')['revision'],1)

    def test_atomic_receipt_cas_cross_kind_conflict_and_replay_returns_current_projection(self):
        self.configure();self.schedules.seed_defaults('alpha')
        first = self.command(key='lost-response',time='08:00')
        saved = self.schedules.patch('alpha',first)
        self.assertEqual(saved['revision'],2)
        revision = self.repo.get_revision('alpha')
        self.assertEqual(self.schedules.patch('alpha',first)['revision'],2)
        self.assertEqual(self.repo.get_revision('alpha'),revision)
        with self.assertRaises(EvidenceError):self.schedules.patch('alpha',dict(first,kind='weekly',weekday=1))
        with self.assertRaises(EvidenceError):self.schedules.patch('alpha',dict(first,time='09:00'))
        with self.assertRaises(RevisionConflict):self.schedules.patch('alpha',self.command(time='09:00'))
        self.schedules.patch('alpha',self.command(revision=2,time='09:00'))
        replay = self.schedules.patch('alpha',first)
        self.assertEqual((replay['time'],replay['revision'],replay['receipt']['revision']),('09:00',3,3))
        with self.repo.transaction('alpha') as connection:
            receipts = connection.execute(sql.SQL('SELECT receipt FROM {} WHERE owner=%s AND operation=%s').format(
                self.repo.table('core_mutation_requests')),('alpha','report-schedules')).fetchall()
        self.assertEqual(len(receipts),2)
        self.assertTrue(all(set(row['receipt'])=={'id','kind','revision','write_status'} for row in receipts))
        self.assertNotIn('09:00',json.dumps(receipts))

    def test_change_stales_only_unsent_matching_kind_and_preserves_sent_uncertain(self):
        self.configure();self.schedules.seed_defaults('alpha')
        ids = {status:self.outbox(status) for status in ('pending','ready','queued','rejected','sent','uncertain')}
        other = self.outbox('pending',kind='weekly')
        foreign = self.outbox('pending',owner='beta')
        self.schedules.patch('alpha',self.command(enabled=False))
        for status, ident in ids.items():
            row = self.row(ident)
            if status in ('sent','uncertain'):
                self.assertEqual(row['status'],status)
                self.assertEqual(row['payload'],{'body':'SYNTHETIC_PENDING_BODY'})
            else:
                self.assertEqual(row['status'],'stale')
                self.assertEqual(row['payload'],{})
                self.assertEqual(row['due'].astimezone(SHANGHAI).hour,7)
        self.assertEqual(self.row(other)['status'],'pending')
        self.assertEqual(self.row(foreign)['status'],'pending')

    def test_sending_rejects_real_change_and_rolls_back_policy_pending_and_receipt(self):
        self.configure();self.schedules.seed_defaults('alpha')
        sending = self.outbox('sending');pending = self.outbox('pending')
        self.assertFalse(self.schedules.get('alpha','daily')['can_modify'])
        response = self.mutate(self.command(key='sending-change',time='08:00'))
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(self.repo.get('alpha','report_schedule','daily')['revision'],1)
        self.assertEqual(self.row(sending)['status'],'sending')
        self.assertEqual(self.row(pending)['status'],'pending')
        with self.repo.transaction('alpha') as connection:
            self.assertEqual(connection.execute(sql.SQL('SELECT count(*) AS n FROM {}').format(self.repo.table('core_mutation_requests'))).fetchone()['n'],0)

    def test_changed_month_day_skips_already_sent_or_uncertain_current_period(self):
        self.configure();self.schedules.seed_defaults('alpha')
        sent = self.outbox('sent',kind='monthly',day=date(2026,10,1))
        now = datetime(2026,10,10,12,tzinfo=SHANGHAI)
        result = self.schedules.patch('alpha',self.command(kind='monthly',day=15),now=now)
        self.assertTrue(result['blocked_current_period'])
        self.assertIn('下期生效',result['status_reason'])
        self.assertEqual(result['next_delivery'],'2026-11-15T09:00:00+08:00')
        self.assertEqual(result['delivery_state']['sent'],1)
        self.assertTrue(self.schedules.protected_period('alpha','monthly',date(2026,10,15)))
        self.assertFalse(self.schedules.protected_period('alpha','monthly',date(2026,11,15)))
        self.assertEqual(self.row(sent)['status'],'sent')
        self.outbox('uncertain',kind='weekly',day=date(2026,10,11))
        weekly = self.schedules.patch('alpha',self.command(kind='weekly',weekday=6),now=now)
        self.assertEqual(weekly['next_delivery'],'2026-10-17T20:00:00+08:00')
        self.assertTrue(weekly['blocked_current_period'])

    def test_schedule_dependency_is_scoped_and_concurrent_revision_has_one_winner(self):
        self.configure();self.schedules.seed_defaults('alpha')
        weekly = self.schedules.effective('alpha','weekly')['dependency']
        daily = self.schedules.effective('alpha','daily')['dependency']
        def update(time):
            try:return self.schedules.patch('alpha',self.command(time=time))
            except RevisionConflict:return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(update,('08:00','09:00')))
        self.assertEqual(sum(value is not None for value in outcomes),1)
        self.assertFalse(self.repo.verify_versions('alpha',daily))
        self.assertTrue(self.repo.verify_versions('alpha',weekly))
        self.assertEqual(self.repo.get('alpha','report_schedule','daily')['revision'],2)

    def test_explicit_change_cutoff_preserves_precision_and_replay_does_not_refresh_it(self):
        self.configure();self.schedules.seed_defaults('alpha')
        self.assertIsNone(self.schedules.effective('alpha','daily')['policy_changed_at'])
        self.assertNotIn('effective_after',self.repo.get('alpha','report_schedule','daily'))
        changed = datetime(2026,10,11,0,5,0,123456,tzinfo=SHANGHAI)
        command = self.command(key='stable-cutoff',time='00:05')
        result = self.schedules.patch('alpha',command,now=changed)
        self.assertEqual(result['policy_changed_at'],changed.isoformat())
        stored = self.repo.get('alpha','report_schedule','daily')
        self.assertEqual(stored['effective_after'],changed.isoformat())
        due = schedule_on_day('daily',changed.date(),self.schedules.effective('alpha','daily'))['deliver_at']
        self.assertLess(due,datetime.fromisoformat(stored['effective_after']))
        revision = self.repo.get_revision('alpha')
        replay = self.schedules.patch('alpha',command,now=changed+timedelta(days=1))
        self.assertEqual(replay['policy_changed_at'],changed.isoformat())
        self.assertEqual(self.repo.get_revision('alpha'),revision)
        self.schedules.patch('alpha',self.command(revision=2,time='00:05'),now=changed+timedelta(days=1))
        self.assertEqual(self.schedules.effective('alpha','daily')['policy_changed_at'],changed.isoformat())
        next_change = changed+timedelta(days=2)
        self.schedules.patch('alpha',self.command(revision=2,time='00:10'),now=next_change)
        self.assertEqual(self.schedules.effective('alpha','daily')['policy_changed_at'],next_change.isoformat())


if __name__=='__main__':unittest.main()
