"""Real ASGI + PostgreSQL command replay and privacy checks."""
import unittest
import test_core_web as fixture


class CoreMutationWeb(unittest.TestCase):
    setUp=fixture.CoreWeb.setUp
    tearDown=fixture.CoreWeb.tearDown
    get=fixture.CoreWeb.get
    post=fixture.CoreWeb.post

    def test_settings_retry_is_one_effect_and_changed_args_conflict(self):
        snap=self.get('/api/state').json()
        body={'request_id':'settings-stable','expected_revision':snap['revision'],'settings':{'auto_save_low_sensitivity':False}}
        first=self.client.patch('/api/state/settings',headers=self.headers,json=body)
        self.assertEqual(first.status_code,200,first.text);revision=self.repo.get_revision('alpha')
        replay=self.client.patch('/api/state/settings',headers=self.headers,json=body)
        self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(self.repo.get_revision('alpha'),revision)
        conflict=self.client.patch('/api/state/settings',headers=self.headers,json=dict(body,settings={'auto_save_low_sensitivity':True}))
        self.assertEqual(conflict.status_code,409,conflict.text)

    def test_correction_stop_and_source_delete_replay_cannot_restore_text(self):
        self.post('/api/chat',{'request_id':'origin','message':'我喜欢晨间阅读','depth':'fast'})
        old=self.get('/api/memories').json()[0]
        body={'request_id':'correct-once','expected_revision':old['revision'],'text':'我喜欢傍晚阅读'}
        endpoint='/api/memories/'+old['id']
        first=self.client.patch(endpoint,headers=self.headers,json=body)
        self.assertEqual(first.status_code,200,first.text);corrected=first.json();revision=self.repo.get_revision('alpha')
        self.assertEqual(self.client.patch(endpoint,headers=self.headers,json=body).json()['id'],corrected['id'])
        self.assertEqual(self.repo.get_revision('alpha'),revision)
        deletion={'request_id':'delete-source','scope':'source','expected_revision':corrected['revision']}
        endpoint='/api/memories/'+corrected['id']+'?scope=source&expected_revision='+str(corrected['revision'])
        first=self.client.request('DELETE',endpoint,headers=self.headers,json=deletion)
        self.assertEqual(first.status_code,200,first.text);revision=self.repo.get_revision('alpha')
        replay=self.client.request('DELETE',endpoint,headers=self.headers,json=deletion)
        self.assertEqual(replay.json(),first.json());self.assertEqual(self.repo.get_revision('alpha'),revision)
        self.assertNotIn('傍晚',replay.text)
        denied=self.client.patch('/api/memories/'+old['id'],headers=self.headers,json=body)
        self.assertGreaterEqual(denied.status_code,400);self.assertNotIn('傍晚',denied.text)

    def test_reveal_cancel_delete_replay_preserves_cards_and_revision(self):
        case=self.post('/api/cases',{'request_id':'case','title':'合成事项'}).json()
        draw=self.post('/api/tarot/draws',{'idempotency_key':'draw','question':'如何核对安排？','case_id':case['id']}).json()['draw']
        path='/api/tarot/draws/'+draw['id'];body={'request_id':'flip-one','position':1}
        first=self.post(path+'/reveal',body);self.assertEqual(first.status_code,200,first.text)
        revision=self.repo.get_revision('alpha');replay=self.post(path+'/reveal',body)
        self.assertEqual(replay.json(),first.json());self.assertEqual(self.repo.get_revision('alpha'),revision)
        self.assertEqual(self.post(path+'/reveal',dict(body,position=2)).status_code,409)
        body={'request_id':'cancel-once'};first=self.post(path+'/cancel',body);revision=self.repo.get_revision('alpha')
        self.assertEqual(self.post(path+'/cancel',body).json(),first.json());self.assertEqual(self.repo.get_revision('alpha'),revision)
        body={'request_id':'delete-draw-once'};first=self.client.request('DELETE',path,headers=self.headers,json=body);revision=self.repo.get_revision('alpha')
        self.assertEqual(self.client.request('DELETE',path,headers=self.headers,json=body).json(),first.json());self.assertEqual(self.repo.get_revision('alpha'),revision)
        self.assertGreaterEqual(self.post(path+'/reveal',{'request_id':'flip-one','position':1}).status_code,400)


if __name__=='__main__':unittest.main()
