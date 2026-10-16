"""Withdraw only the persisted lineage of deleted draws, never unrelated history."""
from __future__ import annotations

from psycopg import sql


def _source_links(data):
    return (set(data.get('source_ids', [])) |
            {ref.get('message_id') for ref in data.get('source_refs', [])} |
            {data.get('message_id'), data.get('source_message_id')}) - {None}


def revoke_draw_dependencies(repo, conn, owner, draws, readings):
    """Called inside the owner transaction, before the draw FK cascade.

    Ordinary authenticated chat originals and facts merely read by a draw stay
    available. Only its dedicated draw-action and generated reading originals
    are withdrawn through the repository's normal, restore-safe deletion API.
    """
    draw_ids = {draw['id'] for draw in draws}
    reading_ids = {reading['id'] for reading in readings}
    reading_runs = set()
    for reading in readings:
        payload = reading['payload']
        reading_runs.add(payload.get('execution_snapshot', {}).get('run_id'))
        reading_runs.add((payload.get('result') or {}).get('meta', {}).get('core_run', {}).get('run_id'))
    reading_runs.discard(None)
    runs = conn.execute(sql.SQL('SELECT id,subject,operation_id,request,result,state_version FROM {} WHERE owner=%s FOR UPDATE').format(
        repo.table('core_runs')), (owner,)).fetchall()
    affected = {run['id'] for run in runs if run['id'] in reading_runs or
                run['request'].get('draw_id') in draw_ids or
                run['request'].get('reading_id') in reading_ids or
                (run['result'] or {}).get('meta', {}).get('draw_id') in draw_ids}
    messages = repo.list(owner, 'message', include_deleted=True)
    by_id = {message['id']: message for message in messages}
    sources = set()
    create_keys = {row['request_key'] for row in conn.execute(sql.SQL(
        "SELECT request_key FROM {} WHERE owner=%s AND operation='create' AND result_id=ANY(%s)").format(
            repo.table('tarot_requests')), (owner, list(draw_ids))).fetchall()}
    for draw in draws:
        message_id = draw['payload'].get('context_snapshot', {}).get('question_message_id')
        message = by_id.get(message_id)
        if (message and message.get('channel') == 'web-action' and message.get('role') == 'user' and
                message['subject_id'] == draw['subject'] and
                message.get('source_id') in {'draw:' + key for key in create_keys}):
            sources.add(message_id)
    sources.update(message['id'] for message in messages if message.get('channel') == 'web-action' and
                   message.get('role') == 'user' and message.get('source_id') in {'draw:' + key for key in create_keys} and
                   message['subject_id'] in {draw['subject'] for draw in draws})
    operations = {(run['operation_id'], run['subject']) for run in runs if run['id'] in affected}
    sources.update(message['id'] for message in messages if message.get('channel') == 'tarot' and
                   message.get('role') == 'user' and (message.get('source_id'), message['subject_id']) in operations)
    # Assistant/tool copies are derived, unlike user messages that happen to
    # mention the same cards or question.
    while True:
        copied = {message['id'] for message in messages if message.get('role') in ('assistant', 'tool') and
                  _source_links(message).intersection(sources)}
        expanded = sources | copied
        if expanded == sources:
            break
        sources = expanded
    facts = {fact['id'] for fact in repo.list(owner, 'fact', include_deleted=True)
             if _source_links(fact).intersection(sources)}
    dependencies = {'message:' + ident for ident in sources} | {'fact:' + ident for ident in facts}
    # Recorded history dependencies and explicit clarification ancestry are
    # authoritative links. Owner/global revision changes alone are not links.
    while True:
        expanded = affected | {run['id'] for run in runs if dependencies.intersection(run['state_version']) or
                               _source_links(run['request']).intersection(sources) or
                               run['request'].get('parent_run') in affected}
        if expanded == affected:
            break
        affected = expanded
    for message_id in sorted(sources):
        message = by_id[message_id]
        repo.delete(owner, 'message', message_id, expected_revision=message['revision'])
    for case in repo.list(owner, 'case'):
        refs = case.get('source_refs', [])
        removed = [ref for ref in refs if ref.get('message_id') in sources]
        if not removed:
            continue
        remaining = [ref for ref in refs if ref.get('message_id') not in sources]
        changes = {'source_refs': remaining, 'source_revoked': True}
        # Automatically created case titles are a projection of the draw
        # question. Preserve a later independently changed title/goal and the
        # case identity, independent events and other fixed draws.
        originals = [by_id[ref['message_id']].get('content', '') for ref in removed]
        if not remaining:
            drawn_titles = {draw['payload'].get('question', '')[:120] for draw in draws
                            if draw['case_id'] == case['id']}
            if case.get('title') in drawn_titles or any(case.get('title') == original[:120] for original in originals):
                changes['title'] = '已删除牌阵的问题'
            state = dict(case.get('state', {}))
            if state.get('goal') and any(state['goal'] in original for original in originals):
                state['goal'] = ''
            state['pending'] = []
            changes['state'] = state
        repo.update(owner, 'case', case['id'], changes, expected_revision=case['revision'])
    for kind in ('fact', 'consent', 'episode', 'feedback', 'request', 'upload'):
        for entity in repo.list(owner, kind, include_deleted=True):
            if entity['status'] == 'deleted':
                continue
            linked_facts = set(entity.get('fact_ids', []))
            linked_run = entity.get('run_id') in affected
            if not (_source_links(entity).intersection(sources) or linked_facts.intersection(facts) or linked_run):
                continue
            if kind == 'upload':
                repo.enqueue_media_deletion(owner, entity)
            repo.delete(owner, kind, entity['id'], expected_revision=entity['revision'])
    if affected:
        ids = sorted(affected)
        conn.execute(sql.SQL("UPDATE {} SET request='{{}}',result=NULL,checkpoint='{{}}',status='revoked',error='TAROT_DELETED',lease_token=NULL,lease_until=NULL,updated_at=now() WHERE owner=%s AND id=ANY(%s)").format(
            repo.table('core_runs')), (owner, ids))
        conn.execute(sql.SQL("UPDATE {} SET data='{{}}',status='deleted',revision=revision+1,updated_at=now() WHERE owner=%s AND kind IN ('runtime_step','interpretive_claim','artifact','model_call','report') AND data->>'run_id'=ANY(%s)").format(
            repo.table('core_entities')), (owner, ids))
        conn.execute(sql.SQL("UPDATE {} SET payload='{{}}',dependencies='{{}}',status=CASE WHEN status IN ('sending','uncertain') THEN 'uncertain' WHEN status='sent' THEN 'sent' ELSE 'cancelled' END,claim_token=NULL,lease_until=NULL,error='TAROT_DELETED',updated_at=now() WHERE owner=%s AND run_id=ANY(%s)").format(
            repo.table('delivery_outbox')), (owner, ids))
    return {'affected_ids': sorted(affected), 'source_ids': sorted(sources), 'fact_ids': sorted(facts)}


def purge_deleted_checkpoints(service, owner, receipt):
    """Run after the atomic deletion/receipt transaction has committed.

    Stable DELETE replay intentionally repeats this cleanup. A live graph also
    purges in ConsultationService.execute.finally after a late provider return.
    """
    for run_id in receipt.get('affected_ids', []):
        run = service.repo.fetch_run(owner, run_id)
        if run['status'] != 'revoked' or run['error'] != 'TAROT_DELETED':
            continue
        for epoch in range(run.get('retry_epoch', 0) + 1):
            service.runtime.purge(run_id, epoch)


def purge_committed_checkpoints(repo, owner, receipt):
    """The direct adapter path has no enclosing HTTP mutation transaction."""
    if not receipt.get('affected_ids'):
        return
    from langgraph.checkpoint.postgres import PostgresSaver
    checkpointer = PostgresSaver(repo.pool)
    for run_id in receipt['affected_ids']:
        run = repo.fetch_run(owner, run_id)
        for epoch in range(run.get('retry_epoch', 0) + 1):
            checkpointer.delete_thread(run_id + ':e' + str(epoch))
