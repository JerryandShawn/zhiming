"""Timeline and cursor regressions over PG, business services and actual HTTP.

Only provider responses and fixture clock values are synthetic. Completed run
timestamps are set in PostgreSQL; results, run state and source IDs are real.
"""
from datetime import datetime, timezone
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from mingjing_core.adapters.web import create_app
from tests import test_core_runtime as helpers


class CoreHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.CoreRuntimeTests.setUpClass.__func__(cls)
        # Actual PG assistant timestamps must exercise the server's +08 output.
        cls.dsn = make_conninfo(cls.dsn, options='-c TimeZone=Asia/Shanghai')

    def setUp(self):
        helpers.CoreRuntimeTests.setUp(self)
        self.environ = patch.dict(os.environ, {'MINGJING_TOKEN':'synthetic-alice', 'MINGJING_OWNER_ID':'alice',
                                                'ZHIMING_TOKEN_OWNERS':'{"synthetic-bob":"bob"}'})
        self.environ.start()
        self.client = TestClient(create_app(self.service)); self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None); self.environ.stop()
        helpers.CoreRuntimeTests.tearDown(self)

    def get(self, *, owner='alice', **params):
        return self.client.get('/api/history', params=params, headers={'X-Token':'synthetic-'+owner})

    def turn(self, ident, user_at, answer_at, *, owner='alice', subject='self', session='shared'):
        content = '合成时序原话 '+ident
        source = self.service.memory.receive(owner, subject, content, source_id=ident, at=user_at, conversation_id=session)
        response = self.client.post('/api/chat', headers={'X-Token':'synthetic-'+owner},
                    json={'request_id':ident,'message':content,'depth':'fast','session_id':session,'subject_id':subject})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('"type": "result"',response.text)
        with self.repo.transaction(owner) as connection:
            run = connection.execute(sql.SQL('SELECT id,status FROM {} WHERE owner=%s AND operation_id=%s').format(self.repo.table('core_runs')),(owner,ident)).fetchone()
            self.assertEqual(run['status'],'succeeded')
            connection.execute(sql.SQL('UPDATE {} SET updated_at=%s WHERE owner=%s AND id=%s').format(self.repo.table('core_runs')),
                               (datetime.fromisoformat(answer_at),owner,run['id']))
        return source

    @staticmethod
    def identities(rows): return [(row['turn_id'],row['role']) for row in rows]

    def test_interleaved_real_utc_users_and_pg_shanghai_answers_keep_original_times(self):
        sources = {}
        for index,minute in enumerate((25,30,35)):
            ident = 'turn-'+str(index)
            sources[ident] = self.turn(ident,f'2026-10-11T13:{minute}:00+00:00',f'2026-10-11T21:{minute+1}:00+08:00')
        rows = self.get().json()
        self.assertEqual(self.identities(rows),[(ident,role) for ident in sources for role in ('user','assistant')])
        for row in rows:
            index=int(row['turn_id'].split('-')[1]);minute=(25,30,35)[index]
            if row['role']=='user':
                self.assertEqual(row['id'],sources[row['turn_id']]['id'])
                self.assertEqual(row['at'],sources[row['turn_id']]['at'])
            else:
                self.assertEqual(row['at'],f'2026-10-11T21:{minute+1}:00+08:00')
            self.assertIn('.000000+00:00|',row['cursor'])

    def test_cross_shanghai_midnight_follows_instants_and_pages_without_duplicates(self):
        self.turn('last-day','2026-10-11T15:59:30+00:00','2026-10-12T00:00:10+08:00')
        self.turn('next-day','2026-10-11T16:00:20+00:00','2026-10-12T00:01:00+08:00')
        rows=self.get().json()
        self.assertEqual(self.identities(rows),[(turn,role) for turn in ('last-day','next-day') for role in ('user','assistant')])
        last=self.get(limit=2).json()
        first=self.get(limit=2,before=last[0]['cursor']).json()
        self.assertEqual(self.identities(first+last),self.identities(rows))
        self.assertEqual(last[0]['at'],'2026-10-11T16:00:20+00:00')

    def test_legacy_naive_shanghai_times_and_old_cursor_prefix_are_compatible(self):
        stamps=[('legacy-a','user','2026-10-11 21:25:00'),
                ('legacy-b','user','2026-10-11T13:25:30Z'),
                ('legacy-a','assistant','2026-10-11 21:26:00')]
        sources=[self.service.memory.receive('alice',content='迁移合成原话 '+role,source_id=ident,role=role,
                    channel='migration',at=stamp,conversation_id='legacy') for ident,role,stamp in stamps]
        rows=self.get(session='legacy').json()
        self.assertEqual(self.identities(rows),[(ident,role) for ident,role,_ in stamps])
        self.assertEqual([row['at'] for row in rows],[stamp for _,_,stamp in stamps])
        self.assertEqual([row['id'] for row in rows],[source['id'] for source in sources])
        old_before='2026-10-11 21:26:00|legacy-a|assistant'
        self.assertEqual(self.identities(self.get(session='legacy',before=old_before).json()),self.identities(rows[:2]))
        self.assertEqual(self.identities(self.get(session='legacy',before=rows[-1]['cursor']).json()),self.identities(rows[:2]))

    def test_equal_instants_tie_by_turn_and_user_before_answer_with_old_and_new_cursors(self):
        for ident in ('b-turn','a-turn'):
            self.turn(ident,'2026-10-11T13:25:00+00:00','2026-10-11T21:25:00+08:00')
        rows=self.get().json()
        expected=[(turn,role) for turn in ('a-turn','b-turn') for role in ('user','assistant')]
        self.assertEqual(self.identities(rows),expected)
        backwards=[];before=None
        for _ in range(5):
            page=self.get(limit=1,**({'before':before} if before else {})).json()
            if not page: break
            self.assertEqual(len(page),1);backwards.extend(page);before=page[0]['cursor']
        self.assertEqual(self.identities(list(reversed(backwards))),expected)
        old_answer_cursor='2026-10-11T21:25:00+08:00|b-turn|assistant'
        old_user_cursor='2026-10-11T13:25:00+00:00|b-turn|user'
        self.assertEqual(self.identities(self.get(before=old_answer_cursor).json()),expected[:3])
        self.assertEqual(self.identities(self.get(before=old_user_cursor).json()),expected[:2])

    def test_owner_session_subject_scope_remains_enforced_for_pagination(self):
        self.repo.create_subject('alice','other','合成人物',consent='granted')
        self.turn('alice-A','2026-10-11T13:25:00+00:00','2026-10-11T21:26:00+08:00',session='A')
        self.turn('alice-B','2026-10-11T13:30:00+00:00','2026-10-11T21:31:00+08:00',session='B')
        self.turn('alice-other','2026-10-11T13:10:00+00:00','2026-10-11T21:11:00+08:00',session='A',subject='other')
        self.turn('bob-A','2026-10-11T13:05:00+00:00','2026-10-11T21:06:00+08:00',session='A',owner='bob')
        a=self.get(session='A').json()
        self.assertEqual(self.identities(a),[('alice-A','user'),('alice-A','assistant')])
        self.assertEqual(self.identities(self.get(session='B').json()),[('alice-B','user'),('alice-B','assistant')])
        self.assertEqual(self.identities(self.get(session='A',subject_id='other').json()),[('alice-other','user'),('alice-other','assistant')])
        self.assertEqual(self.identities(self.get(owner='bob',session='A',before=a[-1]['cursor']).json()),[('bob-A','user'),('bob-A','assistant')])
        self.assertEqual(self.get(owner='bob',session='A',subject_id='other').status_code,403)
        page=self.get(session='A',before=a[-1]['cursor']).json()
        self.assertEqual(self.identities(page),[('alice-A','user')])

    def test_unparseable_legacy_time_uses_created_instant_without_rewriting_source(self):
        source=self.service.memory.receive('alice',content='合成未知旧时间',source_id='unknown-legacy-time',channel='migration',at='旧时间未知')
        row=self.get().json()[0]
        self.assertEqual(row['at'],'旧时间未知');self.assertEqual(row['id'],source['id'])
        instant=datetime.fromisoformat(row['created_at']).astimezone(timezone.utc).isoformat(timespec='microseconds')
        self.assertTrue(row['cursor'].startswith(instant+'|'))

    def test_malformed_before_is_rejected_without_echoing_private_cursor_values(self):
        response=self.get(before='invalid-time|PRIVATE_CURSOR_SENTINEL|user')
        self.assertEqual(response.status_code,422)
        self.assertNotIn('PRIVATE_CURSOR_SENTINEL',response.text)


if __name__=='__main__':unittest.main()
