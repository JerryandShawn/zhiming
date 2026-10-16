"""Verify the explicit continuation of one failed, already charged live run.

No provider, database, HTTP or host operation is performed here. The failed
v1 evidence stays failed; current acceptance covers cached-output recovery and
the remaining real HTTP checks, with no fresh provider allowance.
"""
from collections import Counter
import hashlib
import json
import re

SCHEMA='core3-live-http-zero-model-recovery-v2'
ORIGINAL_COMMIT='890c32ea3e645981b539060088135d375fe19bb1'
ORIGINAL_HASHES={
    'original_failed':'614a0956fe1e648b44a2cc4728431ea755108abdda1633d43d48eeebb1d582cd',
    'original_inspection':'021ad0c85dbcc64bb849d75a684d80f45bbdfd0488e6f2a2172f726f227b9202',
    'original_budget_claim':'bfcb87fac3a0fd58566ce8096f8470b3850a31ca877cc9cb25a5f3f55472fede',
    'original_budget_result':'e4d77aeeade1046ee5f88115d8d7cd94e1d802d837ff9c978c9828f928189f7f',
}
PRIOR_CHECKS=('fresh_synthetic_scope_empty','explicit_save_and_chat_replay',
    'correction_source_delete_and_replay','case_manual_three_cards_reveal_and_conflict')
RECOVERED_CHECKS=('real_reading_and_exact_replay','draw_delete_clears_http_history_chat_and_run',
    'primary_http_and_pg_unchanged')
CLEANUP=('environment_restored','alias_removed','alias_removed_verified_401','all_runs_quiescent',
    'web_running_behind_maintenance','primary_unchanged_after_restore')
CACHED_STAGES=('model:intake','intake','memory','snapshot','plan','calculation',
    'model:specialist:tarot','specialists','model:synthesis','synthesis','review','model:repair')


def require(value,code):
    if not value:raise ValueError(code)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str).encode())


def integer(value,expected):return type(value) is int and value==expected


