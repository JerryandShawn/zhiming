"""Evidence tampering and budget regressions; no provider or host actions."""
import copy
import json
import unittest
from unittest.mock import patch

from tools import incremental_acceptance as gate


COMMIT='c'*40
OLD='a'*40
TREE='b'*40
MANIFEST='d'*64
HASHES={'tools/example.py':'e'*64}


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()


def historical_fixture():
    final={'summary':'A synthetic recorded answer.','cited_fact_ids':[]}
    valid={'valid':True,'schema':'core3.0','status':'validated'}
    wrapper=dict(source_verified_start=True,source_verified_end=True,python_matches=True,cwd_matches=True,
        exit_code=1,manifest_sha256_start=MANIFEST,manifest_sha256_end=MANIFEST)
    provider={'schema':'core-provider-evaluation-v1','commit':OLD,'synthetic_only':True,'wrapper_execution':wrapper,
        'samples':[dict(sample=s,run_id='run-'+s,ok=True,validated=valid,calls=1) for s in gate.SAMPLES]}
    inspection={'samples':[{'id':'run-'+s,'steps':[{'data':{'stage':'validation','output':{'final':final}}}]} for s in gate.SAMPLES]}
    rows=[]
    for arm in gate.CORE_ARMS:
        for scenario in ('decision','tarot'):
            systems=['astro','bazi','tarot','ziwei'] if arm==gate.CORE_ARMS[1] else ['tarot']
            calls=[{'purpose':'specialist:'+s,'output_contract':'SpecialistAnswer','contract_output':{'system':s}}
                for s in systems] if scenario=='tarot' else []
            calls.append({'purpose':'review' if len(systems)==4 else 'synthesis','contract_output':final})
            limit=10 if arm==gate.CORE_ARMS[1] and scenario=='tarot' else 6
            rows.append(dict(arm=arm,scenario=scenario,status='validated',validation=valid,provider_calls=len(calls),
                call_limit=limit,durable_budget={'calls':len(calls),'limit':limit},calls=calls,fixed_cards_unchanged=True,
                successful_specialist_provider_calls=len(systems),completed_specialist_systems=systems,
                successful_review_provider_calls=int(len(systems)==4)))
    rows.append(dict(arm='legacy',scenario='decision',status='failed',provider_calls=1))
    comparison={'schema_version':'core-real-provider-four-arm-v1','commit':OLD,'synthetic_only':True,
        'wrapper_execution':wrapper,'rows':rows}
    files={'provider.json':encoded(provider),'comparison.json':encoded(comparison),'inspection.json':encoded(inspection)}
    sourcehashes={'provider-evaluation-final.json':gate.digest(files['provider.json']),
        'provider-comparison-final.json':gate.digest(files['comparison.json']),
        'candidate-model-inspection.json':gate.digest(files['inspection.json'])}
    seal={'schema':'core3-immutable-model-batch-archive-v1','commit':OLD,'completed_batch_verified':True,
        'source_verified_start':True,'source_verified_end':True,'inspection_exact_run_set_verified':True,
        'production_changed':False,'files_sha256':sourcehashes,'source_hashes_start':sourcehashes,
        'source_hashes_end':sourcehashes,'manifest_sha256':MANIFEST}
    files['seal.json']=encoded(seal); sealhash=gate.digest(files['seal.json'])
    def pointer(kind):
        return dict(source_commit=OLD,source_file=kind+'.json',source_sha256=gate.digest(files[kind+'.json']),
            seal_file='seal.json',seal_sha256=sealhash)
    providers=[dict(sample=s,source_sample_index=n,historical_calls=1,status='validated',**pointer('provider'))
        for n,s in enumerate(gate.SAMPLES)]
    comparisons=[dict(arm=r['arm'],scenario=r['scenario'],source_row_index=n,historical_calls=r['provider_calls'],
        status='validated',**pointer('comparison')) for n,r in enumerate(rows[:4])]
    current=[]
    for n,selection in enumerate(providers+comparisons):
        provider=n<9
        current.append(dict(coverage_key='p:'+selection['sample'] if provider else 'c:'+selection['arm']+':'+selection['scenario'],
            status='validated',validation_issues=[],real_provider_calls=0,model_substitute_calls=0 if provider else selection['historical_calls'],
            service_path='actual_validator_only' if provider else 'postgresql_langgraph_service',
            original_output_sha256=gate.json_digest(final),replayed_output_sha256=gate.json_digest(final),
            opaque_ids_only_rebound=True,prose_sha256_start=gate.json_digest(final),prose_sha256_end=gate.json_digest(final),
            inspection_source_file='inspection.json',inspection_source_sha256=gate.digest(files['inspection.json']),
            original_output_call_index=0 if provider else len(rows[n-9]['calls'])-1,
            original_output_phase='synthesis' if provider else rows[n-9]['calls'][-1]['purpose'],
            opaque_id_bindings=[],idempotent_replay_verified=True,fixed_cards_unchanged=True,
            final_calls=0 if provider else selection['historical_calls'],call_limit=6 if provider else rows[n-9]['call_limit']))
    failures=[dict(kind='comparison',source_file='comparison.json',source_sha256=gate.digest(files['comparison.json']),
        source_commit=OLD,source_index=4,original_status='failed')]
    record=dict(schema='historical-provider-revalidation.v1',commit=COMMIT,tree=TREE,manifest_sha256=MANIFEST,
        source_file_count=1,source_manifest=dict(HASHES),source_verified_start=True,source_verified_end=True,all_passed=True,
        real_provider_calls=0,historical_provider_coverage=providers,historical_core_comparison_coverage=comparisons,
        historical_sources=[dict(kind=k,**pointer(k)) for k in ('provider','comparison')],
        current_revalidation=current,retained_failures=failures)
    return record,files,{OLD:sealhash}


