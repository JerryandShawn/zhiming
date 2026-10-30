import {
  DraftApiError,
  draftRequest,
  exactKeys,
  isId,
  isInstant,
  isRevision,
  isText,
  record,
  sourceRef,
  writeResult,
  type SourceRef,
  type WriteIdentity,
} from '../modules/draftApi';
import type { RequestOwner } from '../threads/request';

// mod api_organize_draft 0.1.0 @ daccd26c. Draft only; record_only never bypasses the quality gate.
export type OrganizeQuery = { limit?: number; cursor?: string; subject_id?: string; batch_id?: string };
export type PlanEdit =
  | { kind: 'rename'; target_id: string; title: string }
  | { kind: 'merge'; target_id: string; target_ids: readonly string[] }
  | { kind: 'split'; target_id: string; message_ids: readonly string[]; title: string }
  | { kind: 'move'; target_id: string; space_id: string }
  | { kind: 'ignore'; target_id: string };
export type SuggestedTopic = Readonly<{
  id: string;
  space_id: string;
  title: string;
  message_ids: readonly string[];
  start_at: string;
  end_at: string;
  sample: string;
  confidence: number;
  source_refs: readonly SourceRef[];
}>;
export type OrganizeProposal = Readonly<{
  batch_id: string;
  subject_id: string;
  revision: number;
  plan_fingerprint: string;
  status: 'proposed' | 'reviewed' | 'applied' | 'reverted' | 'invalidated';
  quality_gate: 'record_only';
  source_refs: readonly SourceRef[];
  topics: readonly SuggestedTopic[];
  needs_review: readonly string[];
  ignored_count: number;
  encoder_mode: string;
  degradation: string | null;
}>;
export type ReviewGrant = Readonly<{
  receipt_id: string;
  batch_id: string;
  revision: number;
  plan_fingerprint: string;
  reviewed_at: string;
  expires_at: string;
}>;
export type RevertConflict = Readonly<{
  entity_id: string;
  field: 'space_id' | 'topic_id' | 'title' | 'status' | 'space_secondary' | 'route_source' | 'route_confidence';
  reason: 'later_edit' | 'source_revoked' | 'scope_changed';
}>;

const bad = () => new DraftApiError('BAD_RESPONSE');
const fingerprint = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const segment = (value: string) => {
  if (!isId(value)) throw new DraftApiError('VALIDATION_ERROR');
  return encodeURIComponent(value);
};
const count = (value: unknown, maximum = 9007199254740991) =>
  Number.isSafeInteger(value) && (value as number) >= 0 && (value as number) <= maximum;
