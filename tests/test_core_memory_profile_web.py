"""Profile HTTP correction and privacy replay on the real Core/PG stack."""
import json
import unittest
from psycopg import sql
import test_core_web as web_fixture


class CoreProfilePrivacyRegression(unittest.TestCase):
    def setUp(self):
        web_fixture.CoreWeb.setUp(self)
        self.assertEqual(self.get('/api/state').status_code,200)
    tearDown=web_fixture.CoreWeb.tearDown
    get=web_fixture.CoreWeb.get
    post=web_fixture.CoreWeb.post

    def confirm(self,key,date):
        payload={'request_id':key,'confirmed':True,'expected_revision':self.repo.get_revision('alpha'),
                 'profile':{'gender':'女','birth':{'solar_datetime':date,'timezone_offset':8,'precision':'exact'}}}
        response=self.post('/api/subjects/self/profile/confirm',payload)
        self.assertEqual(response.status_code,200,response.text)
        return payload,response.json()

    def test_profile_update_replay_and_source_delete_cannot_restore_private_value(self):
        first,_=self.confirm('profile-initial','1998-03-12 08:15')
        updated,result=self.confirm('profile-update','1999-04-13 09:16')
        before=self.repo.get_revision('alpha')
        replay=self.post('/api/subjects/self/profile/confirm',updated)
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json(),result);self.assertEqual(self.repo.get_revision('alpha'),before)
        self.assertEqual(self.get('/api/subjects/self/profile').json()['effective']['birth.solar_datetime'],'1999-04-13 09:16')
        target=next(fact for fact in result['receipts'] if fact.get('field')=='birth.solar_datetime')
        deletion={'request_id':'delete-profile-source','expected_revision':target['revision'],'scope':'source'}
        deleted=self.client.request('DELETE','/api/memories/'+target['id'],headers=self.headers,
                                    params={'scope':'source'},json=deletion)
        self.assertEqual(deleted.status_code,200,deleted.text)
        after=self.repo.get_revision('alpha')
        replay=self.post('/api/subjects/self/profile/confirm',updated)
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertNotIn('1999-04-13',replay.text)
        self.assertTrue(all(fact['status']=='deleted' and fact['write_status']=='deleted' for fact in replay.json()['receipts']))
        self.assertEqual(self.repo.get_revision('alpha'),after)
        self.assertEqual(self.get('/api/subjects/self/profile').json()['effective'],{})
        with self.repo.connection() as connection:
            ledger=connection.execute(sql.SQL('SELECT receipt FROM {} WHERE owner=%s AND operation=%s').format(self.repo.table('core_mutation_requests')),('alpha','profile-confirm')).fetchall()
        self.assertNotIn('1999-04-13',json.dumps(ledger))
        self.assertNotIn('1998-03-12',json.dumps(ledger))

    def test_profile_same_operation_changed_birth_is_rejected(self):
        payload,_=self.confirm('profile-same-key','1998-03-12 08:15')
        changed=dict(payload,profile={'gender':'女','birth':{'solar_datetime':'2001-05-01 11:11'}})
        response=self.post('/api/subjects/self/profile/confirm',changed)
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(self.get('/api/subjects/self/profile').json()['effective']['birth.solar_datetime'],'1998-03-12 08:15')


if __name__=='__main__':unittest.main()
