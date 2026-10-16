"""Tamper tests for the distinct failed-live continuation, without host effects."""
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import patch

from tools import incremental_acceptance as entry
from tools import zero_model_recovery_acceptance as gate

COMMIT='c'*40
TREE='d'*40


def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True).encode()


def fixture():
    original=dict(id='run_'+'1'*32,owner='release_acceptance_'+'2'*32,subject='self',
        operation_id='reading:acceptance-reading-'+'3'*32,fingerprint='4'*64,status='failed',calls=4,
        call_limit=6,repair_used=True,retry_epoch=0,attempts=1,
        request={'mode':'tarot','depth':'standard','draw_id':'5'*32,'reading_id':'6'*32})
    failed=dict(schema='core3-live-http-acceptance-v1',commit=gate.ORIGINAL_COMMIT,passed=False,
        synthetic_owner=original['owner'],checks={k:True for k in gate.PRIOR_CHECKS},calls={'preference':2},
        errors=[{'check':'synthetic-http','code':'CORE_MODEL_RUN_FAILED'}],external_sends=0,
        cleanup={k:True for k in ('environment_restored','alias_removed','web_restarted','synthetic_runs_drained')},
        counts={'primary_before':{'revision':1}})
    claim=dict(schema='core3-live-model-budget-v1',commit=gate.ORIGINAL_COMMIT,business_depth='standard',
        business_call_limits={'preference':6,'reading':6},max_attempts=1,attempts_reserved=1,
        max_total_model_calls=12,retry_allowed=False,claim_survives_failure_or_crash=True)
    entities=[dict(kind='runtime_step',status='active',id=original['id']+':e0:'+name,
        data={'stage':name,'output':{'synthetic_stage':name}}) for name in gate.CACHED_STAGES]
    entities += [dict(kind='model_call',status='succeeded',data={'purpose':name,'run_id':original['id']})
        for name in ('intake','specialist:tarot','synthesis','repair')]
    inspection=[{'run':original,'entities':entities}]
    files={'original_failed.json':encoded(failed),'original_budget_claim.json':encoded(claim),
        'original_inspection.json':encoded(inspection)}
    pins={k:gate.sha(files[k+'.json']) for k in ('original_failed','original_budget_claim','original_inspection')}
    budget=dict(schema='core3-live-model-budget-result-v1',commit=gate.ORIGINAL_COMMIT,passed=False,
        retry_allowed=False,attempt_started=True,source_verified_start=True,source_verified_end=True,
        runner_exit_code=1,max_total_model_calls=12,claim_sha256=pins['original_budget_claim'],
        acceptance={'report_sha256':pins['original_failed'],'calls_from_final_run_metadata':6})
    files['original_budget_result.json']=encoded(budget);pins['original_budget_result']=gate.sha(files['original_budget_result.json'])
    candidate={'commit':COMMIT,'tree':TREE,'tracked_files':1}
    manifest=encoded({'schema':'core3-release-v1','commit':COMMIT,
        'files':{'tests/test_core_live_tarot_guarantee_denial.py':{'sha256':'7'*64}}})
    files['candidate-release.json']=encoded(candidate)
    source={'commit':COMMIT,'tree':TREE,'manifest_sha256':gate.sha(manifest),'tracked_files':1}
    cache={e['data']['stage']:gate.digest(e['data']['output']) for e in entities if e['kind']=='runtime_step'}
    primary={'counts':failed['counts']['primary_before'],'fingerprints':{'history':'8'*64}}
    report=dict(schema=gate.SCHEMA,commit=COMMIT,tree=TREE,original_attempt_commit=gate.ORIGINAL_COMMIT,
        evidence_files={k:{'file':k+'.json','sha256':h} for k,h in pins.items()},
        original_failed_report_sha256=pins['original_failed'],original_inspection_sha256=pins['original_inspection'],
        original_budget_claim_sha256=pins['original_budget_claim'],original_budget_result_sha256=pins['original_budget_result'],
        source_start=deepcopy(source),source_end=deepcopy(source),source_verified_start=True,source_verified_end=True,
        fixed_source_verified_start_and_end=True,cache_sha256=deepcopy(cache),cache_after_execution_sha256=deepcopy(cache),
        run_id=original['id'],operation_id=original['operation_id'],request_fingerprint=original['fingerprint'],
        draw_id=original['request']['draw_id'],reading_id=original['request']['reading_id'],
        direct_recovery={**{k:True for k in ('same_run','same_operation','same_fingerprint','same_draw','same_reading',
            'repair_used_before','repair_used_after')},'calls_before':4,'calls_after':4,'call_limit_before':6,
            'call_limit_after':6,'retry_epoch_before':0,'retry_epoch_after':0,'attempts_before':1,'attempts_after':2,
            'status_before':'failed','status_after':'succeeded','result_sha256':'9'*64},
        original_attempt_passed=False,original_failed_evidence_preserved=True,original_allowance_still_consumed=True,
        original_checks=failed['checks'],checks={k:True for k in gate.RECOVERED_CHECKS},passed=True,errors=[],
        original_recorded_provider_calls=6,additional_provider_calls=0,additional_model_charges=0,external_test_messages_sent=0,
        guards={'charge_attempts':0,'provider_attempts':0},temporary_http_provider_credentials_removed=True,
        cleanup={k:True for k in gate.CLEANUP},synthetic_final={'runs':[{'calls':2,'call_limit':6,'status':'revoked'},
            {'calls':4,'call_limit':6,'status':'revoked'}],'counts':{'counts':{'core_channels':0,'delivery_outbox':0,
            'tarot_draws':0,'tarot_readings':0,'core_runs':2}}},primary_before=deepcopy(primary),primary_after=deepcopy(primary))
    return report,files,pins,manifest


class ZeroModelRecoveryAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.report,self.files,pins,self.manifest=fixture()
        policy=patch.object(gate,'ORIGINAL_HASHES',pins);policy.start();self.addCleanup(policy.stop)
    def validate(self):
        return entry.validate_live_acceptance(self.report,COMMIT,self.files.__getitem__,self.manifest)
    def test_explicit_continuation_passes_and_keeps_original_attempt_failed(self):
        self.assertIs(self.validate(),self.report)
        self.assertFalse(self.report['original_attempt_passed'])
        self.assertEqual(json.loads(self.files['original_failed.json'])['passed'],False)
        self.assertEqual(self.report['additional_provider_calls'],0)
    def test_missing_protected_loader_or_actual_manifest_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'PROTECTED_DEPENDENCIES'):
            entry.validate_live_acceptance(self.report,COMMIT)
    def test_original_evidence_cannot_be_edited_or_resigned(self):
        for resign in (False,True):
            with self.subTest(resign=resign):
                original=deepcopy(self.report);raw=self.files['original_failed.json']
                self.files['original_failed.json']=raw+b' '
                if resign:self.report['evidence_files']['original_failed']['sha256']=gate.sha(raw+b' ')
                with self.assertRaises(ValueError):self.validate()
                self.report=original;self.files['original_failed.json']=raw
    def test_all_four_original_evidence_references_are_mandatory(self):
        for key in gate.ORIGINAL_HASHES:
            with self.subTest(key=key):
                value=self.report['evidence_files'].pop(key)
                with self.assertRaisesRegex(ValueError,'EVIDENCE_SET'):self.validate()
                self.report['evidence_files'][key]=value
    def test_original_failed_record_cannot_be_promoted_to_fresh_success(self):
        for field,value in [('original_attempt_passed',True),('original_allowance_still_consumed',False),
            ('original_failed_evidence_preserved',False),('original_attempt_commit',COMMIT),('original_recorded_provider_calls',0)]:
            with self.subTest(field=field):
                original=deepcopy(self.report);self.report[field]=value
                with self.assertRaises(ValueError):self.validate()
                self.report=original
    def test_changed_source_manifest_or_source_end_blocks_publication(self):
        for change in ('manifest','tree','count','end'):
            with self.subTest(change=change):
                original=deepcopy(self.report);manifest=self.manifest
                if change=='manifest':self.manifest+=b' '
                elif change=='end':self.report['source_verified_end']=False
                elif change=='tree':self.report['source_end']['tree']='0'*40
                else:self.report['source_start']['tracked_files']=2
                with self.assertRaisesRegex(ValueError,'FIXED_SOURCE'):self.validate()
                self.report=original;self.manifest=manifest
    def test_cached_model_output_is_checked_against_original_inspection(self):
        for field in ('cache_sha256','cache_after_execution_sha256'):
            with self.subTest(field=field):
                original=deepcopy(self.report);self.report[field]['model:repair']='0'*64
                with self.assertRaisesRegex(ValueError,'CACHE_CHANGED'):self.validate()
                self.report=original
    def test_new_uuid_retry_epoch_attempt_or_call_budget_cannot_pass(self):
        changes=[('run_id','run_'+'f'*32),('reading_id','f'*32),('operation_id','reading:new'),
            ('calls_after',5),('retry_epoch_after',1),('attempts_after',3),('repair_used_after',False)]
        for key,value in changes:
            with self.subTest(key=key):
                original=deepcopy(self.report)
                target=self.report if key in ('run_id','reading_id','operation_id') else self.report['direct_recovery']
                target[key]=value
                with self.assertRaises(ValueError):self.validate()
                self.report=original
    def test_any_provider_or_charge_attempt_blocks_even_if_total_stays_zero(self):
        for target,key in [('guards','charge_attempts'),('guards','provider_attempts'),('', 'additional_provider_calls'),
            ('','additional_model_charges'),('','external_test_messages_sent')]:
            with self.subTest(key=key):
                original=deepcopy(self.report);(self.report[target] if target else self.report)[key]=1
                with self.assertRaisesRegex(ValueError,'NEW_MODEL_ALLOWANCE_OR_EFFECT'):self.validate()
                self.report=original
    def test_http_checks_401_cleanup_deletion_and_primary_proof_are_required(self):
        for change in ('check','401','queued','deleted_draw','outbox','primary'):
            with self.subTest(change=change):
                original=deepcopy(self.report)
                if change=='check':self.report['checks']['real_reading_and_exact_replay']=False
                elif change=='401':self.report['cleanup']['alias_removed_verified_401']=False
                elif change=='queued':self.report['synthetic_final']['runs'][1]['status']='queued'
                elif change=='deleted_draw':self.report['synthetic_final']['counts']['counts']['tarot_draws']=1
                elif change=='outbox':self.report['synthetic_final']['counts']['counts']['delivery_outbox']=1
                else:self.report['primary_after']['fingerprints']['history']='f'*64
                with self.assertRaises(ValueError):self.validate()
                self.report=original


if __name__=='__main__':unittest.main()
