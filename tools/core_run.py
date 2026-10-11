"""Inspect or resume one owner-scoped Core run; never import a retired controller."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mingjing_core.application.consultation import ConsultationService
from mingjing_core.domain.contracts import LeaseConflict


def execute_command(service, *, owner, run_id, action='status'):
    run = service.repo.fetch_run(owner, run_id)
    if action == 'status':
        return {'schema_version': 'core3.0', 'run_id': run['id'],
                'status': run['status'], 'phase': run['checkpoint'].get('phase'),
                'budget': {'calls': run['calls'], 'limit': run['call_limit']},
                'retry_epoch': run.get('retry_epoch', 0), 'subject_id': run['subject']}
    if action == 'result':
        if run['status'] != 'succeeded':
            raise LeaseConflict('本轮结果尚未提交')
        return run['result']
    if action not in ('resume', 'retry'):
        raise ValueError('Unknown run action')
    if run['status'] == 'succeeded':
        return run['result']
    if run['status'] in ('failed', 'stale'):
        prepared = service.repo.prepare_retry(owner, run_id)
        if prepared['purge_checkpoint']:
            service.runtime.purge(run_id, run.get('retry_epoch', 0))
    elif run['status'] != 'queued':
        raise LeaseConflict('请等待当前工作者；已停止或撤销的请求不可恢复')
    if run['request'].get('reading_id'):
        service.tarot.resume_reading(owner, run['request']['reading_id'], run_id)
    result = service.execute(owner, run_id)
    if run['request'].get('reading_id'):
        service.tarot.finish_reading(owner, run['request']['reading_id'],
                                     result=result, validation=result['validation'])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'result', 'retry', 'resume'))
    parser.add_argument('--owner', required=True)
    parser.add_argument('--run', required=True, dest='run_id')
    args = parser.parse_args(argv)
    service = ConsultationService.from_base()
    try:
        result = execute_command(service, owner=args.owner, run_id=args.run_id, action=args.action)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    finally:
        service.repo.close()


if __name__ == '__main__':
    main()
