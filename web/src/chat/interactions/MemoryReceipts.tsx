import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { operationNamespace } from '../../api/client';
import { Disclosure } from '../../components/ui/Controls';
import { publicChatText } from '../publicProjection';
import type { Receipt } from '../types';
import type { MemoryCommands, MemoryCommandReceipt } from './contracts';
import { v3MemoryCommands } from './memoryCommands';
import { MemoryCard } from './MemoryCard';
import {
  createMemoryReceiptRegistry,
  receiptAliases,
  receiptKey,
  receiptSignature,
  rememberReceipt,
  type DisplayReceipt,
  type MemoryReceiptRegistry,
} from './memoryProjection';

export function MemoryReceipts({
  receipts,
  commands = v3MemoryCommands,
  registry,
}: {
  receipts: Receipt[];
  commands?: MemoryCommands;
  registry?: MemoryReceiptRegistry;
}) {
  const local = useRef(createMemoryReceiptRegistry());
  if (local.current.namespace !== operationNamespace()) local.current = createMemoryReceiptRegistry();
  const activeRegistry = registry?.namespace === operationNamespace() ? registry : local.current;
  const seen = activeRegistry.receipts;
  const version = useSyncExternalStore(
    activeRegistry.subscribe,
    activeRegistry.getSnapshot,
    activeRegistry.getSnapshot,
  );
  const [feedback, setFeedback] = useState<{ text: string; version: number; key: string; status: string }>();
  const before = new Map<string, string>();
  for (const receipt of receipts)
    for (const alias of receiptAliases(receipt)) {
      const existing = seen.get(alias);
      if (existing) before.set(alias, receiptSignature(existing));
    }
  const current = new Map<string, DisplayReceipt>();
  for (const receipt of receipts) {
    const value = rememberReceipt(seen, receipt);
    current.set(receiptKey(value), value);
  }
  const changes = [...before]
    .filter(([key, prior]) => prior !== receiptSignature(seen.get(key)!))
    .map(([key]) => [key, receiptSignature(seen.get(key)!)])
    .sort(([left], [right]) => left.localeCompare(right));
  const change = changes.length ? JSON.stringify(changes) : '';
  const notified = useRef<{ registry: MemoryReceiptRegistry; change: string }>();
  useEffect(() => {
    if (
      !change ||
      activeRegistry.namespace !== operationNamespace() ||
      (notified.current?.registry === activeRegistry && notified.current.change === change)
    )
      return;
    notified.current = { registry: activeRegistry, change };
    activeRegistry.notify();
  }, [activeRegistry, change]);
  const resolved = [...current.values()];
  const saved = resolved.filter((receipt) => receipt.write_status === 'saved');
  const others = resolved.filter((receipt) => receipt.write_status !== 'saved');
  function confirmed(source: DisplayReceipt, result: MemoryCommandReceipt) {
    rememberReceipt(seen, { ...source, ...result, summary: publicChatText(result.summary ?? source.summary) });
    activeRegistry.notify();
    const text =
      result.write_status === 'saved'
        ? result.category_saved
          ? '已记下这条信息，并更新了本地同类记忆偏好。'
          : '已记下这条信息。'
        : result.write_status === 'dismissed'
          ? '这次不记，此条没有保存为有效记忆。'
          : '撤销已确认，此条不会再提起。';
    setFeedback({ text, version: activeRegistry.getSnapshot(), key: receiptKey(source), status: result.write_status });
  }
  const render = (receipt: DisplayReceipt) => (
    <MemoryCard
      key={receiptKey(receipt)}
      receipt={receipt}
      commands={commands}
      onConfirmed={confirmed}
      onAttempt={() => setFeedback(undefined)}
    />
  );
  return (
    <div className="receipt-group">
      {feedback?.version === version && seen.get(feedback.key)?.write_status === feedback.status && (
        <p className="meta receipt-action-feedback" role="status" aria-live="polite">
          {feedback.text}
        </p>
      )}
      {saved.length > 1 ? (
        <Disclosure title={`记下了 ${saved.length} 件事`} count="查看与撤销">
          {saved.map(render)}
        </Disclosure>
      ) : (
        saved.map(render)
      )}
      {others.map(render)}
    </div>
  );
}
