"""PostgreSQL authority, scoped effects and durable execution leases.

No SQLite fallback. Model calls never run inside these transactions.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from mingjing_core.domain.contracts import BudgetExceeded, EvidenceError, LeaseConflict, RevisionConflict, ScopeError
from mingjing_core.memory.projections import tokenized_payload
from .foundation import list_entities, migration_manifest, search as search_entities, validate_history
from .privacy_foundation import DERIVED_KINDS, invalidate_foundation
from .dispatch_hooks import admit_v4, notify_run

ENTITY_KINDS = frozenset({'message','fact','case','episode','draw','reading','report','report_schedule','chart','delivery','upload','session','consent','legacy','feedback','request','interpretive_claim','runtime_step','artifact','model_call'})
ENTITY_KINDS |= frozenset({'thread','thread_summary','note','profile_doc','knowledge_gap','followup','reminder','proposal'})
CALL_LIMITS = {'fast': 2, 'standard': 6, 'deep': 10}


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def new_id(prefix: str) -> str:
    return prefix + '_' + uuid.uuid4().hex


class PostgresRepository:
    def __init__(self, dsn: str, *, schema: str = 'mingjing_core', initialize: bool = True, max_size: int = 12, max_running: int | None = None):
        if not dsn: raise ValueError('CORE_DATABASE_URL is required; no local database fallback')
        if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]{0,62}', schema): raise ValueError('Invalid schema name')
        if max_running is not None and (isinstance(max_running,bool) or not isinstance(max_running,int) or max_running<1):raise ValueError('max_running must be a positive integer or None')
        self.dsn, self.schema = dsn, schema
        self.max_running=max_running
        self._local = threading.local()
        self.pool = ConnectionPool(dsn, min_size=0, max_size=max_size, timeout=20,
                                   kwargs={'autocommit': True, 'row_factory': dict_row}, open=True)
        if initialize: self.initialize()

    def close(self): self.pool.close()

    def table(self, name: str):
        if not re.fullmatch('[a-z_][a-z0-9_]*', name): raise ValueError('Invalid table name')
        return sql.Identifier(self.schema, name)

    @contextmanager
    def transaction(self, owner: str | None = None):
        current = getattr(self._local, 'connection', None)
        if current is not None:
            with current.transaction():
                if owner: current.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (self.schema + ':' + owner,))
                yield current
            return
        with self.pool.connection() as connection:
            with connection.transaction():
                self._local.connection = connection
                try:
                    if owner: connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (self.schema + ':' + owner,))
                    yield connection
                finally: self._local.connection = None

    connection = transaction
    db = transaction

    def initialize(self,*,adopt_unverified=False):
        with self.transaction() as connection:
            connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (self.schema+':schema',))
            connection.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(self.schema)))
            connection.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(self.schema)))
            connection.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version integer PRIMARY KEY,checksum text,applied_at timestamptz NOT NULL DEFAULT now())')
            connection.execute('ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum text')
            applied={row['version']:row['checksum'] for row in connection.execute('SELECT version,checksum FROM schema_migrations').fetchall()}
            migrations=sorted(Path(__file__).with_name('migrations').glob('[0-9][0-9][0-9][0-9]_*.sql'))
            known={int(path.name[:4]) for path in migrations}
            if not migrations or set(applied)-known:raise EvidenceError('Database schema is newer than this release or migrations are missing')
            expected=migration_manifest()
            checked={version:expected[version] if checksum is None and adopt_unverified else checksum for version,checksum in applied.items()}
            validate_history(checked,expected,complete=False)
            for path in migrations:
                version=int(path.name[:4]);source=path.read_text(encoding='utf-8').replace('\r\n','\n')
                checksum=hashlib.sha256(source.encode('utf-8')).hexdigest()
                if version in applied:
                    if applied[version]==checksum:continue
                    if applied[version] is not None or not adopt_unverified:raise EvidenceError('Migration checksum mismatch or unverified historical baseline')
                connection.execute(source)
                connection.execute('INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s) ON CONFLICT(version) DO UPDATE SET checksum=EXCLUDED.checksum', (version,checksum))

    def verify_schema(self):
        """Read-only startup check for the production DML-only application role."""
        import psycopg
        expected=migration_manifest()
        try:
            with self.connection() as c:
                actual={row['version']:row['checksum'] for row in c.execute(sql.SQL('SELECT version,checksum FROM {} ORDER BY version').format(self.table('schema_migrations'))).fetchall()}
        except psycopg.Error:
            raise EvidenceError('Core schema is unavailable; use the separate migration role') from None
        validate_history(actual,expected,complete=True)
        return {'schema':self.schema,'version':max(expected),'checksums':{str(version):checksum for version,checksum in expected.items()}}

    def ensure_owner(self, owner: str, *, settings: dict | None = None) -> dict:
        if not isinstance(owner, str) or not owner.strip() or len(owner) > 200: raise ScopeError('Explicit owner is required')
        with self.transaction(owner) as c:
            c.execute(sql.SQL('INSERT INTO {}(id,settings) VALUES(%s,%s) ON CONFLICT DO NOTHING').format(self.table('core_owners')),
                      (owner, Jsonb(settings or {'auto_save_low_sensitivity': True})))
            c.execute(sql.SQL("INSERT INTO {}(owner,id,label) VALUES(%s,'self','本人') ON CONFLICT DO NOTHING").format(self.table('core_subjects')), (owner,))
            return self.assert_scope(owner)

    def assert_scope(self, owner: str, subject: str = 'self') -> dict:
        with self.transaction(owner) as c:
            row = c.execute(sql.SQL('SELECT s.*,o.revision,o.settings FROM {} s JOIN {} o ON s.owner=o.id WHERE s.owner=%s AND s.id=%s').format(self.table('core_subjects'), self.table('core_owners')), (owner, subject)).fetchone()
            if not row or row['consent'] != 'granted': raise ScopeError('Owner/subject is absent or not authorized')
            return dict(row, owner_user_id=owner, subject_id=subject)

    def create_subject(self, owner: str, subject: str, label: str, *, consent: str = 'granted') -> dict:
        if not subject or not label or consent not in ('granted','pending','revoked'): raise ValueError('Invalid subject')
        with self.transaction(owner) as c:
            self.assert_scope(owner)
            old = c.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND id=%s').format(self.table('core_subjects')), (owner, subject)).fetchone()
            if old:
                if (old['label'], old['consent']) != (label, consent): raise EvidenceError('Subject identity already used')
                return old
            c.execute(sql.SQL('INSERT INTO {}(owner,id,label,consent) VALUES(%s,%s,%s,%s)').format(self.table('core_subjects')), (owner,subject,label,consent))
            self.bump_revision(c,owner,owner_scope=True)
            return {'id': subject, 'owner': owner, 'subject_id':subject,'label':label,'consent':consent}

    def get_revision(self, owner: str) -> int:
        with self.transaction(owner) as c:
            row = c.execute(sql.SQL('SELECT revision FROM {} WHERE id=%s').format(self.table('core_owners')), (owner,)).fetchone()
            if not row: raise ScopeError('Unknown owner')
            return row['revision']

    def bump_revision(self, c, owner: str, *, subject: str | None = None, case_id: str | None = None,
                      owner_scope: bool = False, profile: bool = False, kind: str | None = None, entity_id: str | None = None) -> int:
        row = c.execute(sql.SQL('UPDATE {} SET revision=revision+1 WHERE id=%s RETURNING revision').format(self.table('core_owners')), (owner,)).fetchone()
        if not row: raise ScopeError('Unknown owner')
        keys = []
        if owner_scope: keys.append('owner:' + owner)
        if profile and subject: keys.append('subject:' + subject)
        if case_id: keys.append('case:' + case_id)
        elif subject and kind == 'fact' and not profile: keys.append('global:' + subject)
        for key in set(keys):
            c.execute(sql.SQL('INSERT INTO {}(owner,dependency,revision) VALUES(%s,%s,1) ON CONFLICT(owner,dependency) DO UPDATE SET revision={}.revision+1').format(self.table('core_versions'),self.table('core_versions')), (owner,key))
        return row['revision']

    def _kind(self, kind):
        if kind not in ENTITY_KINDS: raise ValueError('Unregistered entity kind')

    def _decode(self, row):
        if not row: raise ScopeError('Entity does not belong to current owner')
        return dict(row['data'],id=row['id'],owner_user_id=row['owner'],owner=row['owner'],subject_id=row['subject'],subject=row['subject'],case_id=row['case_id'],revision=row['revision'],status=row['status'],created_at=row['created_at'].isoformat(),updated_at=row['updated_at'].isoformat())

    def get(self, owner: str, kind: str, entity_id: str, *, include_deleted: bool = False) -> dict:
        self._kind(kind)
        with self.transaction(owner) as c:
            row=c.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND kind=%s AND id=%s').format(self.table('core_entities')), (owner,kind,entity_id)).fetchone()
            result=self._decode(row)
            if result['status']=='deleted' and not include_deleted: raise EvidenceError('Entity was deleted')
            return result

    def list(self, owner: str, kind: str, *, subject: str | None = None, case_ids: list[str] | None = None,
             include_deleted: bool = False, limit: int = 10000, order: str = 'asc', before=None) -> list[dict]:
        return list_entities(self,owner,kind,subject=subject,case_ids=case_ids,include_deleted=include_deleted,
                             limit=limit,order=order,before=before)

    def search(self,owner,subject,query_tokens,kinds,limit=20,since=None,until=None):
        return search_entities(self,owner,subject,query_tokens,kinds,limit,since,until)

    def _operation(self, c, owner, operation_id, value, kind, entity_id):
        if not operation_id: return False
        digest=fingerprint(value)
        prior=c.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND operation_id=%s').format(self.table('core_operations')), (owner,operation_id)).fetchone()
        if prior:
            if prior['fingerprint']!=digest or prior['kind']!=kind or prior['result_id']!=entity_id: raise EvidenceError('Operation ID reused with different effect')
            return True
        c.execute(sql.SQL('INSERT INTO {}(owner,operation_id,fingerprint,kind,result_id) VALUES(%s,%s,%s,%s,%s)').format(self.table('core_operations')), (owner,operation_id,digest,kind,entity_id))
        return False

    def put(self, owner: str, kind: str, entity_id: str, data: dict, *, subject: str = 'self', case_id: str | None = None,
            expected_revision: int | None = None, operation_id: str | None = None) -> dict:
        self._kind(kind)
        if not isinstance(data,dict) or not entity_id: raise ValueError('Entity payload/ID required')
        reserved={'id','owner','owner_user_id','subject','subject_id','case_id','revision','created_at','updated_at'}
        payload={k:v for k,v in data.items() if k not in reserved and k!='status'};status=data.get('status','active')
        payload=tokenized_payload(self,owner,kind,entity_id,payload)
        with self.transaction(owner) as c:
            self.assert_scope(owner,subject)
            if case_id:
                case=self.get(owner,'case',case_id)
                if case['subject_id']!=subject: raise ScopeError('Case is outside current subject')
            if self.is_revoked(owner,kind,entity_id): raise EvidenceError('Revoked entity cannot be restored by retry')
            if self._operation(c,owner,operation_id,[kind,entity_id,subject,case_id,data],kind,entity_id): return self.get(owner,kind,entity_id,include_deleted=True)
            old=c.execute(sql.SQL('SELECT revision FROM {} WHERE owner=%s AND kind=%s AND id=%s FOR UPDATE').format(self.table('core_entities')), (owner,kind,entity_id)).fetchone()
            current=old['revision'] if old else 0
            if (old and expected_revision is None) or (expected_revision is not None and expected_revision!=current): raise RevisionConflict('Entity revision changed; refresh before writing')
            c.execute(sql.SQL('INSERT INTO {}(owner,kind,id,subject,case_id,revision,status,data) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(owner,kind,id) DO UPDATE SET revision=EXCLUDED.revision,status=EXCLUDED.status,data=EXCLUDED.data,updated_at=now()').format(self.table('core_entities')), (owner,kind,entity_id,subject,case_id,current+1,status,Jsonb(payload)))
            self.bump_revision(c,owner,subject=subject,case_id=entity_id if kind=='case' else case_id,kind=kind,profile=kind=='fact' and bool(payload.get('field')))
            return self.get(owner,kind,entity_id,include_deleted=True)

    def update(self, owner: str, kind: str, entity_id: str, changes: dict, *, expected_revision: int, operation_id: str | None = None) -> dict:
        with self.transaction(owner):
            old=self.get(owner,kind,entity_id,include_deleted=True)
            return self.put(owner,kind,entity_id,dict(old,**changes),subject=old['subject_id'],case_id=old['case_id'],expected_revision=expected_revision,operation_id=operation_id)

    def delete(self, owner: str, kind: str, entity_id: str, *, expected_revision: int, operation_id: str | None = None) -> dict:
        with self.transaction(owner) as c:
            old=self.get(owner,kind,entity_id,include_deleted=True)
            if old['status']=='deleted': return old
            result=self.put(owner,kind,entity_id,{'status':'deleted'},subject=old['subject_id'],case_id=old['case_id'],expected_revision=expected_revision,operation_id=operation_id)
            self.revoke(c,owner,kind,entity_id,'deleted')
            return result

    def _version(self,c,owner,key):
        prefix,_,entity_id=key.partition(':')
        if prefix=='entity':
            kind,separator,ident=entity_id.partition(':')
            if not separator or kind not in ENTITY_KINDS or not ident:raise EvidenceError('Invalid exact entity dependency')
            row=c.execute(sql.SQL('SELECT revision FROM {} WHERE owner=%s AND kind=%s AND id=%s').format(self.table('core_entities')), (owner,kind,ident)).fetchone()
        elif prefix in ('fact','message','report_schedule','thread',*DERIVED_KINDS):
            row=c.execute(sql.SQL('SELECT revision FROM {} WHERE owner=%s AND kind=%s AND id=%s').format(self.table('core_entities')), (owner,prefix,entity_id)).fetchone()
        else:
            row=c.execute(sql.SQL('SELECT revision FROM {} WHERE owner=%s AND dependency=%s').format(self.table('core_versions')), (owner,key)).fetchone()
        return row['revision'] if row else 0

    def versions(self, owner: str, subject: str = 'self', case_ids: list[str] | None = None) -> dict[str,int]:
        with self.transaction(owner) as c:
            self.assert_scope(owner,subject)
            keys=['owner:'+owner,'subject:'+subject,'global:'+subject]+['case:'+cid for cid in case_ids or []]
            for cid in case_ids or []:
                if self.get(owner,'case',cid)['subject_id']!=subject: raise ScopeError('Case belongs to another subject')
            return {key:self._version(c,owner,key) for key in keys}

    def verify_versions(self, owner: str, versions: dict[str,int]) -> bool:
        with self.transaction(owner) as c:
            self.assert_scope(owner)
            for key,value in versions.items():
                if key.startswith('owner:') and key!='owner:'+owner: raise ScopeError('Dependency owner mismatch')
                if self._version(c,owner,key)!=value: return False
            return True

    def bind_channel(self, owner: str, channel: str, external_id: str, subject: str = 'self', *, binding_kind: str = 'user'):
        if not channel or not external_id or binding_kind not in ('user','chat','task'): raise ValueError('Explicit channel identity required')
        with self.transaction(owner) as c:
            self.assert_scope(owner,subject)
            old=c.execute(sql.SQL('SELECT * FROM {} WHERE channel=%s AND external_id=%s').format(self.table('core_channels')), (channel,external_id)).fetchone()
            if old:
                if (old['owner'],old['subject'],old['binding_kind'])!=(owner,subject,binding_kind): raise ScopeError('Channel identity already bound')
                return old
            c.execute(sql.SQL('INSERT INTO {}(channel,external_id,owner,subject,binding_kind) VALUES(%s,%s,%s,%s,%s)').format(self.table('core_channels')), (channel,external_id,owner,subject,binding_kind))
            self.bump_revision(c,owner,owner_scope=True)
            return self.resolve_channel(channel,external_id)

    def resolve_channel(self, channel: str, external_id: str) -> dict:
        with self.transaction() as c:
            row=c.execute(sql.SQL('SELECT * FROM {} WHERE channel=%s AND external_id=%s').format(self.table('core_channels')), (channel,external_id)).fetchone()
            if not row: raise ScopeError('Channel identity has not been bound')
            self.assert_scope(row['owner'],row['subject'])
            return dict(row,owner_user_id=row['owner'],subject_id=row['subject'])

    def is_revoked(self,owner,kind,entity_id):
        with self.transaction(owner) as c:
            return c.execute(sql.SQL('SELECT 1 FROM {} WHERE owner=%s AND kind=%s AND entity_id=%s').format(self.table('core_revocations')), (owner,kind,entity_id)).fetchone() is not None

    def revocations(self,owner):
        with self.transaction(owner) as c:
            self.assert_scope(owner)
            return c.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s ORDER BY created_at').format(self.table('core_revocations')), (owner,)).fetchall()

    def revoke(self,c,owner,kind,entity_id,operation,metadata=None):
        # Metadata is identifiers/ranges only: never old text, quote or model output.
        allowed={'message_id','start','end','fact_ids','source_ids','source','legacy_id'}
        clean={key:value for key,value in (metadata or {}).items() if key in allowed}
        prior=c.execute(sql.SQL('SELECT operation,metadata,revision FROM {} WHERE owner=%s AND kind=%s AND entity_id=%s').format(self.table('core_revocations')),(owner,kind,entity_id)).fetchone()
        if prior and prior['operation']==operation and prior['metadata']==clean:return prior['revision']
        revision=self.bump_revision(c,owner,owner_scope=True)
        c.execute(sql.SQL('INSERT INTO {}(owner,kind,entity_id,operation,metadata,revision) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(owner,kind,entity_id) DO UPDATE SET operation=EXCLUDED.operation,metadata=EXCLUDED.metadata,revision=EXCLUDED.revision').format(self.table('core_revocations')), (owner,kind,entity_id,operation,Jsonb(clean),revision))
        return revision

    def invalidate_derived(self, owner: str, fact_ids: list[str], source_ids: list[str], *, recomputable=False,span_source_ids=(),seed_entities=()):
        with self.transaction(owner) as c:
            original_sources=list(source_ids)
            retry=bool(recomputable and not original_sources)
            source_ids,closure_runs,partial=invalidate_foundation(self,owner,fact_ids,source_ids,
                span_source_ids=span_source_ids,recomputable=recomputable,seed_entities=seed_entities)
            contaminated=set('fact:'+ident for ident in fact_ids)|set('message:'+ident for ident in source_ids)
            runs=c.execute(sql.SQL('SELECT id,state_version,request,status FROM {} WHERE owner=%s').format(self.table('core_runs')), (owner,)).fetchall()
            ids=[]
            for run in runs:
                if recomputable and run['status'] in ('revoked','cancelled'):continue
                if run['id'] in closure_runs or contaminated.intersection(run['state_version']) or run['request'].get('message_id') in source_ids or run['request'].get('source_message_id') in source_ids:
                    ids.append(run['id'])
            if ids:
                c.execute(sql.SQL("UPDATE {} SET request=CASE WHEN %s THEN request ELSE '{{}}'::jsonb END,result=NULL,checkpoint='{{}}',status=%s,error=%s,lease_token=NULL,lease_until=NULL,updated_at=now() WHERE owner=%s AND id=ANY(%s)").format(self.table('core_runs')), (retry,'stale' if retry else 'revoked','STALE_INPUT' if retry else 'SOURCE_REVOKED',owner,ids))
                c.execute(sql.SQL("UPDATE {} SET data='{{}}',status='deleted',revision=revision+1,updated_at=now() WHERE owner=%s AND kind IN ('runtime_step','interpretive_claim','artifact','model_call','report') AND data->>'run_id'=ANY(%s) AND NOT (%s AND kind='runtime_step' AND data->>'stage' IN ('intake','memory'))").format(self.table('core_entities')), (owner,ids,retry))
                c.execute(sql.SQL("UPDATE {} SET payload='{{}}',status=CASE WHEN status IN ('sending','uncertain') THEN 'uncertain' WHEN status='sent' THEN 'sent' WHEN %s THEN 'stale' ELSE 'cancelled' END,error=%s,updated_at=now() WHERE owner=%s AND run_id=ANY(%s)").format(self.table('delivery_outbox')), (retry,'STALE_INPUT' if retry else 'SOURCE_REVOKED',owner,ids))
            for episode in self.list(owner,'episode',include_deleted=True):
                if set(fact_ids)&set(episode.get('fact_ids',[])) or set(source_ids)&set(episode.get('source_ids',[])):
                    self.delete(owner,'episode',episode['id'],expected_revision=episode['revision'])
            for kind in ('feedback','request'):
                for derived in self.list(owner,kind,include_deleted=True):
                    if derived['status']=='deleted':continue
                    linked=set(derived.get('source_ids',[]))|{ref.get('message_id') for ref in derived.get('source_refs',[])}|{derived.get('message_id'),derived.get('source_id')}
                    cached_facts={receipt.get('id') for receipt in derived.get('result',{}).get('receipts',[]) if isinstance(receipt,dict)} if isinstance(derived.get('result'),dict) else set()
                    if linked.intersection(source_ids) or cached_facts.intersection(fact_ids):
                        self.delete(owner,kind,derived['id'],expected_revision=derived['revision'])
            if original_sources:
                # Legacy payloads have no trustworthy fine-grained lineage. Do
                # not let an archive endpoint resurrect withdrawn originals.
                for legacy in self.list(owner,'legacy',include_deleted=True):
                    if legacy['status']!='deleted':self.delete(owner,'legacy',legacy['id'],expected_revision=legacy['revision'])
                hard_sources=set(source_ids)-partial|set(original_sources)
                for case in self.list(owner,'case',include_deleted=True):
                    if case['status']!='deleted' and any(ref.get('message_id') in hard_sources for ref in case.get('source_refs',[])):
                        self.delete(owner,'case',case['id'],expected_revision=case['revision'])
                for upload in self.list(owner,'upload',include_deleted=True):
                    linked=set(upload.get('source_ids',[]))|{ref.get('message_id') for ref in upload.get('source_refs',[])}|{upload.get('message_id')}
                    if linked.intersection(hard_sources) and upload['status']!='deleted':
                        self.enqueue_media_deletion(owner,upload)
                        self.delete(owner,'upload',upload['id'],expected_revision=upload['revision'])

    def _media_path(self,owner,path,media_root=None):
        if not isinstance(path,str) or not path:return None
        root=Path(media_root or os.getenv('ZHIMING_MEDIA_PATH', str(Path(__file__).resolve().parents[2]/'private/media'))).resolve()
        folder=(root/hashlib.sha256(owner.encode()).hexdigest()[:24]).resolve()
        if not folder.is_relative_to(root) or folder==root:return None
        if Path(path).is_symlink():return None
        candidate=Path(path).resolve()
        if not candidate.is_relative_to(folder) or candidate==folder:return None
        return candidate

    def enqueue_media_deletion(self,owner,upload):
        path=self._media_path(owner,upload.get('path'))
        # Old protected archive files are outside the new Core media root.
        if path is None:return False
        with self.transaction(owner) as c:
            c.execute(sql.SQL('INSERT INTO {}(owner,upload_id,path) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING').format(self.table('core_media_deletions')), (owner,upload['id'],str(path)))
        return True

    def cleanup_media_deletions(self,owner=None,*,media_root=None,limit=50):
        """Delete committed Core media intents; never delete protected archives."""
        counts={'deleted':0,'failed':0}
        with self.transaction(owner) as c:
            query=sql.SQL("SELECT * FROM {} WHERE status='pending'").format(self.table('core_media_deletions'));args=[]
            if owner:query+=sql.SQL(' AND owner=%s');args.append(owner)
            query+=sql.SQL(' ORDER BY created_at LIMIT %s FOR UPDATE SKIP LOCKED');args.append(max(1,min(int(limit),500)))
            for row in c.execute(query,args).fetchall():
                path=self._media_path(row['owner'],row['path'],media_root)
                try:
                    if path is None:raise EvidenceError('Media path outside owner root')
                    path.unlink(missing_ok=True)
                    c.execute(sql.SQL("UPDATE {} SET path='',status='deleted',error='' WHERE owner=%s AND upload_id=%s").format(self.table('core_media_deletions')), (row['owner'],row['upload_id']))
                    counts['deleted']+=1
                except (OSError,EvidenceError):
                    c.execute(sql.SQL("UPDATE {} SET status='failed',error='MEDIA_PATH_OR_IO_ERROR' WHERE owner=%s AND upload_id=%s").format(self.table('core_media_deletions')), (row['owner'],row['upload_id']))
                    counts['failed']+=1
        return counts

    def map_legacy(self,owner,source,legacy_id,kind,result_id,status='imported'):
        with self.transaction(owner) as c:
            c.execute(sql.SQL('INSERT INTO {}(owner,source,legacy_id,kind,result_id,status) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING').format(self.table('core_legacy_map')), (owner,source,str(legacy_id),kind,result_id,status))

    def legacy_mapping(self,owner,source,legacy_id,kind):
        with self.transaction(owner) as c:
            return c.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND source=%s AND legacy_id=%s AND kind=%s').format(self.table('core_legacy_map')), (owner,source,str(legacy_id),kind)).fetchone()

    def mutation_request(self,owner,operation,request_key,payload,effect):
        """Exactly-once local mutation with a body-free durable HTTP receipt.

        effect() must contain only database effects in this repository. Re-read
        any private entities for presentation after this method returns; never
        cache fact quotes, original messages, profiles or private decks here.
        """
        if not isinstance(operation,str) or not operation or len(operation)>100 or not isinstance(request_key,str) or not request_key or len(request_key)>200:
            raise ValueError('Stable mutation operation and request key required')
        allowed={'status','id','ids','revision','write_status','operation','kind','affected_ids','deleted_ids','message_id','fact_id','draw_id','reading_id','settings_revision','context_revision','deleted','enabled','code'}
        digest=fingerprint(payload)
        with self.transaction(owner) as c:
            self.assert_scope(owner)
            old=c.execute(sql.SQL('SELECT fingerprint,receipt FROM {} WHERE owner=%s AND operation=%s AND request_key=%s').format(self.table('core_mutation_requests')), (owner,operation,request_key)).fetchone()
            if old:
                if old['fingerprint']!=digest:raise EvidenceError('Mutation request key reused with different intent')
                return old['receipt']
            receipt=effect()
            if not isinstance(receipt,dict) or set(receipt)-allowed:raise EvidenceError('Mutation receipt must contain only identifiers and status')
            for key,value in receipt.items():
                if isinstance(value,(dict,tuple,set)) or isinstance(value,list) and any(not isinstance(item,(str,int,bool,type(None))) for item in value):
                    raise EvidenceError('Mutation receipt cannot retain private structured data')
            try:json.dumps(receipt,allow_nan=False)
            except (TypeError,ValueError) as exc:raise EvidenceError('Mutation receipt must be JSON identifiers/status') from exc
            c.execute(sql.SQL('INSERT INTO {}(owner,operation,request_key,fingerprint,receipt) VALUES(%s,%s,%s,%s,%s)').format(self.table('core_mutation_requests')), (owner,operation,request_key,digest,Jsonb(receipt)))
            return receipt

    def _run(self,row):
        if not row: raise ScopeError('Run does not belong to current owner')
        return dict(row,run_id=row['id'],owner_user_id=row['owner'],subject_id=row['subject'],dependencies=row['state_version'],remaining=row['call_limit']-row['calls'])

    def queue_run(self,owner,operation_id,request,depth='standard',subject='self',case_ids=None):
        if not operation_id or depth not in CALL_LIMITS: raise ValueError('Stable operation ID and valid depth required')
        with self.transaction(owner) as c:
            self.assert_scope(owner,subject)
            self.versions(owner,subject,case_ids or [])
            digest=fingerprint([subject,depth,request])
            row=c.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND operation_id=%s').format(self.table('core_runs')), (owner,operation_id)).fetchone()
            if row:
                if row['fingerprint']!=digest: raise EvidenceError('Operation ID reused with different consultation')
                return self._run(row)
            run_id=new_id('run')
            row=c.execute(sql.SQL('INSERT INTO {}(id,owner,subject,operation_id,fingerprint,request,call_limit) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *').format(self.table('core_runs')), (run_id,owner,subject,operation_id,digest,Jsonb(request),CALL_LIMITS[depth])).fetchone()
            notify_run(c,self.schema,run_id)
            return self._run(row)

    def fetch_run(self,owner,run_id):
        with self.transaction(owner) as c:
            return self._run(c.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND id=%s').format(self.table('core_runs')), (owner,run_id)).fetchone())

    get_run = fetch_run

    def claim_run(self,owner,run_id,lease_seconds=120):
        with self.transaction(owner) as c:
            self.assert_scope(owner)
            row=c.execute(sql.SQL('SELECT *,lease_until>now() AS live FROM {} WHERE owner=%s AND id=%s FOR UPDATE').format(self.table('core_runs')), (owner,run_id)).fetchone()
            if not row: raise ScopeError('Unknown run')
            if row['status']=='succeeded': return self._run(row)
            if row['status'] not in ('queued','running'): raise LeaseConflict('Run is terminal')
            if row['status']=='running' and row['live']: raise LeaseConflict('Run already leased')
            admit_v4(self,c,row)
            if self.max_running is not None:
                # One shared capacity fence covers Web, Feishu and report
                # workers, including distinct owners and connection pools.
                c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(self.schema+':run-capacity',))
                running=c.execute(sql.SQL("SELECT count(*) AS count FROM {} WHERE status='running' AND lease_until>now()").format(self.table('core_runs'))).fetchone()['count']
                if running>=self.max_running:raise LeaseConflict('Core execution capacity is occupied; queued request is retained')
            token=new_id('lease')
            row=c.execute(sql.SQL("UPDATE {} SET status='running',attempts=attempts+1,lease_token=%s,lease_until=now()+%s*interval '1 second',updated_at=now() WHERE owner=%s AND id=%s RETURNING *").format(self.table('core_runs')), (token,max(1,min(int(lease_seconds),3600)),owner,run_id)).fetchone()
            return self._run(row)

    def begin_run(self,owner,operation_id,request,depth='standard',subject='self',case_ids=None,lease_seconds=120):
        row=self.queue_run(owner,operation_id,request,depth,subject,case_ids)
        return row if row['status']=='succeeded' else self.claim_run(owner,row['id'],lease_seconds)

    def _leased(self,c,owner,run_id,lease_token):
        row=c.execute(sql.SQL('SELECT *,lease_until>now() AS live FROM {} WHERE owner=%s AND id=%s FOR UPDATE').format(self.table('core_runs')), (owner,run_id)).fetchone()
        if not row: raise ScopeError('Unknown run')
        if row['status']!='running' or not row['live'] or not lease_token or row['lease_token']!=lease_token: raise LeaseConflict('Execution lease is absent, expired or replaced')
        return row

    def renew_run(self,owner,run_id,lease_token,lease_seconds=120):
        with self.transaction(owner) as c:
            self._leased(c,owner,run_id,lease_token)
            c.execute(sql.SQL("UPDATE {} SET lease_until=now()+%s*interval '1 second',updated_at=now() WHERE owner=%s AND id=%s").format(self.table('core_runs')), (max(1,min(int(lease_seconds),3600)),owner,run_id))
            return self.fetch_run(owner,run_id)

    def charge_run(self,owner,run_id,operation_id=None,lease_token=None,*,repair=False,repair_identity=None,purpose=None):
        if repair_identity is not None and (not repair or not re.fullmatch(r'[0-9a-f]{64}',repair_identity) or not isinstance(purpose,str) or not re.fullmatch(r'[a-z][a-z0-9_:]{0,79}',purpose)):
            raise ValueError('A repair charge requires a body-free identity and purpose')
        operation_id=operation_id or new_id('model')
        with self.transaction(owner) as c:
            row=self._leased(c,owner,run_id,lease_token)
            old=c.execute(sql.SQL('SELECT repair FROM {} WHERE owner=%s AND run_id=%s AND operation_id=%s').format(self.table('core_model_charges')), (owner,run_id,operation_id)).fetchone()
            if old:
                if old['repair']!=repair: raise EvidenceError('Model operation reused with different purpose')
                if repair_identity is not None:
                    previous=self.get(owner,'model_call',run_id+':call:'+operation_id,include_deleted=True)
                    if previous.get('repair_identity')!=repair_identity or previous.get('purpose')!=purpose or previous.get('repair_epoch')!=row['retry_epoch']:
                        raise EvidenceError('Model operation reused with a different repair identity')
                return self._run(row)
            if row['calls']>=row['call_limit']:raise BudgetExceeded('Persistent global model/repair budget exhausted')
            if repair and row['repair_used']:
                # A repair round is unique. Only a known transient failure of
                # that exact round can incur another physical provider call.
                # An unmarked legacy charge or unfinished/crashed call is not
                # evidence that opening the repair gate is safe.
                attempts=c.execute(sql.SQL("SELECT charge.operation_id,log.status,log.data FROM {} charge LEFT JOIN {} log ON log.owner=charge.owner AND log.kind='model_call' AND log.id=charge.run_id||':call:'||charge.operation_id WHERE charge.owner=%s AND charge.run_id=%s AND charge.repair=true").format(self.table('core_model_charges'),self.table('core_entities')),(owner,run_id)).fetchall()
                if not repair_identity or not attempts:raise BudgetExceeded('Persistent global repair round already used')
                for attempt in attempts:
                    data=attempt['data'] or {}
                    if data.get('repair_identity')!=repair_identity or data.get('repair_epoch')!=row['retry_epoch'] or data.get('purpose')!=purpose or type(data.get('call_index')) is not int:
                        raise BudgetExceeded('A different or unverified repair round cannot retry')
                last=max(attempts,key=lambda attempt:attempt['data']['call_index'])
                data=last['data'];reason=data.get('reason');http=data.get('provider_http_status')
                transient=reason in ('network','json','tool_count','tool_input') or (reason=='http' and type(http) is int and (http==429 or 500<=http<=599))
                if last['status']!='failed' or data.get('repair_outcome')!='transient_failure' or data.get('error_class')!='ModelUnavailable' or not transient or data['call_index']!=row['calls']:
                    raise BudgetExceeded('Only the last known transient attempt of the same repair can retry')
            c.execute(sql.SQL('INSERT INTO {}(owner,run_id,operation_id,repair) VALUES(%s,%s,%s,%s)').format(self.table('core_model_charges')), (owner,run_id,operation_id,repair))
            c.execute(sql.SQL('UPDATE {} SET calls=calls+1,repair_used=repair_used OR %s,updated_at=now() WHERE owner=%s AND id=%s').format(self.table('core_runs')), (repair,owner,run_id))
            if repair_identity is not None:
                self.put(owner,'model_call',run_id+':call:'+operation_id,
                         {'run_id':run_id,'purpose':purpose,'status':'started','charge_operation_id':operation_id,
                          'repair_identity':repair_identity,'repair_epoch':row['retry_epoch'],
                          'call_index':row['calls']+1,'repair_outcome':'unknown','usage':{},'usage_known':False},subject=row['subject'])
            return self.fetch_run(owner,run_id)

    def set_run_dependencies(self,owner,run_id,versions,lease_token):
        with self.transaction(owner) as c:
            self._leased(c,owner,run_id,lease_token)
            if not self.verify_versions(owner,versions): raise RevisionConflict('Dependencies changed before execution')
            c.execute(sql.SQL('UPDATE {} SET state_version=%s,updated_at=now() WHERE owner=%s AND id=%s').format(self.table('core_runs')), (Jsonb(versions),owner,run_id))
            return self.fetch_run(owner,run_id)

    def checkpoint_run(self,owner,run_id,checkpoint,lease_token):
        allowed={'phase','node','ids','budget','attempt','state_version','schema_version','run_id','owner_user_id'}
        if set(checkpoint)-allowed or len(json.dumps(checkpoint,default=str))>8192: raise ValueError('Checkpoint stores phase/IDs/budget only')
        def validate(value):
            if isinstance(value,dict):
                if any(k in ('content','text','quote','messages','snapshot','facts','sources') for k in value): raise ValueError('Private bodies are forbidden in checkpoint')
                for v in value.values(): validate(v)
            elif isinstance(value,list):
                for v in value: validate(v)
        validate(checkpoint)
        with self.transaction(owner) as c:
            self._leased(c,owner,run_id,lease_token)
            c.execute(sql.SQL('UPDATE {} SET checkpoint=%s,updated_at=now() WHERE owner=%s AND id=%s').format(self.table('core_runs')), (Jsonb(checkpoint),owner,run_id))
            return self.fetch_run(owner,run_id)

    checkpoint = checkpoint_run

    def commit_run(self,owner,run_id,versions,result,lease_token):
        with self.transaction(owner) as c:
            row=self._leased(c,owner,run_id,lease_token)
            if versions!=row['state_version'] or not self.verify_versions(owner,versions): raise RevisionConflict('Dependencies changed; stale answer cannot commit')
            if result.get('schema_version')!='core3.0' or result.get('validation',{}).get('status')!='validated': raise EvidenceError('Only validated core3.0 results may commit')
            c.execute(sql.SQL("UPDATE {} SET result=%s,status='succeeded',checkpoint='{{}}',lease_token=NULL,lease_until=NULL,updated_at=now() WHERE owner=%s AND id=%s").format(self.table('core_runs')), (Jsonb(result),owner,run_id))
            return self.fetch_run(owner,run_id)

    def fail_run(self,owner,run_id,error,lease_token,*,status='failed'):
        if status not in ('failed','stale','cancelled'): raise ValueError('Invalid terminal status')
        with self.transaction(owner) as c:
            current=self._leased(c,owner,run_id,lease_token)
            c.execute(sql.SQL('UPDATE {} SET status=%s,error=%s,lease_token=NULL,lease_until=NULL,updated_at=now() WHERE owner=%s AND id=%s').format(self.table('core_runs')), (status,str(error)[:300],owner,run_id))
            if current.get('runtime')=='v4':
                from .event_retention_metadata import record_terminal
                record_terminal(self,c,owner,run_id)
            return self.fetch_run(owner,run_id)

    def recover_runs(self,owner=None):
        with self.transaction(owner) as c:
            query=sql.SQL("UPDATE {} SET status='queued',lease_token=NULL,lease_until=NULL,updated_at=now() WHERE status='running' AND lease_until<=now()").format(self.table('core_runs'));args=[]
            if owner: query+=sql.SQL(' AND owner=%s');args=[owner]
            return c.execute(query,args).rowcount

    def prepare_retry(self,owner,run_id):
        """Requeue one business run without restoring withdrawn source or budget.

        A fresh-input failure retains its cache/checkpoint. Stale dependencies
        get a new graph epoch, preserving completed intake and memory receipts
        while retiring every private output from the old epoch.
        """
        with self.transaction(owner) as c:
            row=c.execute(sql.SQL('SELECT * FROM {} WHERE owner=%s AND id=%s FOR UPDATE').format(self.table('core_runs')), (owner,run_id)).fetchone()
            if not row:raise ScopeError('Run does not belong to current owner')
            self.assert_scope(owner,row['subject'])
            if row['status'] not in ('failed','stale'):raise LeaseConflict('Only failed or stale runs can retry')
            if row.get('runtime')=='v4':
                from .event_retention_metadata import is_closed
                if is_closed(self._run(row)):raise EvidenceError('事件历史已过期，请明确发起新请求')
            if row['calls']>=row['call_limit']:raise BudgetExceeded('Persistent global model budget exhausted')
            epoch=int(row['retry_epoch'])
            steps=self.list(owner,'runtime_step',include_deleted=True)
            steps=[step for step in steps if step.get('run_id')==run_id]
            def stage_output(stage):
                identifiers=[run_id+':e'+str(epoch)+':'+stage]
                if epoch==0:identifiers.append(run_id+':'+stage)
                return next((step for step in steps if step['id'] in identifiers and step['status']!='deleted'),None)
            intake=stage_output('intake');memory=stage_output('memory')
            source_id=row['request'].get('source_message_id') or row['request'].get('message_id') or (intake or {}).get('output',{}).get('source_id')
            if source_id:
                source=self.get(owner,'message',source_id)
                if source['subject_id']!=row['subject'] or source.get('role')!='user' or source.get('content')!=row['request'].get('message'):
                    raise EvidenceError('Original source changed or is no longer usable')
                if any(rev['kind']=='source_span' and rev['metadata'].get('message_id')==source_id for rev in self.revocations(owner)):
                    raise EvidenceError('Withdrawn original source cannot be reprocessed')
            stale=row['status']=='stale' or bool(row['state_version']) and not self.verify_versions(owner,row['state_version'])
            if stale:
                epoch+=1
                preserved_stages=((intake,'intake'),(memory,'memory')) if intake and memory else ()
                for preserved,stage in preserved_stages:
                    if preserved:
                        self.put(owner,'runtime_step',run_id+':e'+str(epoch)+':'+stage,
                                 {'run_id':run_id,'stage':stage,'output':preserved['output']},subject=row['subject'],
                                 operation_id='step:'+run_id+':e'+str(epoch)+':'+stage)
                for step in steps:
                    if step['status']!='deleted':self.delete(owner,'runtime_step',step['id'],expected_revision=step['revision'])
                for kind in ('interpretive_claim','artifact'):
                    for item in self.list(owner,kind,include_deleted=True):
                        if item.get('run_id')==run_id and item['status']!='deleted':self.delete(owner,kind,item['id'],expected_revision=item['revision'])
            c.execute(sql.SQL("UPDATE {} SET status='queued',retry_epoch=%s,error='',result=NULL,checkpoint=CASE WHEN %s THEN '{{}}'::jsonb ELSE checkpoint END,state_version=CASE WHEN %s THEN '{{}}'::jsonb ELSE state_version END,lease_token=NULL,lease_until=NULL,updated_at=now() WHERE owner=%s AND id=%s").format(self.table('core_runs')), (epoch,stale,stale,owner,run_id))
            if row.get('runtime')=='v4':
                from .event_retention_metadata import reopen_retry
                reopen_retry(self,c,owner,run_id)
            return {'run':self.fetch_run(owner,run_id),'purge_checkpoint':bool(stale)}

    def queued_runs(self,owner=None,limit=100):
        with self.transaction(owner) as c:
            query=sql.SQL("SELECT * FROM {} WHERE status='queued'").format(self.table('core_runs'));args=[]
            if owner:query+=sql.SQL(' AND owner=%s');args.append(owner)
            query+=sql.SQL(' ORDER BY created_at LIMIT %s');args.append(limit)
            return [self._run(row) for row in c.execute(query,args).fetchall()]

    def export_privacy(self,owner):
        return {'schema_version':'core3.0','owner_user_id':owner,'revocations':[
            {'kind':r['kind'],'entity_id':r['entity_id'],'operation':r['operation'],'metadata':r['metadata']} for r in self.revocations(owner)]}

    def apply_privacy(self,owner,ledger):
        """Replay body-free withdrawals against an explicitly selected restore database."""
        if ledger.get('schema_version')!='core3.0' or ledger.get('owner_user_id')!=owner:raise ScopeError('Privacy ledger owner/schema mismatch')
        rows=ledger.get('revocations',[])
        if not isinstance(rows,list):raise ValueError('Invalid privacy ledger')
        fact_ids=[];source_ids=[];other_targets={};span_sources=[]
        with self.transaction(owner) as c:
            self.assert_scope(owner)
            all_facts=self.list(owner,'fact',include_deleted=True)
            for row in rows:
                kind=row.get('kind');ident=row.get('entity_id');metadata=row.get('metadata',{})
                if not isinstance(ident,str) or kind not in ('fact','message','source_span','episode','legacy_memory','legacy','upload','case','request','feedback',*DERIVED_KINDS):raise ValueError('Invalid revocation target')
                if kind=='fact':fact_ids.append(ident)
                if kind=='message':source_ids.append(ident)
                if kind in ('episode','legacy','upload','case','request','feedback',*DERIVED_KINDS):other_targets.setdefault(kind,[]).append(ident)
                if kind=='source_span':
                    if metadata.get('message_id'):span_sources.append(metadata['message_id'])
                    for fact in all_facts:
                        if any(ref.get('message_id')==metadata.get('message_id') and max(ref.get('start',0),metadata.get('start',0))<min(ref.get('end',0),metadata.get('end',0)) for ref in fact.get('source_refs',[])):fact_ids.append(fact['id'])
                self.revoke(c,owner,kind,ident,row.get('operation','deleted'),metadata)
            for fact in all_facts:
                if any(ref.get('message_id') in source_ids for ref in fact.get('source_refs',[])):fact_ids.append(fact['id'])
            for kind,ids in (('fact',list(set(fact_ids))),('message',list(set(source_ids)))):
                if ids:c.execute(sql.SQL("UPDATE {} SET data='{{}}',status='deleted',revision=revision+1,updated_at=now() WHERE owner=%s AND kind=%s AND id=ANY(%s) AND status!='deleted'").format(self.table('core_entities')), (owner,kind,ids))
            for kind,ids in other_targets.items():
                if kind=='upload':
                    for ident in ids:
                        try:self.enqueue_media_deletion(owner,self.get(owner,'upload',ident,include_deleted=True))
                        except ScopeError:pass
                c.execute(sql.SQL("UPDATE {} SET data='{{}}',status='deleted',revision=revision+1,updated_at=now() WHERE owner=%s AND kind=%s AND id=ANY(%s) AND status!='deleted'").format(self.table('core_entities')), (owner,kind,ids))
            self.invalidate_derived(owner,list(set(fact_ids)),list(set(source_ids)),span_source_ids=span_sources,seed_entities=[(kind,ident) for kind,ids in other_targets.items() for ident in ids])
        return {'facts':len(set(fact_ids)),'sources':len(set(source_ids)),'revision':self.get_revision(owner)}
