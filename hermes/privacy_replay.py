"""Export content-free revocations and apply them to explicitly selected restores.

Export: python privacy_replay.py --export --owner ID --state-db CURRENT/state.sqlite
        --tarot-db CURRENT/tarot.db --file revocations.json
Replay: python privacy_replay.py --apply --owner ID --restore-state-db RESTORE/state.sqlite
        --restore-tarot-db RESTORE/tarot.db --file revocations.json

Run before exposing a restored deployment. Inputs are trusted operator files;
they contain IDs and hashed retry keys, never user prose or plaintext retry keys.
Only the two selected restore databases are changed. External history/archive
caches must be rebuilt separately by the restore workflow.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _key_hash(value):
    # Matches tarot_store._hash exactly; no plaintext request keys are exported.
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _database(path, mode):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError('Expected an existing SQLite file')
    return path, path.as_uri() + '?mode=' + mode


def _identifier(value, limit=500):
    if not isinstance(value, str) or not value or len(value) > limit or any(ord(ch) < 32 for ch in value):
        raise ValueError('Invalid scoped identifier')
    return value


def _validate(data, owner):
    _identifier(owner, 160)
    if not isinstance(data, dict) or set(data) != {'format', 'owner', 'exported_at', 'suppressions', 'tombstones', 'tarot_deleted_requests'}:
        raise ValueError('Unsupported revocation document')
    if data['format'] != 'zhiming-privacy-replay-v1' or data['owner'] != owner:
        raise ValueError('Revocation owner or format does not match')
    datetime.fromisoformat(data['exported_at'])
    for key in ('suppressions', 'tombstones', 'tarot_deleted_requests'):
        if not isinstance(data[key], list) or len(data[key]) > 100000:
            raise ValueError('Invalid revocation collection')
    for row in data['suppressions']:
        if not isinstance(row, dict) or set(row) != {'source', 'source_id', 'operation', 'purge_message'}:
            raise ValueError('Invalid source revocation')
        _identifier(row['source'], 120); _identifier(row['source_id'])
        if row['operation'] not in ('stopped', 'deleted') or type(row['purge_message']) is not bool:
            raise ValueError('Invalid source operation')
        if row['purge_message'] and row['operation'] != 'deleted':
            raise ValueError('Purged sources must remain deleted')
    for row in data['tombstones']:
        if not isinstance(row, dict) or set(row) != {'entity_type', 'entity_id', 'operation'}:
            raise ValueError('Invalid entity tombstone')
        if row['entity_type'] != 'fact' or row['operation'] not in ('stopped', 'deleted'):
            raise ValueError('Unsupported entity tombstone operation')
        _identifier(row['entity_id'])
    for row in data['tarot_deleted_requests']:
        if not isinstance(row, dict) or set(row) != {'operation', 'key_hash'}:
            raise ValueError('Invalid tarot request tombstone')
        if row['operation'] not in ('create', 'select', 'revise', 'reading') or not re.fullmatch('[0-9a-f]{64}', str(row['key_hash'])):
            raise ValueError('Invalid tarot request operation or hash')
    return data


def export_privacy(owner, state_db, tarot_db, output):
    """Read-only export. Refuses an existing output file; creates mode 0600."""
    _identifier(owner, 160)
    state_path, state_uri = _database(state_db, 'ro')
    tarot_path, tarot_uri = _database(tarot_db, 'ro')
    if state_path == tarot_path:
        raise ValueError('State and tarot databases must be distinct')
    connection = sqlite3.connect(state_uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('ATTACH DATABASE ? AS tarot', (tarot_uri,))
        connection.execute('BEGIN')
        if not connection.execute('SELECT 1 FROM owners WHERE id=?', (owner,)).fetchone():
            raise ValueError('Owner not present in source state database')
        suppressions = []
        for row in connection.execute('SELECT source,source_id,reason,purge_message FROM suppressions WHERE owner=? ORDER BY source,source_id', (owner,)):
            suppressions.append({'source': row['source'], 'source_id': row['source_id'],
                                 'operation': 'deleted' if row['purge_message'] or 'deleted' in row['reason'] else 'stopped',
                                 'purge_message': bool(row['purge_message'])})
        data = {'format': 'zhiming-privacy-replay-v1', 'owner': owner, 'exported_at': _now(),
                'suppressions': suppressions,
                'tombstones': [dict(row) for row in connection.execute('SELECT entity_type,entity_id,operation FROM tombstones WHERE owner=? ORDER BY entity_type,entity_id', (owner,))],
                'tarot_deleted_requests': [dict(row) for row in connection.execute('SELECT operation,key_hash FROM tarot.tarot_deleted_requests WHERE owner=? ORDER BY operation,key_hash', (owner,))]}
        _validate(data, owner)
    finally:
        connection.close()
    output = Path(output).absolute()
    if output.resolve() in (state_path, tarot_path):
        raise ValueError('Export output cannot be a database')
    descriptor = os.open(str(output), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as target:
        os.chmod(output, 0o600)
        target.write(_json(data) + '\n')
        target.flush(); os.fsync(target.fileno())
    return {'exported': True, 'suppression_count': len(data['suppressions']),
            'tombstone_count': len(data['tombstones']), 'tarot_key_count': len(data['tarot_deleted_requests'])}


def _references(refs, sources):
    return [(ref['source'], str(ref['id'])) for ref in refs
            if (ref.get('source'), str(ref.get('id'))) in sources]


def _contains_id(value, targets):
    if isinstance(value, dict):
        return any(_contains_id(k, targets) or _contains_id(v, targets) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_id(v, targets) for v in value)
    return isinstance(value, str) and any(value == ident or value.endswith(':' + ident) for ident in targets)


def apply_privacy(owner, restore_state_db, restore_tarot_db, document):
    """Replay only to existing explicit targets, in one SQLite transaction.

    Any tarot request matching a revoked hash causes its restored draw to be
    deleted, including readings and retry keys. This conservatively also drops
    draws whose prior context was revoked, since old tombstones do not encode
    whether the original operation was draw deletion or context revocation.
    """
    data = _validate(json.loads(Path(document).read_text(encoding='utf-8')), owner)
    state_path, state_uri = _database(restore_state_db, 'rw')
    tarot_path, tarot_uri = _database(restore_tarot_db, 'rw')
    if state_path == tarot_path or Path(document).resolve() in (state_path, tarot_path):
        raise ValueError('Replay inputs and target databases must be distinct')
    connection = sqlite3.connect(state_uri, uri=True)
    connection.row_factory = sqlite3.Row
    report = {'applied': True, 'sources_recorded': 0, 'tombstones_recorded': 0, 'facts_revoked': 0, 'messages_purged': 0,
              'cases_invalidated': 0, 'case_events_deleted': 0, 'traces_deleted': 0,
              'tarot_draws_deleted': 0, 'tarot_keys_recorded': 0}
    try:
        connection.execute('ATTACH DATABASE ? AS tarot', (tarot_uri,))
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA main.secure_delete=ON')
        connection.execute('PRAGMA tarot.secure_delete=ON')
        if any(connection.execute('PRAGMA ' + schema + '.journal_mode').fetchone()[0].lower() == 'wal'
               for schema in ('main', 'tarot')):
            raise ValueError('Offline restore targets must use rollback journals for atomic replay')
        connection.execute('BEGIN IMMEDIATE')
        current = connection.execute('SELECT revision FROM owners WHERE id=?', (owner,)).fetchone()
        if not current:
            raise ValueError('Owner not present in selected restore database')
        stamp = _now(); revision = current['revision'] + 1
        sources = {}
        for row in data['suppressions']:
            key = (row['source'], row['source_id'])
            old = connection.execute('SELECT reason,purge_message FROM suppressions WHERE owner=? AND source=? AND source_id=?', (owner, *key)).fetchone()
            deleting = row['operation'] == 'deleted' or bool(old and (old['purge_message'] or 'deleted' in old['reason']))
            purge = row['purge_message'] or bool(old and old['purge_message'])
            operation = 'deleted' if deleting else 'stopped'
            sources[key] = operation
            if not old or (purge and not old['purge_message']) or (deleting and 'deleted' not in old['reason']):
                connection.execute('INSERT INTO suppressions VALUES(?,?,?,?,?,?) ON CONFLICT(owner,source,source_id) DO UPDATE SET reason=excluded.reason,purge_message=excluded.purge_message,at=excluded.at',
                                   (owner, *key, 'privacy_replay_' + operation, int(purge), stamp))
                report['sources_recorded'] += 1
            if purge:
                report['messages_purged'] += connection.execute("UPDATE messages SET content='',status='deleted' WHERE owner=? AND source=? AND source_id=? AND (content!='' OR status!='deleted')", (owner, *key)).rowcount
        tombstones = {row['entity_id']: row['operation'] for row in connection.execute("SELECT entity_id,operation FROM tombstones WHERE owner=? AND entity_type='fact'", (owner,))}
        for row in data['tombstones']:
            if tombstones.get(row['entity_id']) != 'deleted':
                tombstones[row['entity_id']] = row['operation']
        affected_ids = set(tombstones)
        message_ids = set()
        for source, source_id in sources:
            message_ids.update(row[0] for row in connection.execute('SELECT id FROM messages WHERE owner=? AND source=? AND source_id=?', (owner, source, source_id)))
        for row in connection.execute('SELECT * FROM facts WHERE owner=?', (owner,)).fetchall():
            refs = json.loads(row['source_refs']); matched = _references(refs, sources)
            if row['id'] not in tombstones and not matched:
                continue
            affected_ids.add(row['id'])
            deleting = row['status'] == 'deleted' or tombstones.get(row['id']) == 'deleted' or any(sources[key] == 'deleted' for key in matched)
            status = 'deleted' if deleting else 'stopped'
            content = '' if deleting else row['content']
            clean_refs = _json([{k: v for k, v in ref.items() if k != 'quote'} for ref in refs]) if deleting else row['source_refs']
            value = None if deleting else row['value_json']
            if (row['status'], row['content'], row['source_refs'], row['value_json']) != (status, content, clean_refs, value):
                connection.execute('UPDATE facts SET status=?,content=?,source_refs=?,value_json=?,revision=? WHERE owner=? AND id=?',
                                   (status, content, clean_refs, value, revision, owner, row['id']))
                report['facts_revoked'] += 1
            tombstones[row['id']] = status
        for ident, operation in tombstones.items():
            old = connection.execute("SELECT operation FROM tombstones WHERE owner=? AND entity_type='fact' AND entity_id=?", (owner, ident)).fetchone()
            if not old or (operation == 'deleted' and old['operation'] != 'deleted'):
                connection.execute('INSERT INTO tombstones VALUES(?,?,?,?,?,?) ON CONFLICT(owner,entity_type,entity_id) DO UPDATE SET operation=excluded.operation,revision=excluded.revision,at=excluded.at',
                                   (owner, 'fact', ident, operation, revision, stamp))
                report['tombstones_recorded'] += 1
        targets = affected_ids | message_ids | {ident for _, ident in sources}
        for row in connection.execute('SELECT * FROM cases WHERE owner=?', (owner,)).fetchall():
            refs = json.loads(row['source_refs'])
            if _references(refs, sources) or _contains_id(json.loads(row['state']), targets):
                remaining = [ref for ref in refs if not _references([ref], sources)]
                connection.execute('UPDATE cases SET title=?,state=?,source_refs=?,revision=?,updated_at=? WHERE owner=? AND id=?',
                                   ('待重新确认的事项', _json({'pending': ['资料已撤销，请重新确认背景']}), _json(remaining), revision, stamp, owner, row['id']))
                report['cases_invalidated'] += 1
        for row in connection.execute('SELECT id,source_refs FROM case_events WHERE owner=?', (owner,)).fetchall():
            if _references(json.loads(row['source_refs']), sources):
                report['case_events_deleted'] += connection.execute('DELETE FROM case_events WHERE owner=? AND id=?', (owner, row['id'])).rowcount
        if sources or tombstones or data['tarot_deleted_requests']:
            report['traces_deleted'] = connection.execute('DELETE FROM traces WHERE owner=?', (owner,)).rowcount
        for row in data['tarot_deleted_requests']:
            report['tarot_keys_recorded'] += connection.execute('INSERT OR IGNORE INTO tarot.tarot_deleted_requests VALUES(?,?,?)', (owner, row['operation'], row['key_hash'])).rowcount
        hashes = {(row['operation'], row['key_hash']) for row in connection.execute('SELECT operation,key_hash FROM tarot.tarot_deleted_requests WHERE owner=?', (owner,))}
        delete_draws = {row['draw_id'] for row in connection.execute('SELECT operation,request_key,draw_id FROM tarot.tarot_requests WHERE owner=?', (owner,))
                        if (row['operation'], _key_hash(row['request_key'])) in hashes}
        for draw in connection.execute('SELECT id,snapshot_json FROM tarot.tarot_draws WHERE owner=?', (owner,)):
            readings = connection.execute('SELECT context_json,result_json,validation_json FROM tarot.tarot_readings WHERE owner=? AND draw_id=?', (owner, draw['id'])).fetchall()
            if _contains_id(json.loads(draw['snapshot_json']), targets) or any(_contains_id(json.loads(reading[field]), targets) for reading in readings for field in ('context_json', 'result_json', 'validation_json') if reading[field]):
                delete_draws.add(draw['id'])
        for ident in delete_draws:
            for request in connection.execute('SELECT operation,request_key FROM tarot.tarot_requests WHERE owner=? AND draw_id=?', (owner, ident)).fetchall():
                report['tarot_keys_recorded'] += connection.execute('INSERT OR IGNORE INTO tarot.tarot_deleted_requests VALUES(?,?,?)', (owner, request['operation'], _key_hash(request['request_key']))).rowcount
            # Explicit deletes also handle backups made with foreign_keys disabled.
            connection.execute('DELETE FROM tarot.tarot_readings WHERE owner=? AND draw_id=?', (owner, ident))
            connection.execute('DELETE FROM tarot.tarot_requests WHERE owner=? AND draw_id=?', (owner, ident))
            connection.execute('UPDATE tarot.tarot_draws SET previous_draw_id=NULL WHERE owner=? AND previous_draw_id=?', (owner, ident))
            report['tarot_draws_deleted'] += connection.execute('DELETE FROM tarot.tarot_draws WHERE owner=? AND id=?', (owner, ident)).rowcount
        changed = any(value for key, value in report.items() if key != 'applied')
        if changed:
            connection.execute('UPDATE owners SET revision=? WHERE id=?', (revision, owner))
            connection.execute('INSERT INTO audit(owner,entity_type,entity_id,operation,revision,at) VALUES(?,?,?,?,?,?)',
                               (owner, 'privacy', 'restore', 'replayed', revision, stamp))
        connection.commit()
        report['revision'] = revision if changed else current['revision']
        return report
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--export', action='store_true'); mode.add_argument('--apply', action='store_true')
    parser.add_argument('--owner', required=True); parser.add_argument('--file', required=True)
    parser.add_argument('--state-db'); parser.add_argument('--tarot-db')
    parser.add_argument('--restore-state-db'); parser.add_argument('--restore-tarot-db')
    args = parser.parse_args()
    if args.export:
        if not args.state_db or not args.tarot_db or args.restore_state_db or args.restore_tarot_db:
            parser.error('--export requires only --state-db and --tarot-db source paths')
        result = export_privacy(args.owner, args.state_db, args.tarot_db, args.file)
    else:
        if not args.restore_state_db or not args.restore_tarot_db or args.state_db or args.tarot_db:
            parser.error('--apply requires explicit --restore-state-db and --restore-tarot-db targets')
        result = apply_privacy(args.owner, args.restore_state_db, args.restore_tarot_db, args.file)
    print(_json(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Operator diagnostics deliberately omit arbitrary input values/bodies.
        print(_json({'ok': False, 'error_type': type(exc).__name__, 'error': 'Privacy replay failed; check owner, schemas and explicit offline restore paths.'}))
        raise SystemExit(1)
