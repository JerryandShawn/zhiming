import type { Receipt } from '../../chat/types';
import type { MemoryAction, MemoryCommandReceipt } from '../../chat/interactions/contracts';
import { createAboutMeSeed } from './fixtures';
import { applyAboutMeCommand, validateAboutMeSeed } from './model';
import { currentMemoryReceipts, previewDeletion, projectSnapshot, projectSource } from './projections';
import { AboutMeError, type AboutMeCommand, type AboutMePort, type AboutMeReceipt, type AboutMeState } from './types';

function freeze<T>(value: T): T {
  if (value && typeof value === 'object') {
    for (const nested of Object.values(value)) freeze(nested);
    Object.freeze(value);
  }
  return value;
}
function ordered(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(ordered);
  if (value && typeof value === 'object')
    return Object.fromEntries(
      Object.entries(value)
        .filter(([, item]) => item !== undefined)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, ordered(item)]),
    );
  return value;
}
function fingerprint(value: unknown): string {
  return JSON.stringify(ordered(value));
}

// One aggregate owns both Chat receipts and About Me. It has no I/O dependencies.
export function createAboutMeStore(
  seed: AboutMeState = createAboutMeSeed(),
  now = () => new Date().toISOString(),
): AboutMePort {
  let state = structuredClone(seed),
    sequence = 0;
  validateAboutMeSeed(state);
  let snapshot = freeze(projectSnapshot(state));
  const listeners = new Set<() => void>();
  const completed = new Map<string, { fingerprint: string; receipt: AboutMeReceipt }>();
  function dispatch(command: AboutMeCommand, client?: unknown): AboutMeReceipt {
    const signature = fingerprint({ command, client });
    const previous = completed.get(command.requestId);
    if (previous) {
      if (previous.fingerprint !== signature)
        throw new AboutMeError('REPLAY_CHANGED', 409, '原操作的内容已经改变，请重新确认。');
      return previous.receipt;
    }
    const result = applyAboutMeCommand(state, command, { at: now(), newId: (kind) => `local-${kind}-${++sequence}` });
    state = result.state;
    snapshot = freeze(projectSnapshot(state));
    const receipt = freeze(result.receipt);
    completed.set(command.requestId, { fingerprint: signature, receipt });
    for (const listener of [...listeners]) {
      try {
        listener();
      } catch {
        /* A failed view observer cannot undo a committed command. */
      }
    }
    return receipt;
  }
  function match(item: Receipt) {
    const current = currentMemoryReceipts(state).find((candidate) =>
      item.fact_id
        ? candidate.fact_id === item.fact_id
        : Boolean(item.proposal_id && candidate.proposal_id === item.proposal_id),
    );
    return current &&
      current.revision === item.revision &&
      current.write_status === item.write_status &&
      current.summary === item.summary &&
      (!item.proposal_id || current.proposal_id === item.proposal_id) &&
      (!item.category || current.category === item.category)
      ? current
      : undefined;
  }
  function supports(action: MemoryAction, item: Receipt): boolean {
    const current = match(item);
    if (!current) return false;
    if (action === 'undo') return current.write_status === 'saved' && Boolean(item.fact_id);
    return (
      ['remember', 'dismiss', 'remember-category'].includes(action) &&
      current.write_status === 'pending_confirmation' &&
      Boolean(item.proposal_id) &&
      (action !== 'remember-category' || Boolean(item.category && item.category === current.category))
    );
  }
  return {
    getSnapshot: () => snapshot,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    readSource: (ref) => freeze(projectSource(state, ref)),
    previewDelete: (id, scope, ref) => freeze(previewDeletion(state, id, scope, ref)),
    async execute(command) {
      return dispatch(command);
    },
    currentReceipts: () => freeze(currentMemoryReceipts(state)),
    memory: {
      supports,
      async execute(action, item) {
        const id = (action === 'undo' ? item.fact_id : item.proposal_id) || '';
        const requestId = `chat:${action}:${id}:${item.revision ?? 0}`;
        const command: AboutMeCommand =
          action === 'undo'
            ? { type: 'memory-stop', id, expectedRevision: item.revision ?? 0, requestId }
            : { type: 'proposal-act', id, action, expectedRevision: item.revision ?? 0, requestId };
        const client = {
          action,
          fact: item.fact_id,
          proposal: item.proposal_id,
          revision: item.revision,
          status: item.write_status,
          summary: item.summary,
          category: item.category,
        };
        if (!completed.has(requestId) && !supports(action, item)) {
          const exists =
            state.memories.some((fact) => fact.id === id) || state.proposals.some((proposal) => proposal.id === id);
          throw new AboutMeError(
            exists ? 'CONFLICT' : 'NOT_FOUND',
            exists ? 409 : 404,
            exists ? '这条记录已变化或缺少授权条件，请重新查看后再操作。' : '没有找到这条合成记录。',
          );
        }
        const result = dispatch(command, client).memoryReceipt;
        if (!result || !['saved', 'stopped', 'deleted', 'dismissed'].includes(result.write_status))
          throw new AboutMeError('INVALID', 422, '尚未收到有效的记忆确认。');
        // The shared immutable receipt is also the idempotent result object.
        return result as MemoryCommandReceipt;
      },
    },
  };
}