function ids(value: unknown, min = 0, max = 100): value is readonly string[] {
  return (
    Array.isArray(value) &&
    value.length >= min &&
    value.length <= max &&
    value.every(isId) &&
    new Set(value).size === value.length
  );
}
function sourceRefs(value: unknown): readonly SourceRef[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 50) throw bad();
  return Object.freeze(value.map(sourceRef));
}
function topic(value: unknown): SuggestedTopic {
  const item = record(value);
  if (
    !exactKeys(item, [
      'id',
      'space_id',
      'title',
      'message_ids',
      'start_at',
      'end_at',
      'sample',
      'confidence',
      'source_refs',
    ]) ||
    !isId(item.id) ||
    !isId(item.space_id) ||
    !isText(item.title, 1, 80) ||
    !ids(item.message_ids) ||
    !isInstant(item.start_at) ||
    !isInstant(item.end_at) ||
    Date.parse(item.start_at) > Date.parse(item.end_at) ||
    !isText(item.sample, 0, 80) ||
    typeof item.confidence !== 'number' ||
    item.confidence < 0 ||
    item.confidence > 1
  )
    throw bad();
  return Object.freeze({ ...(item as SuggestedTopic), source_refs: sourceRefs(item.source_refs) });
}
function proposal(value: unknown): OrganizeProposal {
  const item = record(value);
  if (
    !exactKeys(item, [
      'batch_id',
      'subject_id',
      'revision',
      'plan_fingerprint',
      'status',
      'quality_gate',
      'source_refs',
      'topics',
      'needs_review',
      'ignored_count',
      'encoder_mode',
      'degradation',
    ]) ||
    !isId(item.batch_id) ||
    !isId(item.subject_id) ||
    !isRevision(item.revision) ||
    !fingerprint(item.plan_fingerprint) ||
    !['proposed', 'reviewed', 'applied', 'reverted', 'invalidated'].includes(item.status as string) ||
    item.quality_gate !== 'record_only' ||
    !Array.isArray(item.topics) ||
    item.topics.length > 100 ||
    !ids(item.needs_review) ||
    !count(item.ignored_count) ||
    !isText(item.encoder_mode, 1, 64) ||
    (item.degradation !== null && !isText(item.degradation, 0, 200))
  )
    throw bad();
  return Object.freeze({
    ...(item as OrganizeProposal),
    source_refs: sourceRefs(item.source_refs),
    topics: Object.freeze(item.topics.map(topic)),
  });
}
function page(value: unknown) {
  const item = record(value);
  if (
    !exactKeys(item, ['items', 'next_cursor']) ||
    !Array.isArray(item.items) ||
    item.items.length > 100 ||
    (item.next_cursor !== null && !isText(item.next_cursor, 1, 512))
  )
    throw bad();
  const items = item.items.map(proposal);
  if (new Set(items.map((entry) => entry.batch_id)).size !== items.length) throw bad();
  return Object.freeze({ items: Object.freeze(items), next_cursor: item.next_cursor as string | null });
}
function reviewResult(value: unknown, requestId: string, batchId: string, planFingerprint: string) {
  const item = record(value),
    review = record(item.review);
  if (
    !exactKeys(item, ['ok', 'request_id', 'receipt', 'review']) ||
    !exactKeys(review, ['receipt_id', 'batch_id', 'revision', 'plan_fingerprint', 'reviewed_at', 'expires_at']) ||
    !isId(review.receipt_id) ||
    review.batch_id !== batchId ||
    !isRevision(review.revision) ||
    review.plan_fingerprint !== planFingerprint ||
    !isInstant(review.reviewed_at) ||
    !isInstant(review.expires_at) ||
    Date.parse(review.expires_at) - Date.parse(review.reviewed_at) !== 86400000
  )
    throw bad();
  const receipt = writeResult({ ok: item.ok, request_id: item.request_id, receipt: item.receipt }, requestId);
  if (receipt.revision !== review.revision) throw bad();
  return Object.freeze({ receipt, review: Object.freeze(review as ReviewGrant) });
}
function applyResult(value: unknown, requestId: string) {
  const item = record(value);
  if (!exactKeys(item, ['ok', 'request_id', 'receipt', 'change_id']) || !isId(item.change_id)) throw bad();
  const receipt = writeResult({ ok: item.ok, request_id: item.request_id, receipt: item.receipt }, requestId);
  if (!['saved', 'updated'].includes(receipt.write_status)) throw bad();
  return Object.freeze({ receipt, change_id: item.change_id });
}
function revertResult(value: unknown, requestId: string) {
  const item = record(value);
  if (
    !exactKeys(item, ['ok', 'request_id', 'receipt', 'restored_count', 'conflicts']) ||
    !count(item.restored_count) ||
    !Array.isArray(item.conflicts) ||
    item.conflicts.length > 100
  )
    throw bad();
  const conflicts = item.conflicts.map((value) => {
    const conflict = record(value);
    if (
      !exactKeys(conflict, ['entity_id', 'field', 'reason']) ||
      !isId(conflict.entity_id) ||
      !['space_id', 'topic_id', 'title', 'status', 'space_secondary', 'route_source', 'route_confidence'].includes(
        conflict.field as string,
      ) ||
      !['later_edit', 'source_revoked', 'scope_changed'].includes(conflict.reason as string)
    )
      throw bad();
    return Object.freeze(conflict as RevertConflict);
  });
  const receipt = writeResult({ ok: item.ok, request_id: item.request_id, receipt: item.receipt }, requestId);
  if (!['undone', 'skipped'].includes(receipt.write_status)) throw bad();
  return Object.freeze({ receipt, restored_count: item.restored_count as number, conflicts: Object.freeze(conflicts) });
}
function validEdit(value: PlanEdit) {
  const item = record(value);
  if (!isId(item.target_id)) return false;
  if (value.kind === 'rename') return exactKeys(item, ['kind', 'target_id', 'title']) && isText(item.title, 1, 80);
  if (value.kind === 'merge')
    return (
      exactKeys(item, ['kind', 'target_id', 'target_ids']) &&
      ids(item.target_ids, 2) &&
      item.target_ids.includes(value.target_id)
    );
  if (value.kind === 'split')
    return (
      exactKeys(item, ['kind', 'target_id', 'message_ids', 'title']) &&
      ids(item.message_ids, 1) &&
      isText(item.title, 1, 80)
    );
  if (value.kind === 'move') return exactKeys(item, ['kind', 'target_id', 'space_id']) && isId(item.space_id);
  return value.kind === 'ignore' && exactKeys(item, ['kind', 'target_id']);
}
function query(value: OrganizeQuery) {
  if (
    (value.limit !== undefined && (!Number.isSafeInteger(value.limit) || value.limit < 1 || value.limit > 100)) ||
    (value.cursor !== undefined && !isText(value.cursor, 1, 512)) ||
    (value.subject_id !== undefined && !isId(value.subject_id)) ||
    (value.batch_id !== undefined && !isId(value.batch_id))
  )
    throw new DraftApiError('VALIDATION_ERROR');
  return { ...value };
}

