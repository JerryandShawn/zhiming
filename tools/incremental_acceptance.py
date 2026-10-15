"""Explicit incremental release evidence; historical calls remain historical.

This module never calls a model, database, network, service manager or transport.
The original frozen stage validator is loaded from checked bytes and reused for
every non-model gate. Publication additionally requires the real live HTTP gate.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
from types import ModuleType

SCHEMA = 'core3-actual-stage-acceptance-incremental-v2'
METHOD = 'historical-real-plus-current-recorded-output-revalidation'
FROZEN_SHA256 = '051c4a399cb417232e30df7e94bb8b03c486ca0b4fc12b4082002c251ca99b34'
PRIVATE = Path('/root/zhiming-core-secrets')
SHA = re.compile(r'[0-9a-f]{64}')
COMMIT = re.compile(r'[0-9a-f]{40}')
SAMPLES = ('memory','recall','bazi','ziwei','astro','tarot','fusion','decision','report')
CORE_ARMS = ('new_single_specialist','new_controlled_multi_specialists')
# Actual immutable completed-batch manifests reviewed before this extension.
# Rehashing edited historic rows and an edited seal cannot create new evidence.
APPROVED_HISTORICAL_SEALS = {
    '2bc3ef534bf5f14e6ae686d33037320c2fc69bd7':'e5c66732bfff587b6ba2643477107663c3e197c787d9de1df671a7ffbe7885b7',
    '964b8529d284a60907c84bb856ef4147b69e3c4b':'1ce8bfc1988fcb5ab540c77508be77ae46c174a3b12d96c3d3f94761f37c147d',
    '6b96ba3de91c262589b5f77f11f61e1ec1c5c3f6':'973edfde1408421143f75cf7f49e50292a7dd7b765b85b2748a86358adb41dcc',
    '4288d5aa3e23c7b2678b37b64462b9e1a91ac1df':'2af30f7fb9ead1b6d1f1f9d6fc360a9c6e9417ecf7fe8739f74027d2619e66ab',
    '88f30cc113ab2fba203a77576eb633e2655ae6b8':'866442c380cc868cb76d3f3aadd80a98478a1d7169e35703185fb03cf7711ad0',
    '8a7ca631b793a4d084a3cfc4830f36cb1ecb1f5d':'9aa2baeee0d4be1b52f4fc5692376c3369a8256c1141beb5298ccc945e96aee7',
}
LIVE_CHECKS = ('fresh_synthetic_scope_empty','explicit_save_and_chat_replay',
    'correction_source_delete_and_replay','case_manual_three_cards_reveal_and_conflict',
    'real_reading_and_exact_replay','draw_delete_clears_http_history_chat_and_run',
    'primary_http_and_pg_unchanged')
CLEANUP = ('environment_restored','alias_removed','web_restarted','synthetic_runs_drained')
INPUTS = {'candidate','local','replay','fixed','replay_preflight','migration','calculators',
    'stage_ui','preflight','bindings','core_log','native_fence','backup_restore','historical_revalidation'}


def require(value, code):
    if not value: raise ValueError(code)


def digest(value): return hashlib.sha256(value).hexdigest()


def json_digest(value):
    return digest(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False).encode())


def integer(value, minimum=0): return type(value) is int and value >= minimum


def basename(name):
    return isinstance(name,str) and bool(name) and name == PurePosixPath(name).name and '\\' not in name and name not in ('.','..')


def protected_bytes(path):
    path=Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink() and
        not any(p.is_symlink() for p in path.parents), 'INCREMENTAL_PRIVATE_FILE_INVALID')
    info=path.stat()
    require(info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600 and stat.S_ISREG(info.st_mode),
        'INCREMENTAL_PRIVATE_FILE_MODE')
    return path.read_bytes()


def frozen_gate():
    source=protected_bytes(PRIVATE/'write-stage-acceptance.py')
    require(digest(source)==FROZEN_SHA256,'INCREMENTAL_FROZEN_VALIDATOR_CHANGED')
    module=ModuleType('_core3_frozen_stage_gate')
    module.__file__=str(PRIVATE/'write-stage-acceptance.py')
    exec(compile(source,module.__file__,'exec'),module.__dict__)
    return module


def dependency_loader(release):
    def read(name):
        if name=='release/calculator-validation.json':
            path=Path(release)/'calculator-validation.json'
            require(path.is_file() and not path.is_symlink() and not any(p.is_symlink() for p in path.parents),
                'INCREMENTAL_CALCULATOR_PATH_INVALID')
            require(path.stat().st_uid==0 and Path(release).stat().st_mode & 0o077 == 0,
                'INCREMENTAL_CALCULATOR_NOT_PROTECTED')
            return path.read_bytes()
        require(basename(name),'INCREMENTAL_DEPENDENCY_PATH_INVALID')
        return protected_bytes(PRIVATE/name)
    return read


def load_ref(ref, read):
    require(isinstance(ref,dict) and set(ref)=={'file','sha256'} and isinstance(ref.get('sha256'),str)
        and SHA.fullmatch(ref['sha256']),'INCREMENTAL_DEPENDENCY_INVALID')
    raw=read(ref['file'])
    require(isinstance(raw,bytes) and digest(raw)==ref['sha256'],'INCREMENTAL_DEPENDENCY_HASH_MISMATCH')
    return raw


def check_native(candidate, manifest_hash, hashes, fence, restore):
    for value in (fence,restore):
        require(value.get('commit')==candidate['commit'] and value.get('passed') is True and
            value.get('synthetic_only') is True and value.get('source_verified_start') is True and
            value.get('source_verified_end') is True and value.get('manifest_files_count')==len(hashes),
            'INCREMENTAL_NATIVE_SOURCE_OR_RESULT_FAILED')
    require(fence.get('schema')=='core3-native-skill-fence-probe-v1' and fence.get('temporary_paths_only') is True
        and fence.get('checks')=={k:True for k in ('shared_fd_survives_exec','exclusive_blocked_until_cli_exit',
        'bounded_timeout','exclusive_available_after_cli_exit','gate_rejects_before_configuration_or_db')}
        and all(type(fence.get(k)) is int and fence[k]==0 for k in ('model_calls','external_test_messages_sent','database_accesses')),
        'INCREMENTAL_NATIVE_FENCE_FAILED')
    require(restore.get('schema')=='core3-stage-synthetic-backup-restore-v1' and restore.get('tree')==candidate['tree']
        and restore.get('database')=='zhiming_core_stage' and restore.get('manifest_sha256_start')==manifest_hash
        and restore.get('canonical_source_hashes')==hashes and restore.get('source_unchanged') is True,
        'INCREMENTAL_RESTORE_SOURCE_FAILED')
    require(all(restore.get(k) is True for k in ('ok','actual_pg_dump','actual_pg_restore','body_free_ledger',
        'reimport_blocked','repeat_apply_stable','probe_schema_removed','temporary_archive_removed'))
        and restore.get('archive_mode')=='0600' and isinstance(restore.get('archive_sha256'),str)
        and SHA.fullmatch(restore['archive_sha256']) and restore.get('older_backup_fact_count')==1
        and restore.get('effective_fact_count_after_latest_withdrawal')==0 and integer(restore.get('latest_revocations'),1),
        'INCREMENTAL_SYNTHETIC_RESTORE_FAILED')
    return {'native_fence_checks':5,'actual_synthetic_pg_dump_restore':True,
        'latest_withdrawal_reimport_blocked':True,'full_private_disaster_restore_verified':False}


def check_history(candidate, manifest_hash, hashes, record, read):
    """Validate independently sourced historical results, never relabel them."""
    require(record.get('schema')=='historical-provider-revalidation.v1' and record.get('commit')==candidate['commit']
        and record.get('tree')==candidate['tree'] and record.get('manifest_sha256')==manifest_hash
        and record.get('source_file_count')==len(hashes) and record.get('source_verified_start') is True
        and record.get('source_verified_end') is True and record.get('source_manifest')==hashes
        and record.get('all_passed') is True,'INCREMENTAL_HISTORY_CURRENT_SOURCE_MISMATCH')
    require(record.get('real_provider_calls')==0 and type(record.get('real_provider_calls')) is int,
        'INCREMENTAL_REPLAY_MISLABELLED_REAL')
    providers=record.get('historical_provider_coverage'); comparisons=record.get('historical_core_comparison_coverage')
    require(isinstance(providers,list) and Counter(r.get('sample') for r in providers)==Counter(SAMPLES),
        'INCREMENTAL_HISTORICAL_NINE_CATEGORIES_MISSING')
    require(isinstance(comparisons,list) and Counter((r.get('arm'),r.get('scenario')) for r in comparisons)==
        Counter((a,s) for a in CORE_ARMS for s in ('decision','tarot')),'INCREMENTAL_HISTORICAL_FOUR_CORE_ROWS_MISSING')
    keys=[]; historical_calls=0; used_sources={}
    sources=record.get('historical_sources')
    require(isinstance(sources,list) and Counter((r.get('kind'),r.get('source_commit')) for r in sources)==
        Counter((kind,commit) for kind in ('provider','comparison') for commit in APPROVED_HISTORICAL_SEALS),
        'INCREMENTAL_HISTORICAL_SOURCE_SET_INCOMPLETE')
    for ref in sources:
        kind=ref['kind'];commit=ref['source_commit']
        require(APPROVED_HISTORICAL_SEALS[commit]==ref.get('seal_sha256'),'INCREMENTAL_HISTORICAL_SEAL_NOT_APPROVED')
        source=json.loads(load_ref({'file':ref.get('source_file'),'sha256':ref.get('source_sha256')},read))
        seal=json.loads(load_ref({'file':ref.get('seal_file'),'sha256':ref.get('seal_sha256')},read))
        original_name='provider-evaluation-final.json' if kind=='provider' else 'provider-comparison-final.json'
        require(source.get('commit')==commit and source.get('synthetic_only') is True and
            seal.get('commit')==commit and seal.get('files_sha256',{}).get(original_name)==ref['source_sha256'],
            'INCREMENTAL_HISTORICAL_SOURCE_IDENTITY')
        used_sources[(kind,ref['source_file'],ref['source_sha256'],commit)]=source
    for kind,rows in (('provider',providers),('comparison',comparisons)):
        for row in rows:
            require(isinstance(row.get('source_commit'),str) and COMMIT.fullmatch(row['source_commit']) and
                row['source_commit']!=candidate['commit'] and row.get('status')=='validated',
                'INCREMENTAL_HISTORICAL_OUTCOME_OR_COMMIT_INVALID')
            require(APPROVED_HISTORICAL_SEALS.get(row['source_commit'])==row.get('seal_sha256'),
                'INCREMENTAL_HISTORICAL_SEAL_NOT_APPROVED')
            raw=load_ref({'file':row.get('source_file'),'sha256':row.get('source_sha256')},read)
            source=json.loads(raw)
            require(source.get('commit')==row['source_commit'] and source.get('synthetic_only') is True,
                'INCREMENTAL_HISTORICAL_SOURCE_IDENTITY')
            seal=json.loads(load_ref({'file':row.get('seal_file'),'sha256':row.get('seal_sha256')},read))
            original_name='provider-evaluation-final.json' if kind=='provider' else 'provider-comparison-final.json'
            require(seal.get('schema')=='core3-immutable-model-batch-archive-v1' and seal.get('commit')==row['source_commit']
                and all(seal.get(k) is True for k in ('completed_batch_verified','source_verified_start','source_verified_end',
                    'inspection_exact_run_set_verified')) and seal.get('production_changed') is False
                and seal.get('files_sha256',{}).get(original_name)==row['source_sha256']
                and seal.get('source_hashes_start')==seal.get('source_hashes_end')==seal.get('files_sha256'),
                'INCREMENTAL_HISTORICAL_SEAL_MISMATCH')
            wrapper=source.get('wrapper_execution',{})
            require(all(wrapper.get(k) is True for k in ('source_verified_start','source_verified_end','python_matches','cwd_matches'))
                and type(wrapper.get('exit_code')) is int and wrapper['exit_code'] in (0,1)
                and isinstance(wrapper.get('manifest_sha256_start'),str) and SHA.fullmatch(wrapper['manifest_sha256_start'])
                and wrapper.get('manifest_sha256_start')==wrapper.get('manifest_sha256_end')==seal.get('manifest_sha256'),
                'INCREMENTAL_HISTORICAL_EXECUTION_UNVERIFIED')
            used_sources[(kind,row['source_file'],row['source_sha256'],row['source_commit'])]=source
            require(any(all(ref.get(k)==row.get(k) for k in ('source_file','source_sha256','source_commit','seal_file','seal_sha256'))
                and ref['kind']==kind for ref in sources),'INCREMENTAL_HISTORICAL_COVERAGE_SOURCE_UNLISTED')
            index=row.get('source_sample_index') if kind=='provider' else row.get('source_row_index')
            values=source.get('samples' if kind=='provider' else 'rows',[])
            require(integer(index) and index<len(values),'INCREMENTAL_HISTORICAL_ROW_INDEX')
            actual=values[index]
            if kind=='provider':
                require(source.get('schema')=='core-provider-evaluation-v1' and actual.get('sample')==row['sample']
                    and actual.get('ok') is True and actual.get('validated',{}).get('valid') is True
                    and actual.get('validated',{}).get('schema')=='core3.0'
                    and actual.get('validated',{}).get('status')=='validated','INCREMENTAL_HISTORICAL_PROVIDER_FAILED')
                calls=actual.get('calls'); limit=10 if row['sample']=='fusion' else 6
                key='p:'+row['sample']
            else:
                require(source.get('schema_version')=='core-real-provider-four-arm-v1' and
                    (actual.get('arm'),actual.get('scenario'))==(row['arm'],row['scenario'])
                    and actual.get('status')=='validated' and actual.get('validation',{}).get('valid') is True
                    and actual.get('validation',{}).get('schema')=='core3.0'
                    and actual.get('validation',{}).get('status')=='validated','INCREMENTAL_HISTORICAL_CORE_FAILED')
                calls=actual.get('provider_calls'); limit=10 if row['arm']==CORE_ARMS[1] and row['scenario']=='tarot' else 6
                require(actual.get('durable_budget')=={'calls':calls,'limit':limit}
                    and actual.get('call_limit')==limit and isinstance(actual.get('calls'),list)
                    and len(actual['calls'])==calls,'INCREMENTAL_HISTORICAL_CORE_BUDGET')
                if row['scenario']=='tarot':
                    specialists=4 if row['arm']==CORE_ARMS[1] else 1
                    systems=sorted(('bazi','ziwei','astro','tarot') if specialists==4 else ('tarot',))
                    successful=[c for c in actual['calls'] if c.get('purpose','').startswith('specialist:')
                        and not c.get('error_type') and not c.get('error_code') and c.get('output_contract')=='SpecialistAnswer'
                        and isinstance(c.get('contract_output'),dict)]
                    require(actual.get('fixed_cards_unchanged') is True,'INCREMENTAL_HISTORICAL_CARDS_CHANGED')
                    require(actual.get('successful_specialist_provider_calls')==len(successful)==specialists and
                        actual.get('completed_specialist_systems')==systems and
                        sorted(c['contract_output'].get('system') for c in successful)==systems and
                        actual.get('successful_review_provider_calls')==int(specialists==4),
                        'INCREMENTAL_HISTORICAL_SPECIALISTS_MISSING')
                key='c:'+row['arm']+':'+row['scenario']
            require(integer(calls,1) and calls<=limit and row.get('historical_calls')==calls,
                'INCREMENTAL_HISTORICAL_CALLS_MISMATCH')
            historical_calls+=calls; keys.append(key)
    current=record.get('current_revalidation')
    require(isinstance(current,list) and Counter(r.get('coverage_key') for r in current)==Counter(keys),
        'INCREMENTAL_CURRENT_THIRTEEN_ROWS_MISSING')
    for row in current:
        require(row.get('status')=='validated' and row.get('validation_issues')==[]
            and type(row.get('real_provider_calls')) is int and row['real_provider_calls']==0
            and integer(row.get('model_substitute_calls')),
            'INCREMENTAL_CURRENT_REVALIDATION_FAILED')
        require(row.get('service_path') in ('actual_validator_only','postgresql_langgraph_service')
            and (row['coverage_key'].startswith('p:') or row['service_path']=='postgresql_langgraph_service'),
            'INCREMENTAL_CURRENT_REVALIDATION_SCOPE')
        require(isinstance(row.get('original_output_sha256'),str) and SHA.fullmatch(row['original_output_sha256'])
            and isinstance(row.get('replayed_output_sha256'),str) and SHA.fullmatch(row['replayed_output_sha256'])
            and row.get('opaque_ids_only_rebound') is True and isinstance(row.get('prose_sha256_start'),str)
            and SHA.fullmatch(row['prose_sha256_start']) and row.get('prose_sha256_end')==row['prose_sha256_start'],
            'INCREMENTAL_ORIGINAL_OUTPUT_CHANGED')
        selection=next(r for r in (providers if row['coverage_key'].startswith('p:') else comparisons)
            if row['coverage_key']==('p:'+r['sample'] if 'sample' in r else 'c:'+r['arm']+':'+r['scenario']))
        kind='provider' if row['coverage_key'].startswith('p:') else 'comparison'
        source=used_sources[(kind,selection['source_file'],selection['source_sha256'],selection['source_commit'])]
        if kind=='provider':
            inspection_raw=load_ref({'file':row.get('inspection_source_file'),'sha256':row.get('inspection_source_sha256')},read)
            seal=json.loads(load_ref({'file':selection['seal_file'],'sha256':selection['seal_sha256']},read))
            require(digest(inspection_raw)==seal['files_sha256']['candidate-model-inspection.json'],
                'INCREMENTAL_ORIGINAL_INSPECTION_NOT_SEALED')
            historical=source['samples'][selection['source_sample_index']]
            matches=[r for r in json.loads(inspection_raw).get('samples',[]) if r.get('id')==historical['run_id']]
            require(len(matches)==1,'INCREMENTAL_ORIGINAL_INSPECTION_RUN_MISSING')
            finals=[r['data']['output']['final'] for r in matches[0]['steps'] if r['data']['stage']=='validation']
            require(len(finals)==1 and json_digest(finals[0])==row['original_output_sha256']==row['replayed_output_sha256'],
                'INCREMENTAL_ORIGINAL_PROVIDER_OUTPUT_MISMATCH')
        else:
            historical=source['rows'][selection['source_row_index']]
            require(row.get('idempotent_replay_verified') is True and row.get('final_calls')==row['model_substitute_calls']
                and integer(row.get('final_calls'),1) and row['final_calls']<=historical['call_limit']
                and row.get('call_limit')==historical['call_limit']
                and (selection['scenario']!='tarot' or row.get('fixed_cards_unchanged') is True),
                'INCREMENTAL_CURRENT_SERVICE_REPLAY_INCOMPLETE')
            index=row.get('original_output_call_index')
            require(integer(index) and index<len(historical['calls']),'INCREMENTAL_ORIGINAL_OUTPUT_INDEX')
            call=historical['calls'][index]
            require(call.get('purpose')==row.get('original_output_phase') and
                call.get('purpose') in ('synthesis','review','repair') and isinstance(call.get('contract_output'),dict),
                'INCREMENTAL_ORIGINAL_OUTPUT_PHASE')
            original=call['contract_output'];bindings=row.get('opaque_id_bindings')
            require(isinstance(bindings,list) and all(isinstance(b,dict) and set(b)=={'old','new'} and
                all(isinstance(b.get(k),str) and re.fullmatch(r'(?:fact_|current_source_|claim-|chart-|tarot-|case_|draw_|msg_)[0-9a-f]{16,64}',b[k])
                    for k in ('old','new')) for b in bindings),'INCREMENTAL_REFERENCE_BINDINGS_INVALID')
            require(len({b['old'] for b in bindings})==len(bindings) and len({b['new'] for b in bindings})==len(bindings),
                'INCREMENTAL_REFERENCE_BINDINGS_AMBIGUOUS')
            def bind(value):
                if isinstance(value,dict):return {k:bind(v) for k,v in value.items()}
                if isinstance(value,list):return [bind(v) for v in value]
                if isinstance(value,str):
                    for b in bindings:value=value.replace(b['old'],b['new'])
                return value
            require(json_digest(original)==row['original_output_sha256'] and json_digest(bind(original))==row['replayed_output_sha256'],
                'INCREMENTAL_REPLAYED_PROSE_OR_STRUCTURE_CHANGED')
    failures=record.get('retained_failures')
    require(isinstance(failures,list),'INCREMENTAL_HISTORICAL_FAILURES_NOT_RETAINED')
    expected_failures=[]
    for (kind,name,source_sha,source_commit),source in used_sources.items():
        for index,row in enumerate(source.get('samples' if kind=='provider' else 'rows',[])):
            failed=row.get('ok') is not True if kind=='provider' else row.get('status')!='validated'
            if failed: expected_failures.append((kind,name,source_sha,source_commit,index,
                row.get('run_status','failed') if kind=='provider' else row.get('status')))
    require(Counter((r.get('kind'),r.get('source_file'),r.get('source_sha256'),r.get('source_commit'),
        r.get('source_index'),r.get('original_status')) for r in failures)==Counter(expected_failures),
        'INCREMENTAL_HISTORICAL_FAILURES_NOT_RETAINED')
    return {'historical_real_provider_categories':9,'historical_real_core_comparison_rows':4,
        'historical_calls_in_selected_coverage_rows':historical_calls,'current_recorded_output_rows':13,
        'current_stage_real_provider_calls':0,'current_provider_rows_reexecuted_against_model':0,
        'historical_failures_retained':len(record['retained_failures']),
        'scope':'Historical real coverage plus current recorded-output validation; not current real-model 9/9.'}


def assemble(candidate,manifest,manifest_hash,records,hashes,read,gate=None):
    gate=gate or frozen_gate()
    require(isinstance(candidate,dict) and isinstance(candidate.get('commit'),str) and COMMIT.fullmatch(candidate['commit'])
        and isinstance(candidate.get('tree'),str) and COMMIT.fullmatch(candidate['tree']),'INCREMENTAL_CANDIDATE_IDENTITY')
    canonical={name:row['sha256'] for name,row in manifest['files'].items()}
    require(manifest.get('schema')=='core3-release-v1' and manifest.get('commit')==candidate.get('commit')
        and len(canonical)==candidate.get('tracked_files'),'INCREMENTAL_CURRENT_MANIFEST_MISMATCH')
    require(gate.hash_map(canonical) and SHA.fullmatch(manifest_hash) and records.get('candidate')==candidate,
        'INCREMENTAL_CURRENT_MANIFEST_HASHES_INVALID')
    require(set(records)==INPUTS and set(hashes)==INPUTS,'INCREMENTAL_CURRENT_EVIDENCE_MISSING')
    raw=gate.check_local(candidate,canonical,records['local'],records['core_log'])
    replay=gate.check_replay(candidate,raw,records['replay'],records['fixed'],records['replay_preflight'],hashes)
    migration=gate.check_migration(candidate,records['migration'],manifest_hash,len(canonical))
    calc=records['calculators']
    require(calc.get('schema_version')=='core-calculation-validation-v1' and calc.get('synthetic_only') is True
        and calc.get('tests')=={'run':60,'passed':60,'skipped':0},'INCREMENTAL_CALCULATORS_NOT_PASSED')
    ui=gate.check_ui(candidate,records['stage_ui'],canonical)
    scope=gate.check_scope(records['preflight'],records['bindings'])
    native=check_native(candidate,manifest_hash,canonical,records['native_fence'],records['backup_restore'])
    history=check_history(candidate,manifest_hash,canonical,records['historical_revalidation'],read)
    for name in ('tests/test_core_8a7_decision_inference_denials.py','tests/test_core_8a7_ziwei_learning_limits.py'):
        require(name in canonical,'INCREMENTAL_AFFECTED_REGRESSIONS_NOT_IN_FIXED_SUITE')
    return {'schema':SCHEMA,'acceptance_method':METHOD,'commit':candidate['commit'],'tree':candidate['tree'],
        'database':'zhiming_core_stage','stage_accepted':True,'frontend_passed':True,'migration_replay_passed':True,
        'historical_real_provider_coverage_passed':True,'current_recorded_output_revalidation_passed':True,
        'current_live_provider_smoke':'required_before_publish','calculator_skips':0,'core_tests':records['local']['core_tests'],
        'core_test_skips':0,'frontend_commands_passed':6,'calculator_tests':60,'synthetic_replay':replay,
        'migration':migration,'readonly_stage_ui':ui,'scope':scope,'native':native,'incremental_model_evidence':history,
        'live_acceptance_requirement':{'runs':['preference','reading'],'max_calls_per_run':6,'max_total_calls':12,
            'replay_additional_calls':0,'external_sends':0},
        'source_provenance':{'manifest_files_count':len(canonical),'manifest_sha256':manifest_hash,
            'whole_tracked_start_end_unchanged':True,'local_canonical_matches_server_release':True,
            'fixed_python_and_cwd_verified':True,'frozen_gate_sha256':FROZEN_SHA256,'evidence_sha256':hashes},
        'external_test_messages_sent':0,'production_cutover':'pending','long_term_professional_quality':'not_verified'}


def validate_acceptance(report,commit,manifest_bytes,read,gate=None):
    require(isinstance(report,dict) and report.get('schema')==SCHEMA and report.get('commit')==commit,
        'INCREMENTAL_ACCEPTANCE_IDENTITY')
    refs=report.get('evidence_files')
    require(isinstance(refs,dict) and set(refs)==INPUTS,'INCREMENTAL_EVIDENCE_REFERENCES_MISSING')
    records={}; hashes={}
    for key,ref in refs.items():
        raw=load_ref(ref,read); hashes[key]=digest(raw)
        records[key]=raw if key=='core_log' else json.loads(raw)
    rebuilt=assemble(records['candidate'],json.loads(manifest_bytes),digest(manifest_bytes),records,hashes,read,gate)
    require(all(report.get(key)==value for key,value in rebuilt.items()),'INCREMENTAL_ACCEPTANCE_SUMMARY_MISMATCH')
    return report


def validate_live_acceptance(report,commit):
    require(isinstance(report,dict) and report.get('schema')=='core3-live-http-acceptance-v1'
        and report.get('commit')==commit and report.get('passed') is True and report.get('errors')==[],
        'INCREMENTAL_LIVE_ACCEPTANCE_FAILED')
    require(type(report.get('external_sends')) is int and report['external_sends']==0,
        'INCREMENTAL_LIVE_EXTERNAL_EFFECT')
    require(all(report.get('checks',{}).get(k) is True for k in LIVE_CHECKS)
        and all(report.get('cleanup',{}).get(k) is True for k in CLEANUP)
        and type(report.get('cleanup',{}).get('cancelled_for_cleanup',0)) is int
        and report.get('cleanup',{}).get('cancelled_for_cleanup',0)==0,'INCREMENTAL_LIVE_CHECKS_INCOMPLETE')
    calls=report.get('calls',{})
    require(set(calls)=={'preference','reading'} and all(integer(v,1) and v<=6 for v in calls.values())
        and sum(calls.values())<=12,'INCREMENTAL_LIVE_BUDGET_EXCEEDED')
    statuses=report.get('statuses',{})
    require(isinstance(statuses.get('synthetic_final'),list) and bool(statuses['synthetic_final'])
        and all(isinstance(statuses.get(k),list) and all(isinstance(r,dict) and
        isinstance(r.get('status'),str) and r['status'] not in ('queued','running') for r in statuses[k])
        for k in ('synthetic_runs','synthetic_final')),'INCREMENTAL_LIVE_RUNS_NOT_DRAINED')
    return report
