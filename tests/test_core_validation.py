"""Real service checks for symbolic claims and explicit limits."""
import unittest
from tests import test_core_runtime as fixture
from tests.test_core_compatibility import CompatibilityProvider
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import InvalidAnswer

class CoreValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.CoreRuntimeTests.setUpClass.__func__(cls)
    setUp=fixture.CoreRuntimeTests.setUp
    tearDown=fixture.CoreRuntimeTests.tearDown
    consult=fixture.CoreRuntimeTests.consult

    def configure(self,text):
        self.provider=CompatibilityProvider();self.provider.final_patch={'plain_summary':text}
        self.service=ConsultationService(self.repo,model=self.provider)

    def test_explicit_symbolic_limits_are_valid_and_need_no_repair(self):
        self.configure('八字不能保证成功。塔罗无法据此证明现实结局。星盘不是保证。')
        result=self.consult(request_id='limits',depth='standard')
        self.assertTrue(result['validation']['valid']);self.assertEqual(result['meta']['core_run']['calls'],2)

    def test_affirmed_guarantee_after_denial_is_rejected(self):
        self.configure('塔罗不能保证成功，但八字一定会成功。')
        with self.assertRaises(InvalidAnswer):self.consult(request_id='guarantee',depth='standard')

    def test_unrelated_negative_word_does_not_hide_guarantee(self):
        self.configure('塔罗不需要怀疑，保证成功。')
        with self.assertRaises(InvalidAnswer):self.consult(request_id='unrelated-negative',depth='standard')

if __name__=='__main__':unittest.main()
