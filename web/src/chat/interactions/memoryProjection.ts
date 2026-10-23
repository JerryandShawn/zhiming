import type { Receipt } from '../types';
import { operationNamespace } from '../../api/client';

export type DisplayReceipt = Receipt & { category_saved?: boolean };
export type MemoryReceiptRegistry = {
  namespace: string;
  receipts: Map<string, DisplayReceipt>;
  subscribe: (listener: () => void) => () => void;
  getSnapshot: () => number;
  notify: () => void;
};
export function createMemoryReceiptRegistry(): MemoryReceiptRegistry {
  const listeners = new Set<() => void>();
  let revision = 0;
  return {
    namespace: operationNamespace(),
    receipts: new Map(),
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getSnapshot: () => revision,
    notify: () => {
      revision++;
      for (const listener of [...listeners]) listener();
    },
  };
}
export function receiptKey(receipt: Receipt) {
  return receipt.proposal_id ? `proposal:${receipt.proposal_id}` : `fact:${receipt.fact_id}`;
}
const rank = (receipt: Receipt) =>
  ['stopped', 'deleted', 'dismissed', 'undone', 'rejected'].includes(receipt.write_status)
    ? 2
    : receipt.write_status === 'saved'
      ? 1
      : 0;
function newer(left: DisplayReceipt, right: DisplayReceipt): DisplayReceipt {
  const bothVersions = Number.isInteger(left.revision) && Number.isInteger(right.revision);
  let winner = left;
  if (bothVersions && right.revision! > left.revision!) winner = right;
  else if (bothVersions && right.revision! < left.revision!) winner = left;
  else if (rank(right) > rank(left)) winner = right;
  else if (rank(right) === rank(left) && !Number.isInteger(left.revision) && Number.isInteger(right.revision))
    winner = right;
  return {
    ...(winner === left ? right : left),
    ...winner,
    fact_id: winner.fact_id || (winner === left ? right.fact_id : left.fact_id),
    proposal_id: winner.proposal_id || (winner === left ? right.proposal_id : left.proposal_id),
    category: winner.category || (winner === left ? right.category : left.category),
    category_saved: winner.category_saved ?? (winner === left ? right.category_saved : left.category_saved),
    undo_token: winner.undo_token || (winner === left ? right.undo_token : left.undo_token),
    revision:
      Number.isInteger(left.revision) && Number.isInteger(right.revision)
        ? Math.max(left.revision!, right.revision!)
        : (left.revision ?? right.revision),
    summary: winner.summary || (winner === left ? right.summary : left.summary),
  };
}
export function receiptAliases(receipt: Receipt) {
  return [
    receipt.fact_id ? `fact:${receipt.fact_id}` : '',
    receipt.proposal_id ? `proposal:${receipt.proposal_id}` : '',
  ].filter(Boolean);
}
export function receiptSignature(receipt: DisplayReceipt) {
  return JSON.stringify([
    receipt.fact_id,
    receipt.proposal_id,
    receipt.write_status,
    receipt.revision,
    receipt.summary,
    receipt.category,
    receipt.category_saved,
    receipt.undo_token,
    receipt.sensitive,
  ]);
}
// A late final can repeat an older saved receipt after a confirmed withdrawal.
// Preserve the highest observed revision, and keep terminal consent at equal revision.
export function rememberReceipt(seen: Map<string, DisplayReceipt>, receipt: DisplayReceipt): DisplayReceipt {
  let current = receipt;
  const keys = new Set(receiptAliases(receipt));
  for (const key of keys) {
    const existing = seen.get(key);
    if (existing) {
      current = newer(existing, current);
      for (const alias of receiptAliases(existing)) keys.add(alias);
    }
  }
  for (const alias of receiptAliases(current)) keys.add(alias);
  for (const key of keys) seen.set(key, current);
  return current;
}
