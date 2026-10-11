"""Actual service contracts and PG failures; only provider outputs are synthetic."""
from copy import deepcopy
import json
import unittest

from jsonschema import Draft202012Validator, ValidationError

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.consultation import FinalAnswer, SpecialistAnswer, InvalidAnswer
from tests import test_core_compatibility as helpers


class ContractProvider(helpers.CompatibilityProvider):
    def __init__(self):
        super().__init__()
        self.contract_requests = []
        self.omit_final = set()
        self.empty_claim_ids = False

    def generate(self, **kwargs):
        self.contract_requests.append({'purpose': kwargs['purpose'], 'schema': deepcopy(kwargs['schema'])})
        response = super().generate(**kwargs)
        response.update(usage={'input_tokens': 11, 'output_tokens': 7},
                        latency_seconds=0.125, model='synthetic-contract-only')
        if kwargs['purpose'] in ('synthesis', 'repair'):
            for field in self.omit_final:
                response['output'].pop(field, None)
            if self.empty_claim_ids:
                # Reproduce the real-model failure: a correct ID in prose is
                # not a structured citation. The original validator must reject.
                claim = kwargs['payload']['reference_data']['claims'][0]
                response['output']['professional_appendix'] = '仅作反思。声明 ID：' + claim['claim_id']
                response['output']['cited_claim_ids'] = []
        return response


def final_output(**changes):
    return dict(plain_summary='先核实书面条件，未知费用保持未知。',
                explanation='', actions=[], decision_options=[], follow_up='',
                professional_appendix='', cited_fact_ids=[], cited_claim_ids=[], caveats=[], **changes)


def decision_options():
    return [{'option': option, 'benefit': '核实后才能判断', 'cost': '实际费用未知',
             'risk': '班次待核实', 'reversibility': '退出条件待确认', 'first_step': '询问书面条件'}
            for option in ('核实A', '核实B')]


class CoreModelContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.CoreCompatibilityTests.setUpClass.__func__(cls)

    setUp = helpers.CoreCompatibilityTests.setUp
    tearDown = helpers.CoreCompatibilityTests.tearDown
    consult = helpers.CoreCompatibilityTests.consult
    run_by_request = helpers.CoreCompatibilityTests.run_by_request
    save = helpers.CoreCompatibilityTests.save

    def configure(self):
        self.provider = ContractProvider()
        self.service = ConsultationService(self.repo, model=self.provider)

    def fixed_draw(self):
        case = self.service.memory.create_case('alice', 'self', '合成契约事项', operation_id='contract-case')
        draw = self.service.tarot.create_draw('alice', subject_id='self', case_id=case['id'],
            question='怎样核实学习条件？', spread_id='focus1', draw_source='manual',
            manual_cards=[{'card_id': 'major-00', 'orientation': 'upright'}],
            idempotency_key='contract-fixed-draw')['draw']
        draw = self.service.tarot.reveal('alice', draw['id'])
        return case, draw

    def actual_reference(self):
        self.configure()
        self.save('我不能上夜班')
        self.save('我喜欢白天学习', kind='preference')
        case, draw = self.fixed_draw()
        snapshot = self.service.memory.snapshot('alice', 'self', [case['id']])
        authorized = self.service.tarot.get_for_reading('alice', draw['id'])
        declarations = self.service.knowledge.tarot_claims(authorized, 'alice', 'self', snapshot['revision'])
        self.assertTrue(declarations['claims'])
        return {'facts': snapshot['facts'], 'claims': declarations['claims']}

    def validate_schema(self, contract, reference):
        schema = self.service._output_schema(contract, {'reference_data': reference})
        Draft202012Validator.check_schema(schema)
        return schema, Draft202012Validator(schema)

    def test_current_reference_ids_bound_final_and_specialist_schema(self):
        reference = self.actual_reference()
        schema, validator = self.validate_schema(FinalAnswer, reference)
        facts = [fact['id'] for fact in reference['facts']]
        claims = [claim['claim_id'] for claim in reference['claims']]
        self.assertEqual(schema['properties']['cited_fact_ids']['items']['enum'], facts)
        self.assertEqual(schema['properties']['cited_claim_ids']['items']['enum'], claims)
        self.assertEqual(schema['properties']['cited_claim_ids']['minItems'], 1)
        valid = final_output()
        valid.update(cited_fact_ids=facts[:1], cited_claim_ids=claims[:1])
        validator.validate(valid)
        for field, value in (('cited_fact_ids', ['fact-outside-current-scope']),
                             ('cited_claim_ids', ['claim-outside-current-scope']), ('cited_claim_ids', [])):
            with self.subTest(field=field, value=value):
                wrong = deepcopy(valid); wrong[field] = value
                with self.assertRaises(ValidationError): validator.validate(wrong)
        specialist_schema, specialist = self.validate_schema(SpecialistAnswer, reference)
        self.assertIn('claim_ids', specialist_schema['required'])
        specialist.validate({'system': 'tarot', 'claim_ids': claims[:1], 'discussion': '仅作反思', 'uncertainties': []})
        for ids in ([], ['claim-outside-current-scope']):
            with self.assertRaises(ValidationError): specialist.validate({'system': 'tarot', 'claim_ids': ids})

    def test_decision_requires_independent_two_options_action_and_current_fact_citation(self):
        reference = self.actual_reference()
        reference['plan'] = {'decision': True, 'mode': 'decision'}
        schema, validator = self.validate_schema(FinalAnswer, reference)
        self.assertEqual(schema['properties']['decision_options']['minItems'], 2)
        self.assertEqual(schema['properties']['actions']['minItems'], 1)
        self.assertEqual(schema['properties']['cited_fact_ids']['minItems'], 1)
        valid = final_output()
        valid.update(actions=['询问书面班次和费用'], decision_options=decision_options(),
                     cited_fact_ids=[reference['facts'][0]['id']], cited_claim_ids=[reference['claims'][0]['claim_id']])
        validator.validate(valid)
        for field, value in (('decision_options', decision_options()[:1]), ('actions', []), ('cited_fact_ids', [])):
            with self.subTest(field=field):
                wrong = deepcopy(valid); wrong[field] = value
                with self.assertRaises(ValidationError): validator.validate(wrong)
        for field in ('actions', 'decision_options', 'cited_fact_ids', 'cited_claim_ids'):
            self.assertIn(field, schema['required'])
            wrong = deepcopy(valid); wrong.pop(field)
            with self.assertRaises(ValidationError): validator.validate(wrong)

    def test_support_and_urgent_support_limit_actions_to_one(self):
        self.configure()
        for mode in ('support', 'urgent_support'):
            with self.subTest(mode=mode):
                schema, validator = self.validate_schema(FinalAnswer, {'plan': {'mode': mode, 'decision': False}})
                self.assertEqual(schema['properties']['actions']['maxItems'], 1)
                valid = final_output(); valid['actions'] = ['选择一个可承受的小步骤']
                validator.validate(valid)
                valid['actions'].append('另一个步骤')
                with self.assertRaises(ValidationError): validator.validate(valid)

    def test_missing_reference_uses_max_zero_and_does_not_leak_prior_enums(self):
        reference = self.actual_reference()
        self.validate_schema(FinalAnswer, reference)
        schema, validator = self.validate_schema(FinalAnswer, {'plan': {'decision': False}})
        validator.validate(final_output())
        for field in ('cited_fact_ids', 'cited_claim_ids'):
            self.assertEqual(schema['properties'][field]['maxItems'], 0)
            self.assertNotIn('enum', schema['properties'][field]['items'])
            wrong = final_output(); wrong[field] = ['old-reference']
            with self.assertRaises(ValidationError): validator.validate(wrong)
        specialist_schema, specialist = self.validate_schema(SpecialistAnswer, {})
        self.assertEqual(specialist_schema['properties']['claim_ids']['maxItems'], 0)
        specialist.validate({'system': 'tarot', 'claim_ids': []})
        with self.assertRaises(ValidationError): specialist.validate({'system': 'tarot', 'claim_ids': ['old-reference']})

    def test_missing_required_arrays_fail_and_preserve_real_usage_failure_record(self):
        self.configure()
        self.save('我不能上夜班')
        sentinel = 'SYNTHETIC_FAILED_CONTRACT_BODY_NOT_IN_LEDGER'
        self.provider.final_patch['plain_summary'] = sentinel
        for field in ('cited_fact_ids', 'cited_claim_ids', 'actions', 'decision_options'):
            with self.subTest(field=field):
                self.provider.omit_final = {field}
                request = 'missing-array-' + field
                with self.assertRaises(InvalidAnswer): self.consult(request_id=request, depth='standard')
                run = self.run_by_request(request)
                self.assertEqual(run['status'], 'failed')
                self.assertIsNone(run['result'])
                self.assertEqual(run['calls'], 2)
                self.assertIsNone(self.service._record('alice', run['id'], 'model:synthesis'))
                calls = [call for call in self.repo.list('alice', 'model_call') if call['run_id'] == run['id']]
                failed = [call for call in calls if call.get('reason') == 'output_contract']
                self.assertEqual(len(failed), 1)
                self.assertEqual(failed[0]['status'], 'failed')
                self.assertEqual(failed[0]['failure_code'], 'MODEL_OUTPUT_CONTRACT')
                self.assertEqual(failed[0]['purpose'], 'synthesis')
                self.assertEqual(failed[0]['usage'], {'input_tokens': 11, 'output_tokens': 7})
                self.assertTrue(failed[0]['usage_known'])
                self.assertEqual(failed[0]['latency_seconds'], 0.125)
                self.assertNotIn(sentinel, json.dumps(calls))

    def test_correct_claim_id_in_prose_cannot_replace_empty_professional_citation_array(self):
        self.configure(); _, draw = self.fixed_draw()
        self.provider.empty_claim_ids = True
        with self.assertRaises(InvalidAnswer):
            self.consult(message='请解释这组固定塔罗的反思角度。', request_id='empty-professional-cites',
                         depth='standard', draw_id=draw['id'])
        run = self.run_by_request('empty-professional-cites')
        self.assertEqual(run['status'], 'failed'); self.assertIsNone(run['result'])
        self.assertEqual(run['calls'], 4)
        self.assertIsNone(self.service._record('alice', run['id'], 'validation'))
        claims = self.service._record('alice', run['id'], 'calculation')['claims']
        self.assertTrue(claims)
        for purpose in ('synthesis', 'repair'):
            answer = self.service._record('alice', run['id'], 'model:' + purpose)
            self.assertEqual(answer['cited_claim_ids'], [])
            self.assertIn(claims[0]['claim_id'], answer['professional_appendix'])

    def test_actual_successful_professional_run_receives_current_enum_and_minimum(self):
        self.configure(); _, draw = self.fixed_draw()
        result = self.consult(message='请解释这组固定塔罗的反思角度。', request_id='typed-professional-cites',
                              depth='standard', draw_id=draw['id'])
        schema = next(request['schema'] for request in self.provider.contract_requests if request['purpose'] == 'synthesis')
        Draft202012Validator.check_schema(schema)
        self.assertEqual(schema['properties']['cited_claim_ids']['minItems'], 1)
        self.assertTrue(result['cited_claim_ids'])
        self.assertTrue(set(result['cited_claim_ids']) <= set(schema['properties']['cited_claim_ids']['items']['enum']))
        self.assertEqual(self.run_by_request('typed-professional-cites')['status'], 'succeeded')
        self.assertEqual(result['meta']['core_run']['calls'], 3)


if __name__ == '__main__':
    unittest.main()
