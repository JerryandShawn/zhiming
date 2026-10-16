"""Durable HTTP effects and parent/cancellation fences on real PostgreSQL."""
import asyncio
import json
import unittest
from unittest.mock import patch
from psycopg import sql
import test_core_web as web_fixture
import test_core_runtime as runtime_fixture
from test_core_memory import test_dsn
from mingjing_core.domain.contracts import LeaseConflict


class CoreCaseMutationRegression(unittest.TestCase):
    def setUp(self):
        web_fixture.CoreWeb.setUp(self)
        self.assertEqual(self.get('/api/state').status_code,200)
    tearDown=web_fixture.CoreWeb.tearDown
    get=web_fixture.CoreWeb.get
    post=web_fixture.CoreWeb.post

    def case(self,key,title):
        result=self.post('/api/cases',{'request_id':key,'title':title})
        self.assertEqual(result.status_code,200,result.text)
        return result.json()

    def update_case(self,case,key,title):
        payload={'request_id':key,'expected_revision':case['revision'],'changes':{'title':title}}
        result=self.client.patch('/api/cases/'+case['id'],json=payload,headers=self.headers)
        self.assertEqual(result.status_code,200,result.text)
        return payload,result.json()

    def test_event_lost_response_replay_survives_later_case_update(self):
        case=self.case('event-case','合成学习安排')
        payload={'request_id':'event-lost-response','expected_revision':case['revision'],
                 'kind':'acted','content':'SYNTHETIC_CASE_PRIVATE_FEEDBACK_481'}
        first=self.post('/api/cases/'+case['id']+'/events',payload)
        self.assertEqual(first.status_code,200,first.text)
        self.update_case(case,'event-case-update','已执行的合成安排')
        revision=self.repo.get_revision('alpha')
        replay=self.post('/api/cases/'+case['id']+'/events',payload)
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json(),first.json())
        self.assertEqual(self.repo.get_revision('alpha'),revision)
        self.assertEqual(len(self.repo.list('alpha','feedback')),1)
        with self.repo.connection() as connection:
            rows=connection.execute(sql.SQL('SELECT receipt FROM {} WHERE owner=%s').format(self.repo.table('core_mutation_requests')),('alpha',)).fetchall()
        self.assertNotIn(payload['content'],json.dumps(rows,ensure_ascii=False))

    def test_same_event_key_other_case_rolls_back_original_linkage(self):
        left=self.case('left-case','合成事项 A');right=self.case('right-case','合成事项 B')
        payload={'request_id':'shared-event-key','expected_revision':left['revision'],
                 'kind':'progress','content':'SYNTHETIC_CROSS_CASE_EVENT_492'}
        first=self.post('/api/cases/'+left['id']+'/events',payload)
        self.assertEqual(first.status_code,200,first.text)
        message_id=first.json()['source_refs'][0]['message_id']
        before=self.repo.get_revision('alpha')
        conflict=self.post('/api/cases/'+right['id']+'/events',dict(payload,expected_revision=right['revision']))
        self.assertEqual(conflict.status_code,409,conflict.text)
        self.assertEqual(self.service.memory.get_source('alpha',message_id)['case_ids'],[left['id']])
        self.assertEqual(self.repo.get_revision('alpha'),before)
        self.assertEqual(len(self.repo.list('alpha','feedback')),1)

    def test_case_update_retry_projects_current_case_without_reapplying(self):
        case=self.case('case-replay','合成初始事项')
        payload,first=self.update_case(case,'case-first-update','合成第一修改')
        _,current=self.update_case(first,'case-second-update','合成第二修改')
        revision=self.repo.get_revision('alpha')
        replay=self.client.patch('/api/cases/'+case['id'],json=payload,headers=self.headers)
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json(),current)
        creation_replay=self.post('/api/cases',{'request_id':'case-replay','title':'合成初始事项'})
        self.assertEqual(creation_replay.status_code,200,creation_replay.text)
        self.assertEqual(creation_replay.json(),current)
        self.assertEqual(self.repo.get_revision('alpha'),revision)
        conflict=self.client.patch('/api/cases/'+case['id'],json=dict(payload,changes={'title':'合成另一修改'}),headers=self.headers)
        self.assertEqual(conflict.status_code,409,conflict.text)

    def test_deleted_feedback_source_replay_is_body_free(self):
        case=self.case('feedback-delete-case','合成删除事项')
        payload={'request_id':'feedback-delete-key','expected_revision':case['revision'],
                 'kind':'feedback','content':'我喜欢SYNTHETIC_FEEDBACK_DELETE_672'}
        first=self.post('/api/cases/'+case['id']+'/events',payload)
        self.assertEqual(first.status_code,200,first.text)
        source_id=first.json()['source_refs'][0]['message_id']
        fact=self.service.memory.save_fact('alpha','self',source_id,payload['content'],case_id=case['id'])
        self.service.memory.retire_fact('alpha',fact['id'],expected_revision=fact['revision'],scope='source')
        revision=self.repo.get_revision('alpha')
        replay=self.post('/api/cases/'+case['id']+'/events',payload)
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['status'],'deleted')
        self.assertNotIn('SYNTHETIC_FEEDBACK_DELETE',replay.text)
        self.assertEqual(self.repo.get_revision('alpha'),revision)


