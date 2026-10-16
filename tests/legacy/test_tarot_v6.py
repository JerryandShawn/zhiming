import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'hermes'))
from tarot_deck import CARDS,CARD_BY_ID,SPREADS,DECK_VERSION,public_catalog
from tarot_store import TarotDrawService

class TarotDeckTests(unittest.TestCase):
    def test_complete_original_editorial_deck(self):
        self.assertEqual(len(CARDS),78);self.assertEqual(len(CARD_BY_ID),78)
        self.assertEqual(sum(c['group']=='major' for c in CARDS),22)
        for suit in ('wands','cups','swords','pentacles'):
            self.assertEqual([c['number'] for c in CARDS if c.get('suit')==suit],list(range(1,15)))
        for field in ('upright','reversed','misreading','question'):
            self.assertEqual(len({c[field] for c in CARDS}),78)
            self.assertTrue(all(len(c[field])>10 for c in CARDS))
        copy=public_catalog();copy['cards'][0]['name']='changed'
        self.assertEqual(CARDS[0]['name'],'愚人')
        self.assertEqual([len(x['positions']) for x in SPREADS.values()],[1,3,5])

    def test_every_original_asset_exists_and_is_safe_svg(self):
        root=Path(__file__).resolve().parents[1]/'static'/'tarot'
        manifest=json.loads((root/'licenses.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['files']),79)
        hashes=set()
        for name in manifest['files']:
            data=(root/name).read_bytes();element=ET.fromstring(data)
            self.assertTrue(element.tag.endswith('svg'))
            self.assertEqual(element.attrib['viewBox'],'0 0 250 390')
            self.assertFalse(any(e.tag.endswith(('script','image','foreignObject')) for e in element.iter()))
            hashes.add(hashlib.sha256(data).hexdigest())
        self.assertEqual(len(hashes),79)

class TarotStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=TarotDrawService(self.tmp.name,randbelow=lambda n:n-1)
    def tearDown(self):self.tmp.cleanup()
    def create(self,**kwargs):
        args=dict(subject_id='self',case_id='case-a',question='怎样安排学习与休息？',idempotency_key='create-1')
        args.update(kwargs);return self.store.create_draw('alice',**args)
    def ready(self,**kwargs):
        draw=self.create(**kwargs)['draw'];return self.store.reveal('alice',draw['id'])

    def test_auto_is_persisted_before_exposure_and_frozen_on_retry(self):
        first=self.create();draw=first['draw']
        self.assertTrue(first['created']);self.assertEqual(draw['status'],'pending_reveal')
        self.assertEqual(draw['selected_count'],3)
        self.assertTrue(all('card_id' not in x and 'orientation' not in x for x in draw['cards']))
        replay=self.create();self.assertFalse(replay['created']);self.assertEqual(replay['draw']['id'],draw['id'])
        recreated=TarotDrawService(self.tmp.name)
        self.assertEqual(recreated.get('alice',draw['id']),draw)
        reveal=self.store.reveal('alice',draw['id']);again=self.store.reveal('alice',draw['id'])
        self.assertEqual(reveal['cards'],again['cards']);self.assertEqual(reveal['status'],'ready')
        self.assertEqual(len({x['card_id'] for x in reveal['cards']}),3)
        self.assertTrue(all(x['orientation']=='reversed' for x in reveal['cards']))

    def test_meaning_snapshot_does_not_change_after_library_edit(self):
        draw=self.create()['draw']
        original=CARD_BY_ID['major-00']['upright']
        try:
            CARD_BY_ID['major-00']['upright']='模拟未来牌意库改版'
            shown=self.store.reveal('alice',draw['id'])
            self.assertEqual(shown['cards'][0]['card']['upright'],original)
        finally:CARD_BY_ID['major-00']['upright']=original

    def test_unbiased_algorithm_bounds_and_reversals_setting(self):
        bounds=[]
        service=TarotDrawService(self.tmp.name,randbelow=lambda n:(bounds.append(n) or 0))
        draw=service.create_draw('b',subject_id='s',case_id='c',question='问题',reversals=False,idempotency_key='k')['draw']
        self.assertEqual(bounds,list(range(78,1,-1)))
        shown=service.reveal('b',draw['id'])
        self.assertTrue(all(x['orientation']=='upright' for x in shown['cards']))
        self.assertFalse(service.preferences('b')['reversals'])
        self.assertTrue(service.preferences('new-owner')['reversals'])

    def test_pick_back_only_concurrent_double_click_and_refresh(self):
        draw=self.create(draw_source='pick')['draw'];backs=draw['backs']
        self.assertEqual(len(backs),78);self.assertEqual(len({x['back_id'] for x in backs}),78)
        self.assertNotIn('"card_id":',json.dumps(draw));self.assertNotIn('"orientation":',json.dumps(draw))
        ident=draw['id'];back=backs[20]['back_id']
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            responses=list(pool.map(lambda i:self.store.select('alice',ident,back,'double-click-'+str(i)),range(4)))
        self.assertTrue(all(r['selected_count']==1 for r in responses))
        self.assertNotIn('card_id',json.dumps(responses[-1]))
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda i:self.store.select('alice',ident,backs[i]['back_id'],'pick-'+str(i)),range(2)))
        shown=self.store.reveal('alice',ident)
        self.assertEqual([c['position'] for c in shown['cards']],[1,2,3])
        self.assertEqual(len({c['card_id'] for c in shown['cards']}),3)
        with self.assertRaises(ValueError):self.store.select('alice',ident,backs[5]['back_id'],'extra')
        with self.assertRaises(ValueError):self.store.select('alice',ident,backs[2]['back_id'],'pick-0')

    def test_same_case_stage_reuses_including_cancelled_and_new_is_linked(self):
        old=self.create()['draw'];self.store.cancel('alice',old['id'])
        repeat=self.create(idempotency_key='again',question='再抽到好的为止')
        self.assertTrue(repeat['reused']);self.assertEqual(repeat['draw']['id'],old['id'])
        self.assertEqual(repeat['draw']['status'],'cancelled')
        new=self.create(idempotency_key='intentional-new',explicit_new=True)['draw']
        self.assertNotEqual(new['id'],old['id']);self.assertEqual(new['previous_draw_id'],old['id'])
        other=self.create(idempotency_key='new-stage',stage='after-interview')['draw']
        self.assertNotEqual(other['id'],new['id'])

    def test_choice_options_required_frozen_and_manual_unique(self):
        with self.assertRaises(ValueError):self.create(spread_id='choice5')
        with self.assertRaises(ValueError):self.create(spread_id='choice5',options={'A':'相同','B':'相同'})
        options={'A':'先试一周','B':'保持现状','other':['暂缓']};snapshot={'memory_revision':8}
        draw=self.create(spread_id='choice5',options=options,context_snapshot=snapshot)['draw']
        options['A']='已变化';snapshot['memory_revision']=9
        self.assertEqual(self.store.get('alice',draw['id'])['options']['A'],'先试一周')
        self.assertEqual(draw['context_snapshot']['memory_revision'],8)
        with self.assertRaises(ValueError):self.create(idempotency_key='bad-manual',case_id='other',draw_source='manual',manual_cards=[{'card_id':'major-00'}]*3)
        with self.assertRaises(ValueError):self.create(idempotency_key='bad-disable',case_id='other',draw_source='manual',spread_id='focus1',reversals=False,manual_cards=[{'card_id':'major-00','orientation':'reversed'}])

    def test_explicit_manual_correction_retains_versions_and_source(self):
        cards=[{'card_id':'cups-01','orientation':'reversed'}]
        old=self.ready(spread_id='focus1',draw_source='manual',manual_cards=cards)
        corrected=self.store.revise_manual('alice',old['id'],[{'card_id':'cups-02','orientation':'upright'}],'录入时选错了','correct-1')
        self.assertEqual(corrected['revision'],2);self.assertEqual(corrected['previous_draw_id'],old['id'])
        self.assertEqual(corrected['draw_source'],'manual');self.assertEqual(corrected['correction_reason'],'录入时选错了')
        self.assertEqual(self.store.get('alice',old['id'])['cards'][0]['card_id'],'cups-01')
        self.assertEqual(self.store.revise_manual('alice',old['id'],[{'card_id':'cups-02','orientation':'upright'}],'录入时选错了','correct-1')['id'],corrected['id'])
        auto=self.ready(case_id='auto',idempotency_key='auto')
        with self.assertRaises(ValueError):self.store.revise_manual('alice',auto['id'],cards,'试图换牌','bad-correction')

    def test_owner_scope_on_every_state_path(self):
        draw=self.ready();ident=draw['id']
        begin=self.store.begin_reading('alice',ident,model='unconfigured',prompt_version='v1',context_snapshot={},idempotency_key='read')
        rid=begin['reading']['id']
        actions=[lambda:self.store.get('bob',ident),lambda:self.store.select('bob',ident,'x','x'),lambda:self.store.reveal('bob',ident),
                 lambda:self.store.cancel('bob',ident),lambda:self.store.delete('bob',ident),lambda:self.store.get_for_reading('bob',ident),
                 lambda:self.store.get_reading('bob',rid),lambda:self.store.list_readings('bob',ident),
                 lambda:self.store.finish_reading('bob',rid,error='no'),
                 lambda:self.store.begin_reading('bob',ident,model='m',prompt_version='p',context_snapshot={},idempotency_key='read')]
        for action in actions:
            with self.assertRaises(KeyError):action()
        self.assertEqual(self.store.list_draws('bob'),[])

    def test_reading_retry_is_separate_and_does_not_redraw(self):
        draw=self.ready();before=draw['cards'];ident=draw['id']
        args=dict(model='test',prompt_version='v6',context_snapshot={'memory_revision':2},idempotency_key='read-1')
        first=self.store.begin_reading('alice',ident,**args);rid=first['reading']['id']
        self.assertFalse(self.store.begin_reading('alice',ident,**args)['created'])
        failed=self.store.finish_reading('alice',rid,error='AI 解读未配置')
        self.assertEqual(failed['status'],'failed')
        # A late worker must not rewrite a terminal result.
        late=self.store.finish_reading('alice',rid,result={'text':'pretend success'},validation={})
        self.assertEqual(late['status'],'failed')
        second=self.store.begin_reading('alice',ident,**dict(args,idempotency_key='read-2',context_snapshot={'memory_revision':3}))
        self.assertEqual(second['reading']['version'],2)
        validation=self.store.validate_cards('alice',ident,before,DECK_VERSION)
        done=self.store.finish_reading('alice',second['reading']['id'],result={'text':'解释'},validation=validation)
        self.assertEqual(done['status'],'success');self.assertEqual(self.store.get('alice',ident)['cards'],before)
        bad=[dict(x) for x in before];bad[0]['orientation']='upright' if before[0]['orientation']=='reversed' else 'reversed'
        with self.assertRaises(ValueError):self.store.validate_cards('alice',ident,bad,DECK_VERSION)
        with self.assertRaises(ValueError):self.store.validate_cards('alice',ident,before,'wrong-version')
        with self.assertRaises(ValueError):self.store.validate_cards('alice',ident,[before[0]]*3,DECK_VERSION)

    def test_cancel_and_restart_recover_pending_reading_without_redraw(self):
        draw=self.ready();ident=draw['id']
        reading=self.store.begin_reading('alice',ident,model='m',prompt_version='v',context_snapshot={},idempotency_key='r')['reading']
        self.assertEqual(self.store.recover_running('alice',older_than_seconds=0),1)
        self.assertEqual(self.store.get_reading('alice',reading['id'])['status'],'failed')
        self.assertEqual(self.store.get('alice',ident)['cards'],draw['cards'])
        reading2=self.store.begin_reading('alice',ident,model='m',prompt_version='v',context_snapshot={},idempotency_key='r2')['reading']
        self.store.cancel('alice',ident)
        self.assertEqual(self.store.get_reading('alice',reading2['id'])['status'],'failed')
        with self.assertRaises(ValueError):self.store.get_for_reading('alice',ident)

    def test_privacy_delete_clears_snapshots_all_manual_revisions_and_readings(self):
        secret='PRIVATE_TAROT_BODY_7cb2'
        original=self.ready(spread_id='focus1',draw_source='manual',manual_cards=[{'card_id':'major-00'}],question=secret,context_snapshot={'fact':secret})
        revision=self.store.revise_manual('alice',original['id'],[{'card_id':'major-01'}],secret,'revise-key')
        self.store.reveal('alice',revision['id'])
        reading=self.store.begin_reading('alice',revision['id'],model='m',prompt_version='p',context_snapshot={'fact':secret},idempotency_key='reading-key')['reading']
        self.store.finish_reading('alice',reading['id'],result={'text':secret},validation={})
        deleted=self.store.delete('alice',revision['id'])
        self.assertEqual(set(deleted['deleted_ids']),{original['id'],revision['id']})
        self.assertEqual(self.store.list_draws('alice'),[])
        with self.assertRaises(KeyError):self.store.get_reading('alice',reading['id'])
        with self.assertRaises(ValueError):self.create(spread_id='focus1',draw_source='manual',manual_cards=[{'card_id':'major-00'}],question=secret,context_snapshot={'fact':secret})
        with self.store.db() as c:
            dump='\n'.join(c.iterdump())
        self.assertNotIn(secret,dump);self.assertNotIn(secret.encode(),self.store.path.read_bytes())

    def test_retry_lookup_and_revoke_derived_context_without_changing_cards(self):
        self.assertIsNone(self.store.request_result('alice','create','missing'))
        draw=self.ready(context_snapshot={'facts':[{'id':'fact-7','text':'被撤销的背景'}]})
        ident=draw['id'];cards=draw['cards']
        self.assertEqual(self.store.request_result('alice','create','create-1')['draw']['id'],ident)
        self.assertIsNone(self.store.request_result('bob','create','create-1'))
        reading=self.store.begin_reading('alice',ident,model='m',prompt_version='v',context_snapshot={'source_refs':['source:src-2']},idempotency_key='reading')['reading']
        self.assertEqual(self.store.request_result('alice','reading','reading')['reading']['id'],reading['id'])
        self.assertEqual(self.store.purge_context('bob',['fact-7'])['draw_ids'],[])
        purged=self.store.purge_context('alice',['fact-7'])
        self.assertEqual(purged['draw_ids'],[ident]);self.assertEqual(purged['readings_deleted'],1)
        current=self.store.get('alice',ident)
        self.assertEqual(current['cards'],cards);self.assertTrue(current['context_revoked'])
        self.assertNotIn('被撤销的背景',json.dumps(current,ensure_ascii=False))
        with self.assertRaises(ValueError):self.store.request_result('alice','create','create-1')
        with self.assertRaises(ValueError):self.store.request_result('alice','reading','reading')
        fresh=self.store.begin_reading('alice',ident,model='m',prompt_version='v',context_snapshot={'source_refs':['source:src-2']},idempotency_key='fresh')['reading']
        self.assertEqual(self.store.purge_context('alice',[],['src-2'])['readings_deleted'],1)
        with self.assertRaises(KeyError):self.store.get_reading('alice',fresh['id'])

if __name__=='__main__':unittest.main()