export type OrganizeHttpPort = ReturnType<typeof organizeHttpPort>;
export function organizeHttpPort(fetcher: typeof fetch = fetch) {
  const write = async (path: string, body: WriteIdentity, owner: RequestOwner, method: 'POST' | 'PATCH' = 'POST') =>
    writeResult(await draftRequest(fetcher, { method, path, body }, owner), body.request_id);
  return {
    async listProposals(list: OrganizeQuery, owner: RequestOwner) {
      return page(
        await draftRequest(fetcher, { method: 'GET', path: '/api/organize/proposal', query: query(list) }, owner),
      );
    },
    suggest(body: WriteIdentity & { subject_id: string; source_refs: readonly SourceRef[] }, owner: RequestOwner) {
      if (
        body.expected_revision !== 0 ||
        !exactKeys(record(body), ['request_id', 'expected_revision', 'subject_id', 'source_refs']) ||
        !isId(body.subject_id)
      )
        throw new DraftApiError('VALIDATION_ERROR');
      try {
        sourceRefs(body.source_refs);
      } catch {
        throw new DraftApiError('VALIDATION_ERROR');
      }
      return write('/api/organize/proposal', body, owner);
    },
    edit(batchId: string, body: WriteIdentity & { edits: readonly PlanEdit[] }, owner: RequestOwner) {
      if (
        !isRevision(body.expected_revision) ||
        !exactKeys(record(body), ['request_id', 'expected_revision', 'edits']) ||
        !Array.isArray(body.edits) ||
        body.edits.length < 1 ||
        body.edits.length > 100 ||
        !body.edits.every(validEdit)
      )
        throw new DraftApiError('VALIDATION_ERROR');
      return write(`/api/organize/${segment(batchId)}`, body, owner, 'PATCH');
    },
    async review(
      batchId: string,
      body: WriteIdentity & { plan_fingerprint: string; accepted: true },
      owner: RequestOwner,
    ) {
      if (
        !isRevision(body.expected_revision) ||
        !fingerprint(body.plan_fingerprint) ||
        body.accepted !== true ||
        !exactKeys(record(body), ['request_id', 'expected_revision', 'plan_fingerprint', 'accepted'])
      )
        throw new DraftApiError('VALIDATION_ERROR');
      return reviewResult(
        await draftRequest(fetcher, { method: 'POST', path: `/api/organize/${segment(batchId)}/review`, body }, owner),
        body.request_id,
        batchId,
        body.plan_fingerprint,
      );
    },
    async apply(
      batchId: string,
      body: WriteIdentity & { plan_fingerprint: string; review_receipt_id: string },
      owner: RequestOwner,
    ) {
      if (
        !isRevision(body.expected_revision) ||
        !fingerprint(body.plan_fingerprint) ||
        !isId(body.review_receipt_id) ||
        !exactKeys(record(body), ['request_id', 'expected_revision', 'plan_fingerprint', 'review_receipt_id'])
      )
        throw new DraftApiError('VALIDATION_ERROR');
      return applyResult(
        await draftRequest(fetcher, { method: 'POST', path: `/api/organize/apply/${segment(batchId)}`, body }, owner),
        body.request_id,
      );
    },
    async revert(batchId: string, body: WriteIdentity & { change_id: string }, owner: RequestOwner) {
      if (
        !isRevision(body.expected_revision) ||
        !isId(body.change_id) ||
        !exactKeys(record(body), ['request_id', 'expected_revision', 'change_id'])
      )
        throw new DraftApiError('VALIDATION_ERROR');
      return revertResult(
        await draftRequest(fetcher, { method: 'POST', path: `/api/organize/revert/${segment(batchId)}`, body }, owner),
        body.request_id,
      );
    },
  };
}
