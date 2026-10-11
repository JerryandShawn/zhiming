"""Model denials must not become fabricated program save receipts."""
import unittest
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import InvalidAnswer
from tests import test_core_compatibility as helpers


class SaveAssertionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):helpers.CoreCompatibilityTests.setUpClass.__func__(cls)
    setUp=helpers.CoreCompatibilityTests.setUp
    tearDown=helpers.CoreCompatibilityTests.tearDown
    consult=helpers.CoreCompatibilityTests.consult
    run_by_request=helpers.CoreCompatibilityTests.run_by_request

    def configure(self,summary,caveats=None):
        self.provider=helpers.CompatibilityProvider()
        self.provider.final_patch={'plain_summary':summary,'caveats':caveats or []}
        self.service=ConsultationService(self.repo,model=self.provider)

    def test_actual_fc4_negative_caveat_passes_without_false_receipt(self):
        self.configure('先核实条件再决定。',['不声称已保存或更新任何资料。'])
        result=self.consult(request_id='actual-negative-save',depth='standard')
        self.assertEqual(result['meta']['core_run']['calls'],2)
        self.assertEqual(result['validation']['status'],'validated')
        self.assertEqual(result['memory_receipts'],[])

    def test_denial_cannot_exempt_later_save_promise(self):
        for i,text in enumerate(('不声称已保存。但我已经保存了。','不能声称已保存，不过我会记住。',
                                 '不是不声称已保存。','并非不能声称已经保存。')):
            with self.subTest(text=text):
                self.configure(text)
                with self.assertRaises(InvalidAnswer):self.consult(request_id='unsafe-save-'+str(i),depth='standard')
                run=self.run_by_request('unsafe-save-'+str(i))
                self.assertEqual(run['status'],'failed')
                final=self.service._record('alice',run['id'],'model:repair')
                self.assertIn('保存或删除提示必须由实际程序回执生成',self.service._validate('alice',run,final))

    def test_positive_model_save_promise_is_blocked(self):
        self.configure('我已经为你保存到长期记忆。')
        with self.assertRaises(InvalidAnswer):self.consult(request_id='positive-save',depth='standard')
        self.assertEqual(self.run_by_request('positive-save')['calls'],3)


if __name__=='__main__':unittest.main()
