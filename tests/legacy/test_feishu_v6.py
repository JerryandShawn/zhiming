"""Exercise the actual website loader against isolated Hermes/owner databases.

Only the function AST is loaded, avoiding main.py's app startup and global DBs.
"""
import ast
from contextlib import closing
import datetime
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'hermes'))
from state_store import StateStore,ScopeError,EvidenceError
from context_query import ChannelContext
from context_builder import ContextBuilder
from domain_context import register_history
from semantic_index import catalog
from tarot_store import TarotDrawService
from privacy_replay import export_privacy,apply_privacy


def website_loader(base,hermes_db,state,tarot):
    tree=ast.parse((ROOT/'main.py').read_text(encoding='utf-8'))
    function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='load_feishu_log')
    namespace={'os':os,'sqlite3':sqlite3,'datetime':datetime,'BASE':str(base),'HERMES_DB':str(hermes_db),
               'PRIMARY_OWNER':'alice','LOCAL_TZ':datetime.timezone(datetime.timedelta(hours=8)),
               'domain_services':lambda ignored:(state,tarot)}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(ROOT/'main.py'),'exec'),namespace)
    return namespace['load_feishu_log']


class FeishuWebsiteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.db=self.base/'hermes.db'
        self.state=StateStore(self.base);self.tarot=TarotDrawService(self.base)
        self.state.ensure_owner('alice');self.state.ensure_owner('bob')
        self.state.create_subject('alice','friend','朋友')
        self.state.bind_channel('alice','feishu','ou_alice')
        self.state.bind_channel('alice','feishu','oc_shared')
        self.state.bind_channel('alice','feishu','ou_friend','friend')
        self.state.bind_channel('bob','feishu','ou_bob')
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript('''
            CREATE TABLE sessions(id TEXT,source TEXT,user_id TEXT,chat_id TEXT,chat_type TEXT);
            CREATE TABLE messages(id INTEGER,session_id TEXT,role TEXT,content TEXT,timestamp REAL,active INTEGER);
            ''')
            connection.executemany('INSERT INTO sessions VALUES(?,?,?,?,?)',[
                ('a','feishu','ou_alice','oc_alice','dm'),('b','feishu','ou_bob','oc_bob','dm'),
                ('collision','feishu','ou_bob','ou_alice','dm'),
                ('shared-a','feishu','ou_chat_a','oc_shared','dm'),('shared-b','feishu','ou_chat_b','oc_shared','dm'),
                ('friend','feishu','ou_friend','oc_friend','dm'),('group','feishu','ou_alice','oc_group','group'),
                ('other','telegram','ou_alice','oc_other','dm'),('missing','feishu',None,'ou_alice','dm')])
            connection.executemany('INSERT INTO messages VALUES(?,?,?,?,?,?)',[
                (1,'a','user','请记住，我喜欢清晨读书',1790800000,1),(2,'a','assistant','这是一条助手回复',1790800010,1),
                (3,'b','user','其他账号内容',1790800020,1),(4,'collision','user','CHAT_FIELD_COLLISION',1790800030,1),
                (5,'shared-a','user','SHARED_AUTHOR_A',1790800040,1),(6,'shared-b','user','SHARED_AUTHOR_B',1790800050,1),
                (7,'friend','user','其他人物内容',1790800060,1),(8,'group','user','GROUP_CONTENT',1790800070,1),
                (9,'other','user','OTHER_CHANNEL',1790800080,1),(10,'missing','user','MISSING_AUTHOR',1790800090,1),
                (11,'a','user','INACTIVE_MESSAGE',1790800100,0)])
            connection.commit()
        self.load=website_loader(self.base,self.db,self.state,self.tarot)

    def test_user_binding_cannot_match_chat_field_or_ambiguous_chat_authors(self):
        rows=self.load(100,'alice')
        self.assertEqual([row['message_id'] for row in rows],[1,2])
        self.assertTrue(all(row['owner_user_id']=='alice' and row['subject_id']=='self' for row in rows))
        self.assertEqual(self.load(100,'unknown'),[])
        self.assertEqual(self.load(100),[])
        self.assertEqual([row['message_id'] for row in self.load(100,'bob')],[3,4])
        self.assertEqual([row['message_id'] for row in self.load(100,'alice','friend')],[7])
        # Explicit channel CLI chat mode still refuses multiple session authors.
        bridge=ChannelContext(self.base,self.db)
        with self.assertRaises(ScopeError):bridge.sync_hermes('feishu','oc_shared',binding_kind='chat')

    def test_catalog_source_id_matches_registered_original_and_is_recalled(self):
        history=[row for row in self.load(100,'alice') if row['role']=='user']
        self.assertEqual(history[0]['id'],'fs-1')
        self.assertEqual(history[0]['source_id'],'feishu:1:user')
        register_history(self.state,'alice','self',history)
        docs=[dict(doc,owner_user_id='alice',subject_id='self') for doc in catalog({},history)]
        self.assertEqual(docs[0]['record_id'],1)
        self.assertEqual(docs[0]['source_id'],'feishu:1:user')
        class Index:
            status={'mode':'fixture'}
            def search(self,query,limit):return docs
        context,_,evidence,_=ContextBuilder(self.state,Index()).build('alice','self','清晨读书',history)
        self.assertEqual(len(context['retrieved']),1)
        ref=context['retrieved'][0]['data']['source_ref']
        original=self.state.get_message('alice',ref['message_id'])
        self.assertEqual(original['source_id'],'1:user')
        self.assertEqual(original['role'],'user')
        self.assertTrue(evidence)

    def test_restored_source_stays_revoked_after_real_hermes_sync_and_index_rebuild(self):
        bridge=ChannelContext(self.base,self.db)
        fact=bridge.remember_hermes('1','我喜欢清晨读书','feishu','ou_alice')
        restore=self.base/'restored';restore.mkdir()
        for name in ('state.sqlite','tarot.db'):
            with closing(sqlite3.connect(self.base/name)) as source,closing(sqlite3.connect(restore/name)) as destination:
                source.backup(destination)
        self.state.delete_fact('alice',fact['id'],self.state.revision('alice'),scope='source')
        journal=self.base/'privacy.json'
        export_privacy('alice',self.base/'state.sqlite',self.base/'tarot.db',journal)
        apply_privacy('alice',restore/'state.sqlite',restore/'tarot.db',journal)
        restored=ChannelContext(restore,self.db)
        restored.sync_hermes('feishu','ou_alice')
        self.assertEqual(restored.state.list_facts('alice'),[])
        self.assertNotIn('清晨读书',json.dumps(restored.history('alice','self'),ensure_ascii=False))
        with restored.state.db() as connection:
            row=connection.execute("SELECT id,content,status FROM messages WHERE owner='alice' AND source='feishu' AND source_id='1:user'").fetchone()
        self.assertEqual(row['status'],'deleted');self.assertEqual(row['content'],'')
        with self.assertRaises((ValueError,EvidenceError)):
            restored.remember_hermes('1','我喜欢清晨读书','feishu','ou_alice')
        loaded=website_loader(restore,self.db,restored.state,TarotDrawService(restore))(100,'alice')
        self.assertNotIn(1,[row['message_id'] for row in loaded])
        self.assertNotIn('清晨读书',json.dumps(catalog({},loaded),ensure_ascii=False))
        result=restored.prepare('继续','feishu','ou_alice',sync=True)
        self.assertNotIn('清晨读书',json.dumps(result,ensure_ascii=False))

    def test_stop_preserves_history_but_blocks_its_context_and_index_evidence(self):
        bridge=ChannelContext(self.base,self.db)
        fact=bridge.remember_hermes('1','我喜欢清晨读书','feishu','ou_alice')
        self.state.stop_fact('alice',fact['id'],self.state.revision('alice'))
        history=self.load(100,'alice')
        self.assertIn(1,[row['message_id'] for row in history])
        docs=[dict(doc,owner_user_id='alice',subject_id='self') for doc in catalog({},history)]
        class Index:
            status={'mode':'fixture'}
            def search(self,query,limit):return docs
        context,messages,evidence,_=ContextBuilder(self.state,Index()).build('alice','self','继续',history)
        self.assertEqual(context['retrieved'],[])
        self.assertEqual(messages,[])
        self.assertEqual(evidence,{})


if __name__=='__main__':unittest.main(verbosity=2)