class CoreParentAndCancellationRegression(unittest.TestCase):
    def setUp(self):
        self.dsn=test_dsn()
        runtime_fixture.CoreRuntimeTests.setUp(self)
    tearDown=runtime_fixture.CoreRuntimeTests.tearDown
    consult=runtime_fixture.CoreRuntimeTests.consult
    run_by_request=runtime_fixture.CoreRuntimeTests.run_by_request

    def test_explicit_old_parent_source_stays_in_all_three_phase_dependencies(self):
        parent=self.consult(message='SYNTHETIC_PARENT_QUESTION_638',request_id='parent-source')
        parent_id=parent['meta']['core_run']['run_id']
        source_id=self.service._record('alice',parent_id,'intake')['source_id']
        for index in range(40):
            self.service.memory.receive('alice','self','合成无关历史 '+str(index),source_id='irrelevant-'+str(index),conversation_id='shared')
        child=self.service.submit(owner='alice',message='补充这个问题的可用时间。',request_id='parent-followup',
                                  parent_run=parent_id,conversation_id='shared',depth='standard')
        child=self.repo.claim_run('alice',child['id']);token=child['lease_token']
        for phase in ('intake','memory','snapshot'):
            self.service.execute_stage('alice',child['id'],token,phase)
            self.assertIn('message:'+source_id,self.repo.fetch_run('alice',child['id'])['dependencies'])
        intake=self.provider.requests[-1]['payload']['reference_data']
        self.assertEqual(intake['clarification_for'],{'question':'SYNTHETIC_PARENT_QUESTION_638'})
        self.assertNotIn('plan',intake['clarification_for'])
        original=self.repo.get('alice','message',source_id)
        self.repo.delete('alice','message',source_id,expected_revision=original['revision'])
        self.repo.invalidate_derived('alice',[],[source_id])
        self.assertEqual(self.repo.fetch_run('alice',child['id'])['status'],'revoked')
        self.assertFalse(any(step.get('run_id')==child['id'] for step in self.repo.list('alice','runtime_step')))
        with self.assertRaises(LeaseConflict):self.repo.prepare_retry('alice',child['id'])

    def test_cancel_during_intake_counts_call_without_saving_late_body(self):
        self.provider.proposal={'quote':'我喜欢SYNTHETIC_CANCEL_BODY_534','category':'偏好'}
        generate=self.provider.generate
        def cancelled(**kwargs):
            output=generate(**kwargs)
            if kwargs['purpose']=='intake':
                run=self.run_by_request('cancel-during-intake')
                self.repo.fail_run('alice',run['id'],'SYNTHETIC_CANCEL',run['lease_token'],status='cancelled')
            return output
        with patch.object(self.provider,'generate',side_effect=cancelled):
            with self.assertRaises(LeaseConflict):self.consult(message='我喜欢SYNTHETIC_CANCEL_BODY_534',request_id='cancel-during-intake',depth='standard')
        run=self.run_by_request('cancel-during-intake')
        self.assertEqual((run['status'],run['calls']),('cancelled',1))
        self.assertEqual(self.service.memory.facts('alice'),[])
        self.assertFalse(any(step.get('run_id')==run['id'] for step in self.repo.list('alice','runtime_step')))
        with self.assertRaises(LeaseConflict):self.repo.prepare_retry('alice',run['id'])
        with self.assertRaises(LeaseConflict):self.consult(message='我喜欢SYNTHETIC_CANCEL_BODY_534',request_id='cancel-during-intake',depth='standard')
        self.assertEqual(len(self.provider.requests),1)

    def test_cancel_after_committed_memory_keeps_authorized_effect_once(self):
        self.provider.proposal={'quote':'我喜欢合成晨间学习','category':'偏好'}
        run=self.service.submit(owner='alice',message='我喜欢合成晨间学习',request_id='cancel-after-memory',depth='standard')
        run=self.repo.claim_run('alice',run['id']);token=run['lease_token']
        for phase in ('intake','memory'):self.service.execute_stage('alice',run['id'],token,phase)
        self.assertEqual(len(self.service.memory.facts('alice')),1)
        receipt=self.service._record('alice',run['id'],'memory')['receipts'][0]
        self.assertEqual(receipt['write_status'],'saved')
        self.repo.fail_run('alice',run['id'],'SYNTHETIC_CANCEL',token,status='cancelled')
        with self.assertRaises(LeaseConflict):self.service.execute_stage('alice',run['id'],token,'snapshot')
        with self.assertRaises(LeaseConflict):self.repo.prepare_retry('alice',run['id'])
        self.assertEqual(len(self.service.memory.facts('alice')),1)
        self.assertEqual(self.repo.fetch_run('alice',run['id'])['calls'],1)


if __name__=='__main__':unittest.main()