def validate_acceptance(report,commit,read,manifest_bytes):
    from tools.incremental_acceptance import load_ref
    require(isinstance(report,dict) and report.get('schema')==SCHEMA and report.get('commit')==commit
        and isinstance(commit,str) and re.fullmatch('[0-9a-f]{40}',commit) and commit!=ORIGINAL_COMMIT
        and report.get('original_attempt_commit')==ORIGINAL_COMMIT,'RECOVERY_ACCEPTANCE_IDENTITY')
    require(callable(read) and isinstance(manifest_bytes,bytes),'RECOVERY_PROTECTED_DEPENDENCIES_REQUIRED')
    refs=report.get('evidence_files')
    require(isinstance(refs,dict) and set(refs)==set(ORIGINAL_HASHES),'RECOVERY_ORIGINAL_EVIDENCE_SET')
    originals={}
    for key,expected in ORIGINAL_HASHES.items():
        require(refs[key].get('sha256')==expected,'RECOVERY_ORIGINAL_PIN_CHANGED')
        originals[key]=json.loads(load_ref(refs[key],read))
    failed=originals['original_failed'];inspection=originals['original_inspection']
    claim=originals['original_budget_claim'];budget=originals['original_budget_result']
    require(isinstance(inspection,list) and len(inspection)==1,'RECOVERY_ORIGINAL_INSPECTION_SET')
    original=inspection[0]['run']
    require(failed.get('schema')=='core3-live-http-acceptance-v1' and failed.get('commit')==ORIGINAL_COMMIT
        and failed.get('passed') is False and failed.get('errors')==[{'check':'synthetic-http','code':'CORE_MODEL_RUN_FAILED'}]
        and failed.get('checks')=={k:True for k in PRIOR_CHECKS} and failed.get('calls')=={'preference':2}
        and integer(failed.get('external_sends'),0),'RECOVERY_ORIGINAL_FAILED_HTTP_CHANGED')
    require(all(failed.get('cleanup',{}).get(k) is True for k in
        ('environment_restored','alias_removed','web_restarted','synthetic_runs_drained'))
        and integer(failed['cleanup'].get('cancelled_for_cleanup',0),0),'RECOVERY_ORIGINAL_CLEANUP_INCOMPLETE')
    require(original.get('owner')==failed.get('synthetic_owner') and original.get('status')=='failed'
        and all(integer(original.get(k),v) for k,v in (('calls',4),('call_limit',6),('retry_epoch',0),('attempts',1)))
        and original.get('repair_used') is True and original.get('request',{}).get('mode')=='tarot'
        and original['request'].get('depth')=='standard'
        and original.get('operation_id','').startswith('reading:acceptance-reading-'),'RECOVERY_ORIGINAL_RUN_CHANGED')
    require(claim.get('schema')=='core3-live-model-budget-v1' and claim.get('commit')==ORIGINAL_COMMIT
        and claim.get('business_depth')=='standard' and claim.get('business_call_limits')=={'preference':6,'reading':6}
        and all(integer(claim.get(k),v) for k,v in (('max_attempts',1),('attempts_reserved',1),('max_total_model_calls',12)))
        and claim.get('retry_allowed') is False and claim.get('claim_survives_failure_or_crash') is True,
        'RECOVERY_ORIGINAL_ALLOWANCE_REOPENED')
    require(budget.get('schema')=='core3-live-model-budget-result-v1' and budget.get('commit')==ORIGINAL_COMMIT
        and budget.get('passed') is False and budget.get('retry_allowed') is False and budget.get('attempt_started') is True
        and budget.get('source_verified_start') is True and budget.get('source_verified_end') is True
        and integer(budget.get('runner_exit_code'),1) and integer(budget.get('max_total_model_calls'),12)
        and budget.get('claim_sha256')==ORIGINAL_HASHES['original_budget_claim']
        and budget.get('acceptance',{}).get('report_sha256')==ORIGINAL_HASHES['original_failed']
        and integer(budget['acceptance'].get('calls_from_final_run_metadata'),6),'RECOVERY_FAILED_BUDGET_RESULT_CHANGED')
    require(report.get('original_failed_report_sha256')==ORIGINAL_HASHES['original_failed']
        and report.get('original_inspection_sha256')==ORIGINAL_HASHES['original_inspection']
        and report.get('original_budget_claim_sha256')==ORIGINAL_HASHES['original_budget_claim']
        and report.get('original_budget_result_sha256')==ORIGINAL_HASHES['original_budget_result'],
        'RECOVERY_ORIGINAL_SUMMARY_HASHES_CHANGED')
    candidate=json.loads(read('candidate-release.json'));manifest=json.loads(manifest_bytes)
    source={'commit':commit,'tree':candidate.get('tree'),'manifest_sha256':sha(manifest_bytes),
        'tracked_files':candidate.get('tracked_files')}
    require(candidate.get('commit')==commit and isinstance(source['tree'],str) and re.fullmatch('[0-9a-f]{40}',source['tree'])
        and manifest.get('schema')=='core3-release-v1' and manifest.get('commit')==commit
        and isinstance(manifest.get('files'),dict) and len(manifest['files'])==source['tracked_files']
        and 'tests/test_core_live_tarot_guarantee_denial.py' in manifest['files']
        and report.get('tree')==source['tree'] and report.get('source_start')==report.get('source_end')==source
        and all(report.get(k) is True for k in ('source_verified_start','source_verified_end','fixed_source_verified_start_and_end')),
        'RECOVERY_CURRENT_FIXED_SOURCE_MISMATCH')
    expected={}
    prefix=original['id']+':e0:'
    for entity in inspection[0]['entities']:
        if entity.get('kind')=='runtime_step' and entity.get('status')!='deleted' and entity.get('id','').startswith(prefix):
            data=entity['data'];require(data.get('stage') not in expected,'RECOVERY_DUPLICATE_CACHED_STAGE')
            expected[data['stage']]=digest(data['output'])
    model_calls=[e['data'].get('purpose') for e in inspection[0]['entities'] if e.get('kind')=='model_call'
        and e.get('status')=='succeeded' and e.get('data',{}).get('run_id')==original['id']]
    require(set(expected)==set(CACHED_STAGES) and Counter(model_calls)==Counter(('intake','specialist:tarot','synthesis','repair'))
        and report.get('cache_sha256')==report.get('cache_after_execution_sha256')==expected,
        'RECOVERY_ORIGINAL_CACHE_CHANGED')
    require(all(report.get(k)==original[v] for k,v in (('run_id','id'),('operation_id','operation_id'),
        ('request_fingerprint','fingerprint'))) and report.get('draw_id')==original['request']['draw_id']
        and report.get('reading_id')==original['request']['reading_id'],'RECOVERY_OPERATION_REPLACED')
    direct=report.get('direct_recovery',{})
    require(all(direct.get(k) is True for k in ('same_run','same_operation','same_fingerprint','same_draw','same_reading',
        'repair_used_before','repair_used_after')) and all(integer(direct.get(k),v) for k,v in
        (('calls_before',4),('calls_after',4),('call_limit_before',6),('call_limit_after',6),('retry_epoch_before',0),
         ('retry_epoch_after',0),('attempts_before',1),('attempts_after',2)))
        and direct.get('status_before')=='failed' and direct.get('status_after')=='succeeded'
        and isinstance(direct.get('result_sha256'),str) and re.fullmatch('[0-9a-f]{64}',direct['result_sha256']),
        'RECOVERY_IDENTITY_OR_BUDGET_CHANGED')
    require(report.get('original_attempt_passed') is False and report.get('original_failed_evidence_preserved') is True
        and report.get('original_allowance_still_consumed') is True and report.get('original_checks')==failed['checks']
        and report.get('checks')=={k:True for k in RECOVERED_CHECKS}
        and report.get('passed') is True and report.get('errors')==[],'RECOVERY_NOT_ACTUALLY_COMPLETED')
    require(all(integer(report.get(k),v) for k,v in (('original_recorded_provider_calls',6),('additional_provider_calls',0),
        ('additional_model_charges',0),('external_test_messages_sent',0)))
        and report.get('guards')=={'charge_attempts':0,'provider_attempts':0}
        and all(type(v) is int for v in report['guards'].values())
        and report.get('temporary_http_provider_credentials_removed') is True,'RECOVERY_NEW_MODEL_ALLOWANCE_OR_EFFECT')
    require(all(report.get('cleanup',{}).get(k) is True for k in CLEANUP),'RECOVERY_CLEANUP_INCOMPLETE')
    runs=report.get('synthetic_final',{}).get('runs',[])
    require(isinstance(runs,list) and len(runs)==2 and Counter((r.get('calls'),r.get('call_limit'),r.get('status')) for r in runs)==
        Counter(((2,6,'revoked'),(4,6,'revoked'))),'RECOVERY_RUNS_NOT_REVOKED_OR_BUDGET_CHANGED')
    counts=report.get('synthetic_final',{}).get('counts',{}).get('counts',{})
    require(all(integer(counts.get(k),0) for k in ('core_channels','delivery_outbox','tarot_draws','tarot_readings'))
        and integer(counts.get('core_runs'),2),'RECOVERY_DELETION_OR_EXTERNAL_SCOPE_FAILED')
    before=report.get('primary_before')
    require(isinstance(before,dict) and before.get('counts')==failed.get('counts',{}).get('primary_before')
        and isinstance(before.get('fingerprints'),dict) and bool(before['fingerprints'])
        and report.get('primary_after')==before,'RECOVERY_PRIMARY_SCOPE_CHANGED')
    return report