class IncrementalHistoryTests(unittest.TestCase):
    def setUp(self):
        self.record,self.files,approved=historical_fixture()
        self.policy=patch.object(gate,'APPROVED_HISTORICAL_SEALS',approved);self.policy.start();self.addCleanup(self.policy.stop)

    def validate(self):
        return gate.check_history({'commit':COMMIT,'tree':TREE},MANIFEST,HASHES,self.record,self.files.__getitem__)

    def test_historical_passes_remain_historical_and_current_calls_zero(self):
        result=self.validate()
        self.assertEqual(result['current_stage_real_provider_calls'],0)
        self.assertEqual(result['historical_real_provider_categories'],9)
        self.assertEqual(result['current_recorded_output_rows'],13)
        self.assertEqual(result['historical_failures_retained'],1)
        self.assertIn('not current real-model 9/9',result['scope'])

    def test_failed_original_row_cannot_be_dropped(self):
        self.record['retained_failures']=[]
        with self.assertRaisesRegex(ValueError,'FAILURES_NOT_RETAINED'):self.validate()

    def test_tampered_original_cannot_be_resigned_by_report(self):
        self.files['provider.json']+=b' '
        self.record['historical_provider_coverage'][0]['source_sha256']=gate.digest(self.files['provider.json'])
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH|IDENTITY'):self.validate()

    def test_current_source_must_equal_whole_fixed_tree(self):
        self.record['source_manifest']['untracked.py']='f'*64
        with self.assertRaisesRegex(ValueError,'SOURCE_MISMATCH'):self.validate()

    def test_relabelled_or_missing_revalidation_is_rejected(self):
        for mutation in ('new_real','missing','failed','validator_only_comparison'):
            with self.subTest(mutation=mutation):
                original=copy.deepcopy(self.record)
                if mutation=='new_real':self.record['current_revalidation'][0]['real_provider_calls']=1
                elif mutation=='missing':self.record['current_revalidation'].pop()
                elif mutation=='failed':self.record['current_revalidation'][0]['validation_issues']=['unsafe']
                else:self.record['current_revalidation'][-1]['service_path']='actual_validator_only'
                with self.assertRaises(ValueError):self.validate()
                self.record=original

    def test_replayed_prose_cannot_change_behind_output_hash(self):
        self.record['current_revalidation'][-1]['replayed_output_sha256']=gate.json_digest({'summary':'Changed.'})
        with self.assertRaisesRegex(ValueError,'PROSE_OR_STRUCTURE_CHANGED'):self.validate()

    def test_reference_map_cannot_rewrite_ordinary_words(self):
        self.record['current_revalidation'][-1]['opaque_id_bindings']=[{'old':'synthetic','new':'different'}]
        with self.assertRaisesRegex(ValueError,'BINDINGS_INVALID'):self.validate()

    def test_service_replay_must_restore_idempotency_cards_and_budget(self):
        for key,value in [('idempotent_replay_verified',False),('fixed_cards_unchanged',False),('final_calls',11)]:
            with self.subTest(key=key):
                original=copy.deepcopy(self.record);self.record['current_revalidation'][-1][key]=value
                with self.assertRaisesRegex(ValueError,'SERVICE_REPLAY_INCOMPLETE'):self.validate()
                self.record=original


class IncrementalLiveTests(unittest.TestCase):
    def setUp(self):
        self.report=dict(schema='core3-live-http-acceptance-v1',commit=COMMIT,passed=True,errors=[],external_sends=0,
            checks={k:True for k in gate.LIVE_CHECKS},cleanup={k:True for k in gate.CLEANUP},
            calls={'preference':6,'reading':6},statuses={'synthetic_runs':[{'status':'succeeded'}],
                'synthetic_final':[{'status':'succeeded'}]})

    def test_exact_twelve_call_live_gate_is_accepted(self):
        self.assertIs(gate.validate_live_acceptance(self.report,COMMIT),self.report)

    def test_budget_sends_missing_cleanup_and_running_work_block_publication(self):
        for kind in ('over_budget','extra_business_run','send','cleanup','running','cancelled'):
            with self.subTest(kind=kind):
                record=copy.deepcopy(self.report)
                if kind=='over_budget':record['calls']['reading']=7
                elif kind=='extra_business_run':record['calls']['other']=1
                elif kind=='send':record['external_sends']=1
                elif kind=='cleanup':record['cleanup']['alias_removed']=False
                elif kind=='running':record['statuses']['synthetic_final'][0]['status']='running'
                else:record['cleanup']['cancelled_for_cleanup']=1
                with self.assertRaises(ValueError):gate.validate_live_acceptance(record,COMMIT)


if __name__=='__main__':unittest.main()
