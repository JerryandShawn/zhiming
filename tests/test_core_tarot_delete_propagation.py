"""Deletion over real PostgreSQL, official checkpoints and the real Core service.

Only the model provider is substituted. Outbox state is exercised through its
real claim/receipt API; no external message is sent.
"""
import json
import os
from pathlib import Path
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from test_core_memory import test_dsn as pg_dsn
from test_core_pg_channels import FixtureModel
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.adapters.web import create_app
from mingjing_core.adapters.tarot import IdempotencyConflict
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict
from mingjing_core.repositories.postgres import PostgresRepository


MARKER = 'SYNTHETIC_DELETED_INTERPRETATION_721'


class Provider(FixtureModel):
    def __init__(self):
        super().__init__()
        self.during_call = None
        self.during_purpose = None

    def generate(self, **kwargs):
        response = super().generate(**kwargs)
        if kwargs['purpose'] == 'synthesis':
            response['output']['plain_summary'] = MARKER
        callback = self.during_call
        if callback and (self.during_purpose is None or self.during_purpose == kwargs['purpose']):
            self.during_call = None
            callback()
        return response


class TarotDeletePropagation(unittest.TestCase):
    def setUp(self):
        self.schema = 'test_tarot_delete_' + uuid.uuid4().hex[:16]
        self.repo = PostgresRepository(pg_dsn(), schema=self.schema, max_size=4)
        for owner in ('alpha', 'beta'):
            self.repo.ensure_owner(owner)
            self.repo.bind_channel(owner, 'feishu', 'ou_synthetic_' + owner)
        self.provider = Provider()
        self.service = ConsultationService(self.repo, model=self.provider)
        self.environment = patch.dict(os.environ, {'MINGJING_TOKEN': 'synthetic-alpha',
            'MINGJING_OWNER_ID': 'alpha', 'ZHIMING_TOKEN_OWNERS': '{"synthetic-beta":"beta"}'})
        self.environment.start()
        # Routes are real, while the independent background recovery loop is
        # unnecessary for these explicitly awaited requests/race scenarios.
        self.client = TestClient(create_app(self.service))
        self.headers = {'X-Token': 'synthetic-alpha'}

    def tearDown(self):
        with self.repo.transaction() as conn:
            runs = conn.execute(sql.SQL('SELECT id,retry_epoch FROM {}').format(self.repo.table('core_runs'))).fetchall()
        for run in runs:
            for epoch in range(run['retry_epoch'] + 1):
                self.service.runtime.purge(run['id'], epoch)
        self.client.close()
        self.environment.stop()
        with self.repo.transaction() as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def post(self, path, value, owner='alpha'):
        return self.client.post(path, json=value, headers={'X-Token': 'synthetic-' + owner})

    def get(self, path, owner='alpha'):
        return self.client.get(path, headers={'X-Token': 'synthetic-' + owner})

    def delete(self, draw_id, request_id='delete-one', owner='alpha'):
        return self.client.request('DELETE', '/api/tarot/draws/' + draw_id,
            json={'request_id': request_id}, headers={'X-Token': 'synthetic-' + owner})

    def draw(self, key='draw-one', owner='alpha', case_id=None, manual=False):
        value = {'idempotency_key': key, 'question': '合成牌阵问题 ' + key,
                 'background': '合成牌阵专属背景 ' + key,
                 'draw_source': 'manual' if manual else 'auto', 'spread_id': 'reflect3'}
        if case_id:
            value['case_id'] = case_id
        if manual:
            from hermes.tarot_deck import CARDS
            value['manual_cards'] = [{'card_id': card['card_id']} for card in CARDS[:3]]
        response = self.post('/api/tarot/draws', value, owner)
        self.assertEqual(response.status_code, 200, response.text)
        draw = response.json()['draw']
        self.service.tarot.reveal(owner, draw['id'])
        return self.service.tarot.get(owner, draw['id']), value

    def completed(self, draw, key='reading-one', owner='alpha'):
        response = self.post('/api/tarot/draws/' + draw['id'] + '/readings',
                             {'request_id': key, 'depth': 'fast'}, owner)
        self.assertIn('"type": "result"', response.text, response.text)
        reading = self.service.tarot.list_readings(owner, draw['id'])[-1]
        self.assertEqual(reading['status'], 'success')
        return self.repo.fetch_run(owner, reading['execution_snapshot']['run_id']), reading

    def assert_checkpoints_absent(self, run_id, epochs=1):
        for epoch in range(epochs):
            thread = run_id + ':e' + str(epoch)
            self.assertIsNone(self.service.runtime.checkpointer.get_tuple({'configurable': {'thread_id': thread}}))
            with self.repo.connection() as conn:
                for table in ('checkpoints', 'checkpoint_blobs', 'checkpoint_writes'):
                    row = conn.execute(sql.SQL('SELECT count(*) AS n FROM public.{} WHERE thread_id=%s').format(
                        sql.Identifier(table)), (thread,)).fetchone()
                    self.assertEqual(row['n'], 0, table)

    def delivery(self, run_id, status):
        now = datetime.now(timezone.utc)
        outbox = self.service.outbox.prepare_delivery(owner='alpha', run_id=run_id,
            business_id='delete-probe:' + status, channel='feishu', target='ou_synthetic_alpha', due=now-timedelta(seconds=1))
        if status != 'pending':
            claim = self.service.outbox.claim_delivery(owner='alpha', outbox_id=outbox['id'], now=now)
            if status != 'sending':
                self.service.outbox.record_delivery(owner='alpha', outbox_id=outbox['id'], status=status,
                    message_id='om_synthetic_receipt' if status == 'sent' else None, claim_token=claim['claim_token'])
        return outbox['id']

    def test_http_completed_reading_delete_erases_history_results_reports_and_all_epochs(self):
        saved = self.service.memory.receive('alpha', content='我喜欢独立的合成阅读习惯', source_id='global-source')
        fact = self.service.memory.save_fact('alpha', 'self', saved['id'], saved['content'])
        self.repo.put('alpha', 'legacy', 'legacy-independent', {'content': '独立旧资料'})
        independent = self.service.submit(owner='alpha', message='独立合成事项', request_id='independent', depth='fast')
        self.service.execute('alpha', independent['id'])
        draw, create_payload = self.draw()
        run, reading = self.completed(draw)
        beta_draw, _ = self.draw(owner='beta')
        beta_run, _ = self.completed(beta_draw, owner='beta')
        self.assertIn(MARKER, json.dumps(self.get('/api/history').json()))
        self.repo.put('alpha', 'report', 'derived-report', {'run_id': run['id'], 'content': MARKER, 'guidance': run['result']})
        # Exercise each delivery state independently through actual outbox APIs.
        delivery_ids = {}
        for state in ('pending', 'sent', 'uncertain', 'sending'):
            # Sending/uncertain blocks creation of another business for the same
            # run; the pending rows are all prepared before any claim.
            delivery_ids[state] = self.service.outbox.prepare_delivery(owner='alpha', run_id=run['id'],
                business_id='delete-probe:' + state, channel='feishu', target='ou_synthetic_alpha',
                due=datetime.now(timezone.utc)-timedelta(seconds=1))['id']
        for state in ('sent', 'uncertain', 'sending'):
            claim = self.service.outbox.claim_delivery(owner='alpha', outbox_id=delivery_ids[state])
            if state != 'sending':
                self.service.outbox.record_delivery(owner='alpha', outbox_id=delivery_ids[state], status=state,
                    message_id='om_synthetic_receipt' if state == 'sent' else None, claim_token=claim['claim_token'])
        with self.repo.transaction('alpha') as conn:
            conn.execute(sql.SQL('UPDATE {} SET retry_epoch=1 WHERE owner=%s AND id=%s').format(
                self.repo.table('core_runs')), ('alpha', run['id']))
        checkpoint = {'v': 1, 'id': str(uuid.uuid4()), 'ts': datetime.now(timezone.utc).isoformat(),
            'channel_values': {'run_id': run['id']}, 'channel_versions': {'run_id': '1'}, 'versions_seen': {}}
        self.service.runtime.checkpointer.put({'configurable': {'thread_id': run['id'] + ':e1', 'checkpoint_ns': ''}},
                                              checkpoint, {}, {'run_id': '1'})
        response = self.delete(draw['id'])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['affected_ids'], [run['id']])
        current = self.repo.fetch_run('alpha', run['id'])
        self.assertEqual((current['status'], current['error']), ('revoked', 'TAROT_DELETED'))
        self.assertEqual((current['result'], current['request'], current['checkpoint']), (None, {}, {}))
        self.assertEqual(current['calls'], run['calls'])
        for url in ('/api/history', '/api/chat/reading:reading-one', '/api/runs/' + run['id']):
            data = self.get(url).json()
            if url == '/api/history':
                self.assertFalse(any(row.get('meta', {}).get('meta', {}).get('core_run', {}).get('run_id') == run['id'] for row in data))
            else:
                self.assertNotIn(MARKER, json.dumps(data))
        self.assert_checkpoints_absent(run['id'], 2)
        for kind in ('runtime_step', 'interpretive_claim', 'artifact', 'model_call', 'report'):
            rows = self.repo.list('alpha', kind, include_deleted=True)
            self.assertFalse(any(row.get('run_id') == run['id'] for row in rows))
        self.assertEqual(self.repo.get('alpha', 'report', 'derived-report', include_deleted=True)['status'], 'deleted')
        with self.repo.connection() as conn:
            outboxes = conn.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND run_id=%s').format(
                self.repo.table('delivery_outbox')), ('alpha', run['id'])).fetchall()
        for outbox in outboxes:
            original = next(state for state, ident in delivery_ids.items() if ident == outbox['id'])
            self.assertEqual(outbox['status'], 'sent' if original == 'sent' else 'uncertain' if original in ('sending', 'uncertain') else 'cancelled')
            self.assertEqual(outbox['payload'], {})
            if original == 'sent':
                self.assertEqual(outbox['receipt'], 'om_synthetic_receipt')
            with self.assertRaises(LeaseConflict):
                self.service.outbox.claim_delivery(owner='alpha', outbox_id=outbox['id'])
        self.assertEqual(self.repo.get('alpha', 'fact', fact['id'])['content'], saved['content'])
        self.assertEqual(self.repo.get('alpha', 'message', saved['id'])['content'], saved['content'])
        self.assertEqual(self.repo.get('alpha', 'legacy', 'legacy-independent')['content'], '独立旧资料')
        self.assertEqual(self.repo.fetch_run('alpha', independent['id'])['status'], 'succeeded')
        self.assertEqual(self.repo.fetch_run('beta', beta_run['id'])['status'], 'succeeded')
        self.assertEqual(self.delete(draw['id']).json(), response.json())
        with self.assertRaises(IdempotencyConflict):
            self.service.tarot.request_result('alpha', 'create', 'draw-one')
        with self.assertRaises(IdempotencyConflict):
            self.service.tarot.request_result('alpha', 'reading', 'reading-one')
        with self.assertRaises(LeaseConflict):
            self.repo.prepare_retry('alpha', run['id'])
        replay = self.post('/api/tarot/draws', create_payload)
        self.assertNotEqual(replay.status_code, 200)

    def test_late_provider_return_cannot_write_usage_output_or_checkpoint_after_delete(self):
        for purpose, calls in (('intake', 1), ('synthesis', 2)):
            with self.subTest(purpose=purpose):
                draw, _ = self.draw('draw-race-' + purpose)
                reading = self.service.tarot.begin_reading('alpha', draw['id'], model='synthetic', prompt_version='core3.0',
                    context_snapshot={}, idempotency_key='race-reading-' + purpose)['reading']
                operation = 'race-' + purpose
                run = self.service.submit(owner='alpha', message='请解读固定牌阵，合成删除竞争', request_id=operation,
                    mode='tarot', depth='fast', draw_id=draw['id'], reading_id=reading['id'])
                responses = []
                self.provider.during_purpose = purpose
                self.provider.during_call = lambda: responses.append(self.delete(draw['id'], 'delete-' + operation))
                with self.assertRaises(LeaseConflict):
                    self.service.execute('alpha', run['id'])
                self.assertEqual(responses[0].status_code, 200, responses[0].text)
                current = self.repo.fetch_run('alpha', run['id'])
                self.assertEqual((current['status'], current['calls']), ('revoked', calls))
                self.assertIsNone(current['result'])
                for kind in ('runtime_step', 'model_call'):
                    self.assertFalse(any(row.get('run_id') == run['id'] for row in self.repo.list('alpha', kind)))
                self.assert_checkpoints_absent(run['id'])
                with self.assertRaises(LeaseConflict):
                    self.repo.claim_run('alpha', run['id'])
                self.assertEqual(self.get('/api/chat/' + operation).json()['answer'], '')

    def test_actual_history_and_parent_dependencies_revoke_but_keep_authentic_chat_source(self):
        draw, _ = self.draw()
        first, _ = self.completed(draw)
        dependent = self.service.submit(owner='alpha', message='请继续核对现实合成事项', request_id='dependent',
            case_ids=[draw['case_id']], depth='fast', parent_run=first['id'])
        self.service.execute('alpha', dependent['id'])
        intake = self.repo.get('alpha', 'runtime_step', dependent['id'] + ':e0:intake')['output']
        authentic = self.service.memory.get_source('alpha', intake['source_id'])
        self.assertEqual(authentic['channel'], 'web')
        self.assertIn('message:' + authentic['id'], self.repo.fetch_run('alpha', dependent['id'])['dependencies'])
        response = self.delete(draw['id'])
        self.assertEqual(set(response.json()['affected_ids']), {first['id'], dependent['id']})
        self.assertEqual(self.service.memory.get_source('alpha', authentic['id'])['content'], authentic['content'])
        self.assertEqual(self.repo.fetch_run('alpha', dependent['id'])['status'], 'revoked')
        self.assert_checkpoints_absent(dependent['id'])

    def test_auto_case_projection_and_source_fact_removed_independent_events_retained(self):
        draw, _ = self.draw()
        run, _ = self.completed(draw)
        source = next(row for row in self.repo.list('alpha', 'message') if row.get('channel') == 'tarot')
        # This is an actual user-authorized saved quote from the dedicated
        # original; no synthetic business commit or fabricated run is used.
        # Explicit quoted save authorization is unnecessary for low sensitivity.
        fact = self.service.memory.save_fact('alpha', 'self', source['id'], source['content'], case_id=draw['case_id'])
        self.assertEqual(fact['write_status'], 'saved')
        case = self.repo.get('alpha', 'case', draw['case_id'])
        event = self.post('/api/cases/' + case['id'] + '/events', {'request_id': 'independent-event',
            'expected_revision': case['revision'], 'kind': 'progress', 'content': '独立真实合成进度'}).json()
        response = self.delete(draw['id'])
        self.assertEqual(response.status_code, 200, response.text)
        snap = self.service.memory.snapshot('alpha', case_ids=[case['id']])
        self.assertNotIn(draw['question'], json.dumps(snap, ensure_ascii=False))
        projected = self.repo.get('alpha', 'case', case['id'])
        self.assertTrue(projected['source_revoked'])
        self.assertEqual(projected['source_refs'], [])
        self.assertEqual(self.repo.get('alpha', 'feedback', event['id'])['content'], '独立真实合成进度')
        self.assertEqual(self.repo.get('alpha', 'fact', fact['id'], include_deleted=True)['status'], 'deleted')
        with self.assertRaises(EvidenceError):
            self.service.memory.receive('alpha', content=source['content'], channel='tarot', source_id=run['operation_id'])

    def test_manual_revision_family_delete_and_queued_lease_fence_are_owner_scoped(self):
        draw, _ = self.draw(manual=True)
        from hermes.tarot_deck import CARDS
        revised = self.service.tarot.revise_manual('alpha', draw['id'],
            [{'card_id': card['card_id']} for card in CARDS[3:6]], '合成录入更正', 'manual-revision')
        self.service.tarot.reveal('alpha', revised['id'])
        first = self.service.submit(owner='alpha', message='请解读第一个合成牌阵', request_id='queued-first',
                                    mode='tarot', depth='fast', draw_id=draw['id'])
        second = self.service.submit(owner='alpha', message='请解读修订合成牌阵', request_id='queued-revised',
                                     mode='tarot', depth='fast', draw_id=revised['id'])
        foreign = self.delete(draw['id'], owner='beta')
        self.assertNotEqual(foreign.status_code, 200)
        self.assertEqual(self.repo.fetch_run('alpha', first['id'])['status'], 'queued')
        receipt = self.delete(revised['id']).json()
        self.assertEqual(set(receipt['deleted_ids']), {draw['id'], revised['id']})
        self.assertEqual(set(receipt['affected_ids']), {first['id'], second['id']})
        for run in (first, second):
            with self.assertRaises(LeaseConflict):
                self.service.execute('alpha', run['id'])
            self.assertEqual(self.repo.fetch_run('alpha', run['id'])['calls'], 0)
        with self.assertRaises(IdempotencyConflict):
            self.service.tarot.request_result('alpha', 'revise', 'manual-revision')

    def test_direct_service_delete_purges_checkpoints_and_keeps_independent_case_edit(self):
        draw, _ = self.draw()
        run, _ = self.completed(draw)
        case = self.repo.get('alpha', 'case', draw['case_id'])
        changed = self.client.patch('/api/cases/' + case['id'], headers=self.headers, json={
            'request_id': 'rename-independent', 'expected_revision': case['revision'],
            'changes': {'title': '独立修改后的事项名称', 'goal': '独立的合成现实目标'}})
        self.assertEqual(changed.status_code, 200, changed.text)
        receipt = self.service.tarot.delete('alpha', draw['id'])
        self.assertEqual(receipt['affected_ids'], [run['id']])
        self.assert_checkpoints_absent(run['id'])
        current = self.repo.get('alpha', 'case', case['id'])
        self.assertEqual(current['title'], '独立修改后的事项名称')
        self.assertEqual(current['state']['goal'], '独立的合成现实目标')
        self.assertEqual(current['source_refs'], [])
        self.assertTrue(current['source_revoked'])


if __name__ == '__main__':
    unittest.main()
