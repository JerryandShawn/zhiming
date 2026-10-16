"""Finite recorded denials keep actual reality/consent guards enabled."""
import unittest

from mingjing_core.domain.consultation import InvalidAnswer
from tests import test_core_76b_provider_denials as providers

SYMBOLIC = '象征解释被提升为现实确定性或概率'


class HypotheticalCurrentSourceModel(providers.LocalAnswerModel):
    def generate(self, **kwargs):
        response = super().generate(**kwargs)
        if kwargs['purpose'] == 'intake':
            response['output']['proposals'] = [{'quote':'付款无损失','category':'hypothesis',
                                               'field':None,'value':None,'case_id':None}]
        return response


class Original035SymbolicLimits(unittest.TestCase):
    setUp = providers.Provider76bDenialRegression.setUp
    tearDown = providers.Provider76bDenialRegression.tearDown
    run_for = providers.Provider76bDenialRegression.run_for

    def consult(self, passage, key):
        self.service.model = providers.LocalAnswerModel(passage)
        run = self.service.submit(owner=self.owner,message='费用、班次和退出规则仍待核实，不排盘。',request_id=key)
        return self.service.execute(self.owner,run['id'])

    def test_two_literal_symbolic_limits_and_finite_unknown_list_commit_without_repair(self):
        passages = (
            '八字、紫微、星盘，也不产生任何概率或吉凶保证。',
            '星盘协调与张力并存，不能摘取单一相位证明顺利或失败。',
            '不能把未知当成零成本、完全可逆或无损失。',
            '不能把未知当成零成本或完全无损失。',
        )
        for index, passage in enumerate(passages):
            with self.subTest(passage=passage):
                key = '035-symbolic-finite-' + str(index)
                answer = self.consult(passage,key); current = self.run_for(key)
                self.assertEqual((current['status'],current['calls'],current['repair_used']),('succeeded',2,False))
                self.assertTrue(answer['validation']['valid'])

    def test_double_denial_quotes_contrast_new_subject_field_and_cross_sentence_fail(self):
        passages = (
            ('星盘产生任何概率或吉凶保证。',SYMBOLIC),
            ('星盘不是不产生任何概率或吉凶保证。',SYMBOLIC),
            ('星盘不能“不产生任何概率或吉凶保证”。',SYMBOLIC),
            ('不是“星盘不产生任何概率或吉凶保证”。',SYMBOLIC),
            ('不能“星盘不产生任何概率或吉凶保证”。',SYMBOLIC),
            ('星盘不产生任何概率或吉凶保证，但塔罗保证成功。',SYMBOLIC),
            ('星盘不产生任何概率或吉凶保证。牌面证明真实班次。',SYMBOLIC),
            ('不产生任何概率或吉凶。星盘保证成功。',SYMBOLIC),
            ('星盘能摘取单一相位证明顺利。',SYMBOLIC),
            ('星盘不是不能摘取单一相位证明顺利。',SYMBOLIC),
            ('星盘不能“不能摘取单一相位证明順利”。',SYMBOLIC),
            ('不是“星盘不能摘取单一相位证明顺利”。',SYMBOLIC),
            ('不能“星盘不能摘取单一相位证明顺利”。',SYMBOLIC),
            ('星盘不能摘取单一相位证明顺利，但塔罗证明成功。',SYMBOLIC),
            ('不能摘取单一相位。星盘证明顺利。',SYMBOLIC),
            ('不是不能把未知当成零成本、完全可逆或无损失。',providers.GUARANTEE),
            ('不是“不能把未知当成零成本、完全可逆或无损失”。',providers.GUARANTEE),
            ('不能把未知当成零成本，但付款完全可逆。',providers.GUARANTEE),
            ('不能把未知当成A零成本或B完全可逆。',providers.GUARANTEE),
            ('不能把未知当成零成本。付款完全可逆。',providers.GUARANTEE),
        )
        for index, (passage, issue) in enumerate(passages):
            with self.subTest(passage=passage):
                key = '035-symbolic-unsafe-' + str(index)
                with self.assertRaises(InvalidAnswer): self.consult(passage,key)
                current = self.run_for(key)
                self.assertEqual((current['status'],current['calls'],current['repair_used']),('failed',3,True))
                self.assertIsNone(current['result']); self.assertIn(issue,self.service.validation_attempts[-1])

    def test_current_source_question_fragment_cannot_authorize_positive_guarantee(self):
        self.service.model = HypotheticalCurrentSourceModel('付款无损失。')
        run = self.service.submit(owner=self.owner,message='请判断“付款无损失”是否有依据？',request_id='035-question-fragment')
        with self.assertRaises(InvalidAnswer): self.service.execute(self.owner,run['id'])
        current = self.repo.fetch_run(self.owner,run['id'])
        snapshot = self.service._snapshot(self.owner,current)
        temporary = snapshot['current_source_facts']
        self.assertEqual(len(temporary),1)
        self.assertEqual((temporary[0]['kind'],temporary[0]['content']),('hypothesis','付款无损失'))
        self.assertEqual(len(self.service.memory.facts(self.owner)),7)
        self.assertNotIn(temporary[0]['id'],{f['id'] for f in snapshot['effective_facts']})
        self.assertFalse(any(k.startswith('fact:current_source_') for k in current['dependencies']))
        self.assertIn(providers.GUARANTEE,self.service.validation_attempts[-1])

    def test_explicitly_saved_hypothesis_is_citable_but_cannot_authorize_a_guarantee(self):
        for kind in ('hypothesis','hearsay','concern'):
            with self.subTest(kind=kind):
                text = '请保存这条' + kind + '：付款无损失'
                source = self.service.memory.receive(self.owner,content=text,source_id='035-saved-' + kind)
                receipt = self.service.memory.save_fact(self.owner,'self',source['id'],'付款无损失',kind)
                self.assertEqual(receipt['write_status'],'saved')
                self.service.model = providers.LocalAnswerModel('付款无损失。')
                run = self.service.submit(owner=self.owner,message='费用与退出规则未经核实，请只按已确认现实条件讨论。',
                                          request_id='035-saved-nonfactual-' + kind)
                with self.assertRaises(InvalidAnswer): self.service.execute(self.owner,run['id'])
                self.assertIn(receipt['fact_id'],{f['id'] for f in self.service._snapshot(self.owner,self.repo.fetch_run(self.owner,run['id']))['facts']})
                self.assertIn(receipt['fact_id'],self.service._record(self.owner,run['id'],'synthesis')['cited_fact_ids'])
                self.assertIn(providers.GUARANTEE,self.service.validation_attempts[-1])


if __name__ == '__main__': unittest.main()
