import { appliedFields, applyChanges, buildChanges, checkSources, revertFields } from './changes';
import { editDraft, validateSeed } from './draft';
import { createOrganizeSeed } from './seed';
import { projectOrganizeSources } from './sourceProjection';
import {
  OrganizeError,
  type AppliedField,
  type CommandReceipt,
  type ConfirmationScope,
  type ConfirmationTicket,
  type OrganizeDocument,
  type OrganizeOptions,
  type OrganizePort,
  type OrganizeSnapshot,
  type RevertConflict,
  type WireChangeSet,
} from './types';
import { canonical, fieldId, freeze, identity, sha256, validateDocument } from './values';

export const ORGANIZE_CONFIRMATION_TTL_MS = 15 * 60 * 1000;
const MODULE_SHA = '8c554bd4af6788b3a4d98b9dd0d7618c591f7cfd';

/** Offline adapter only. Its ledger is never a server authorization or a persistent receipt. */
export function createOrganizeDemoPort(options: OrganizeOptions = {}): OrganizePort {
  let draft = structuredClone(options.seed ?? createOrganizeSeed());
  validateSeed(draft);
  if (draft.segments.some((item) => item.decision !== 'pending'))
    throw new OrganizeError('INVALID', '初始合成建议必须先经过人工审阅。');
  let document = structuredClone(draft.document),
    revision = 1;
  let status: OrganizeSnapshot['status'] = 'draft';
  let changeset: WireChangeSet | null = null,
    fields: AppliedField[] = [],
    conflicts: RevertConflict[] = [];
  const now = options.now ?? Date.now,
    digest = options.digest ?? sha256;
  const nonce = options.nonce ?? (() => crypto.randomUUID());
  const listeners = new Set<() => void>();
  const tickets = new Map<string, { ticket: ConfirmationTicket; consumed: boolean }>();
  const completed = new Map<string, { signature: string; receipt: CommandReceipt }>();
  let chain: Promise<unknown> = Promise.resolve();

  function projection(): OrganizeSnapshot {
    const accepted = draft.segments.filter((item) => item.decision === 'accepted');
    const visible = projectOrganizeSources(draft, document);
    return freeze(
      structuredClone({
        revision,
        status,
        spaces: draft.spaces,
        topics: draft.topics,
        segments: visible.segments,
        document: visible.document,
        summary: {
          accepted_segments: accepted.length,
          rejected_segments: draft.segments.filter((item) => item.decision === 'rejected').length,
          pending_segments: draft.segments.filter((item) => item.decision === 'pending').length,
          message_count: accepted.reduce((count, item) => count + item.message_ids.length, 0),
          field_changes: changeset?.ops.filter((op) => op.field !== null).length ?? 0,
          topic_creations: changeset?.ops.filter((op) => op.field === null).length ?? 0,
        },
        changeset,
        ...(fields.length ? { applied: { batch_id: draft.batch_id, fields } } : {}),
        conflicts,
        metadata: {
          module_sha: MODULE_SHA,
          mode: 'synthetic' as const,
          encoder_mode: 'keyword-demo',
          degradation: '合成人工审阅候选；关键词降级不能自动应用真实旧历史。',
        },
      }),
    );
  }
  let snapshot = projection();
  function publish() {
    revision++;
    snapshot = projection();
    for (const listener of [...listeners]) {
      try {
        listener();
      } catch {
        /* Observer failure cannot roll back a confirmed local command. */
      }
    }
  }
  function clock() {
    const value = now();
    if (!Number.isSafeInteger(value)) throw new OrganizeError('UNAVAILABLE', '本地时钟暂不可用，请重新确认。');
    return value;
  }
  function schedule(command: { request_id: string }, work: () => Promise<string>): Promise<CommandReceipt> {
    const run = async (): Promise<CommandReceipt> => {
      let signature: string;
      try {
        identity(command.request_id);
        signature = canonical(command);
      } catch {
        return {
          status: 'rejected',
          request_id: command.request_id,
          revision,
          code: 'INVALID',
          message: '操作标识无效。',
        };
      }
      const previous = completed.get(command.request_id);
      if (previous)
        return previous.signature === signature
          ? previous.receipt
          : freeze({
              status: 'rejected',
              request_id: command.request_id,
              revision,
              code: 'REPLAY_CHANGED',
              message: '原操作内容已改变，请重新确认。',
            });
      let receipt: CommandReceipt;
      try {
        const message = await work();
        receipt = { status: 'accepted', request_id: command.request_id, revision, message };
      } catch (reason) {
        receipt = {
          status: 'rejected',
          request_id: command.request_id,
          revision,
          code: reason instanceof OrganizeError ? reason.code : 'UNAVAILABLE',
          message: reason instanceof OrganizeError ? reason.message : '本地整理未完成，未修改本次数据。',
        };
      }
      const frozen = freeze(receipt);
      completed.set(command.request_id, { signature, receipt: frozen });
      return frozen;
    };
    const result = chain.then(run, run);
    chain = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }
  function normalizedScope(scope: ConfirmationScope): ConfirmationScope {
    if (scope.action === 'apply') {
      if (status !== 'draft' || !changeset || !changeset.ops.length || scope.fields !== undefined)
        throw new OrganizeError('INVALID', '请先接受至少一个片段，再确认应用。');
      return { action: 'apply' };
    }
    if (scope.action !== 'revert' || status === 'draft' || !fields.some((item) => item.state === 'applied'))
      throw new OrganizeError('INVALID', '没有尚可撤销的整理字段。');
    if (!scope.fields) return { action: 'revert' };
    const ids = scope.fields.map(fieldId);
    if (
      !ids.length ||
      new Set(ids).size !== ids.length ||
      ids.some((id) => !fields.some((item) => item.state === 'applied' && fieldId(item) === id))
    )
      throw new OrganizeError('INVALID_SELECTION', '请选择尚未撤销且属于本批的字段。');
    if (changeset && scope.fields.some((field) => field.collection === 'topics' && field.field === null)) {
      const preview = revertFields(document, changeset, fields, scope.fields);
      if (preview.conflicts.some((item) => item.reason === 'later_references'))
        throw new OrganizeError('INVALID_SELECTION', '请先同时选择该话题的归属标签，或先撤销这些标签。');
    }
    const keys = scope.fields.map(({ collection, entity_id, field }) => ({ collection, entity_id, field }));
    return { action: 'revert', fields: keys.sort((a, b) => fieldId(a).localeCompare(fieldId(b))) };
  }
  function ticketFor(scope: ConfirmationScope): ConfirmationTicket {
    const normalized = normalizedScope(scope),
      at = clock();
    const existing = [...tickets.values()].find(
      (item) =>
        !item.consumed &&
        item.ticket.revision === revision &&
        at >= item.ticket.issued_at_ms &&
        at < item.ticket.expires_at_ms &&
        sameScope(item.ticket, normalized),
    );
    if (existing) return existing.ticket;
    const id = nonce();
    identity(id);
    if (tickets.has(id)) throw new OrganizeError('UNAVAILABLE', '确认标识发生重复，请刷新合成示例。');
    const ticket = freeze({
      ...structuredClone(normalized),
      id,
      batch_id: draft.batch_id,
      owner_id: document.owner_id,
      subject_id: document.subject_id,
      revision,
      issued_at_ms: at,
      expires_at_ms: at + ORGANIZE_CONFIRMATION_TTL_MS,
    });
    tickets.set(id, { ticket, consumed: false });
    return ticket;
  }
  function checkTicket(id: string) {
    const item = tickets.get(id);
    if (!item) throw new OrganizeError('INVALID', '确认卡不存在，请重新打开。');
    const ticket = item.ticket,
      at = clock();
    if (at < ticket.issued_at_ms || at >= ticket.expires_at_ms)
      throw new OrganizeError('EXPIRED', '这张卡已过期，我重新发一张');
    if (item.consumed) throw new OrganizeError('CONSUMED', '这次确认已使用，请读取当前结果。');
    if (
      ticket.revision !== revision ||
      ticket.batch_id !== draft.batch_id ||
      ticket.owner_id !== document.owner_id ||
      ticket.subject_id !== document.subject_id
    )
      throw new OrganizeError('CONFLICT', '建议或资料已变化，请重新查看摘要并确认。');
    return item;
  }
  return {
    getSnapshot: () => snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    edit(command) {
      return schedule(command, async () => {
        if (status !== 'draft' || command.expected_revision !== revision)
          throw new OrganizeError('CONFLICT', '建议版本已变化，请重新核对。');
        const expected = revision,
          next = editDraft(draft, command.intent);
        const changes = await buildChanges(next, digest);
        if (revision !== expected) throw new OrganizeError('CONFLICT', '核对期间资料已变化，未保存这次草稿。');
        draft = next;
        changeset = changes;
        conflicts = [];
        publish();
        return '已更新本地审阅草稿，尚未应用。';
      });
    },
    prepareConfirmation: ticketFor,
    execute(command) {
      return schedule(command, async () => {
        const item = checkTicket(command.ticket_id),
          ticket = item.ticket,
          changes = changeset;
        if (!changes) throw new OrganizeError('INVALID', '尚无可应用的整理变更。');
        await checkSources(document, changes, digest);
        checkTicket(command.ticket_id);
        if (ticket.action === 'apply') {
          if (status !== 'draft') throw new OrganizeError('CONFLICT', '本批已经应用或撤销。');
          const next = applyChanges(document, changes);
          document = next;
          fields = appliedFields(changes, draft);
          conflicts = [];
          status = 'applied';
        } else {
          const next = revertFields(document, changes, fields, ticket.fields);
          document = next.document;
          fields = next.fields;
          conflicts = next.conflicts;
          status = fields.some((field) => field.state !== 'reverted') ? 'partially_reverted' : 'reverted';
        }
        item.consumed = true;
        publish();
        return ticket.action === 'apply'
          ? '已应用本地整理；原消息保持不变。'
          : status === 'reverted'
            ? '本批整理字段已全部撤销。'
            : '已核对选定字段；尚未撤销或后来改过的字段已保留。';
      });
    },
    refresh(next: OrganizeDocument) {
      validateDocument(next, document.owner_id, document.subject_id);
      document = structuredClone(next);
      publish();
    },
  };
}
function sameScope(ticket: ConfirmationTicket, scope: ConfirmationScope) {
  return canonical({ action: ticket.action, ...(ticket.fields ? { fields: ticket.fields } : {}) }) === canonical(scope);
}
