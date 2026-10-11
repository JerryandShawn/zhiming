"""Real PostgreSQL tarot/outbox regression; transports are always synthetic."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone, date
import json
import os
from pathlib import Path
import sys
import unittest
import uuid

from psycopg import sql
from psycopg.types.json import Jsonb

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.adapters.tarot import TarotService,IdempotencyConflict
from mingjing_core.adapters.delivery import OutboxService,DeliveryUncertain
from mingjing_core.adapters.channels.delivery import CoreDeliveryWorker,TransportRejected
from mingjing_core.adapters.channels.reports import report_schedule
from mingjing_core.domain.contracts import ScopeError,RevisionConflict,EvidenceError


class PostgreSQLEffects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn=os.environ.get('CORE_TEST_DSN')
        if not cls.dsn:
            configuration=ROOT.parent/'dev-environment.json'
            if configuration.is_file():cls.dsn=json.loads(configuration.read_text())['dsn']
        if not cls.dsn:raise unittest.SkipTest('requires disposable PostgreSQL CORE_TEST_DSN')

    def setUp(self):
        self.schema='test_effect_'+uuid.uuid4().hex[:16]
        self.repo=PostgresRepository(self.dsn,schema=self.schema)
        self.repo.ensure_owner('alice');self.repo.ensure_owner('bob')
        self.repo.put('alice','case','case-study',{'title':'学习安排','state':{},'status':'open'})
        self.repo.bind_channel('alice','feishu','ou_fixture_alice')
        self.repo.bind_channel('bob','feishu','ou_fixture_bob')
        self.cards=TarotService(self.repo)
        self.outbox=OutboxService(self.repo)

    def tearDown(self):
        assert self.schema.startswith('test_effect_')
        with self.repo.transaction() as c:c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.repo.close()

    def draw(self,key='draw-first',**changes):
        args=dict(subject_id='self',case_id='case-study',question='我怎样安排学习时间？',idempotency_key=key,context_snapshot={'revision':self.repo.get_revision('alice'),'fact_ids':['fact-synthetic'],'background':'需要保留休息'})
        args.update(changes)
        return self.cards.create_draw('alice',**args)

    def saved_run(self,operation='report-fixture',cases=None):
        """Repository/outbox unit fixture, not an end-to-end service execution."""
        row=self.repo.begin_run('alice',operation,{'case_ids':cases or [],'mode':'scheduled_report'},subject='self',case_ids=cases or [])
        dependencies=self.repo.versions('alice','self',cases or [])
        self.repo.set_run_dependencies('alice',row['id'],dependencies,row['lease_token'])
        result={'schema_version':'core3.0','plain_summary':'先核对本期现实安排。','answer':'先核对本期现实安排。','actions':['先确认时间。'],
                'decision_options':[],'cited_fact_ids':[],'cited_claim_ids':[],
                'validation':{'valid':True,'schema':'core3.0','status':'validated'},'meta':{'subject_id':'self','case_ids':cases or [],'core_run':{'run_id':row['id'],'dependencies':dependencies}}}
        self.repo.commit_run('alice',row['id'],dependencies,result,row['lease_token'])
        return row['id']

    def pending(self,operation='report-fixture',cases=None,business='daily-fixture'):
        run_id=self.saved_run(operation,cases)
        return self.outbox.prepare_delivery(owner='alice',run_id=run_id,business_id=business,channel='feishu',target='ou_fixture_alice',due=datetime.now(timezone.utc)-timedelta(seconds=1))

    def test_full_deck_hidden_cards_and_frozen_restart(self):
        draw=self.draw(draw_source='pick')['draw']
        self.assertEqual(len(draw['backs']),78)
        self.assertNotIn('card_id',json.dumps(draw['backs']))
        self.assertEqual(draw['cards'],[])
        back=draw['backs'][0]['back_id']
        selected=self.cards.select('alice',draw['id'],back,'selection-1')
        self.assertNotIn('card_id',selected['cards'][0])
        self.assertEqual(self.cards.select('alice',draw['id'],back,'selection-1')['selected_count'],1)
        self.assertEqual(TarotService(self.repo).get('alice',draw['id'])['cards'],selected['cards'])

    def test_reused_draw_has_independent_request_fingerprint(self):
        first=self.draw()['draw']
        second=self.draw('draw-second',question='同一学习事项，周末怎样安排？')
        self.assertTrue(second['reused']);self.assertEqual(second['draw']['id'],first['id'])
        self.assertEqual(self.draw('draw-second',question='同一学习事项，周末怎样安排？')['draw']['id'],first['id'])
        with self.assertRaises(IdempotencyConflict):self.draw('draw-second',question='改成另一个问题')

    def test_concurrent_selection_is_atomic(self):
        draw=self.draw(draw_source='pick')['draw'];back=draw['backs'][0]['back_id']
        with ThreadPoolExecutor(max_workers=2) as pool:
            values=list(pool.map(lambda key:self.cards.select('alice',draw['id'],back,key),['click-a','click-b']))
        self.assertTrue(all(v['selected_count']==1 for v in values))

    def test_choice_frozen_manual_revision_and_reading_failure(self):
        draw=self.draw(spread_id='choice5',options={'A':'保持原安排','B':'减少课程'})['draw']
        self.assertEqual(draw['options']['B'],'减少课程')
        draw=self.cards.reveal('alice',draw['id'])
        version=self.cards.begin_reading('alice',draw['id'],model='fixture',prompt_version='core3',context_snapshot={'supplement':'现实资料'},idempotency_key='reading-first')['reading']
        self.cards.finish_reading('alice',version['id'],error='synthetic failure')
        retry=self.cards.begin_reading('alice',draw['id'],model='fixture',prompt_version='core3',context_snapshot={'supplement':'现实资料'},idempotency_key='reading-retry')['reading']
        self.assertEqual(retry['version'],2);self.assertEqual(self.cards.get('alice',draw['id'])['cards'],draw['cards'])
        manual=self.draw('manual-first',draw_source='manual',explicit_new=True,manual_cards=[{'card_id':c['card_id'],'orientation':c['orientation']} for c in draw['cards'][:3]])['draw']
        actual=self.cards.reveal('alice',manual['id'])
        revised=self.cards.revise_manual('alice',manual['id'],[{'card_id':c['card_id'],'orientation':'upright'} for c in actual['cards']],'实体牌方向录错','manual-revision')
        self.assertEqual(revised['revision'],2);self.assertEqual(revised['revision_root'],manual['id']);self.assertEqual(revised['previous_draw_id'],manual['id'])

    def test_delete_and_source_revoke_prevent_retry_resurrection(self):
        draw=self.draw()['draw'];self.cards.delete('alice',draw['id'])
        with self.assertRaises(IdempotencyConflict):self.draw()
        fresh=self.draw('another-request')['draw'];self.cards.purge_context('alice',['fact-synthetic'])
        self.assertTrue(self.cards.get('alice',fresh['id'])['context_revoked'])
        with self.assertRaises(IdempotencyConflict):self.cards.request_result('alice','create','another-request')
        with self.assertRaises(KeyError):self.cards.get('bob',fresh['id'])

    def test_wrong_cards_and_unconfigured_reading_are_not_success(self):
        draw=self.cards.reveal('alice',self.draw()['draw']['id'])
        fake=[dict(c) for c in draw['cards']];fake[0]['card_id']='fake-card'
        with self.assertRaises(ValueError):self.cards.validate_cards('alice',draw['id'],fake,draw['deck_version'])
        reading=self.cards.begin_reading('alice',draw['id'],model='unconfigured',prompt_version='core3',context_snapshot={},idempotency_key='no-model')['reading']
        self.cards.recover_running('alice',0)
        self.assertEqual(self.cards.get_reading('alice',reading['id'])['status'],'failed')

    def test_scoped_versions_block_stale_but_allow_unrelated_change(self):
        pending=self.pending(cases=['case-study'])
        with self.repo.transaction('alice') as c:self.repo.bump_revision(c,'alice',case_id='unrelated-case')
        claim=self.outbox.claim_delivery(owner='alice',outbox_id=pending['id'])
        self.outbox.record_delivery(owner='alice',outbox_id=pending['id'],status='rejected',claim_token=claim['claim_token'])
        with self.repo.transaction('alice') as c:self.repo.bump_revision(c,'alice',case_id='case-study')
        with self.assertRaises(RevisionConflict):self.outbox.claim_delivery(owner='alice',outbox_id=pending['id'])
        self.assertEqual(self.outbox.status('alice')['rows'][0]['status'],'stale')

    def test_outbox_rechecks_owner_target_and_due_time(self):
        run_id=self.saved_run()
        with self.assertRaises(ScopeError):self.outbox.prepare_delivery(owner='alice',run_id=run_id,business_id='fake-target',channel='feishu',target='ou_fixture_bob')
        pending=self.outbox.prepare_delivery(owner='alice',run_id=run_id,business_id='future',channel='feishu',target='ou_fixture_alice',due=datetime.now(timezone.utc)+timedelta(days=1))
        with self.assertRaises(Exception):self.outbox.claim_delivery(owner='alice',outbox_id=pending['id'])

    def test_uncertain_never_blindly_retries_then_receipt_reconciles(self):
        pending=self.pending();calls=[]
        def timeout(target,content,business):calls.append(business);raise TimeoutError('synthetic only')
        worker=CoreDeliveryWorker(self.outbox,timeout)
        row=asyncio.run(worker.deliver(owner='alice',outbox_id=pending['id']))
        self.assertEqual(row['status'],'uncertain')
        with self.assertRaises(DeliveryUncertain):asyncio.run(worker.deliver(owner='alice',outbox_id=pending['id']))
        with self.assertRaises(DeliveryUncertain):self.outbox.prepare_delivery(owner='alice',run_id=pending['run_id'],business_id='changed-business',channel='feishu',target='ou_fixture_alice')
        with self.assertRaises(EvidenceError):self.outbox.reconcile_delivery(owner='alice',outbox_id=pending['id'],delivered=False)
        self.outbox.reconcile_delivery(owner='alice',outbox_id=pending['id'],delivered=True,message_id='fixture-receipt',evidence_ref='fixture-provider-record')
        self.assertEqual(len(calls),1);self.assertEqual(self.outbox.status('alice')['rows'][0]['status'],'sent')

    def test_concurrent_claim_and_crash_recovery_are_not_duplicate_delivery(self):
        pending=self.pending()
        def claim(_):
            try:return self.outbox.claim_delivery(owner='alice',outbox_id=pending['id'])
            except DeliveryUncertain:return None
        with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(claim,range(2)))
        self.assertEqual(sum(c is not None for c in claims),1)
        self.outbox.recover_claims('alice',datetime.now(timezone.utc)+timedelta(minutes=5))
        self.assertEqual(self.outbox.status('alice')['rows'][0]['status'],'uncertain')

    def test_original_shanghai_schedule(self):
        self.assertEqual(report_schedule('daily',date(2026,10,11))['prepare_at'].strftime('%H:%M'),'06:45')
        self.assertEqual(report_schedule('daily',date(2026,10,11))['deliver_at'].strftime('%H:%M'),'07:00')
        self.assertEqual(report_schedule('weekly',date(2026,10,11))['deliver_at'].hour,20)
        self.assertIsNone(report_schedule('weekly',date(2026,10,12)))
        self.assertEqual(report_schedule('monthly',date(2026,11,1))['deliver_at'].hour,9)
        self.assertEqual(report_schedule('quarterly',date(2027,1,1))['deliver_at'].hour,10)


if __name__=='__main__':unittest.main()
