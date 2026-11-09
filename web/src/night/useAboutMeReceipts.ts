import { useEffect, useSyncExternalStore } from 'react';
import {
  rememberReceipt,
  receiptAliases,
  receiptSignature,
  type MemoryReceiptRegistry,
} from '../chat/interactions/memoryProjection';
import type { AboutMePort } from './me/types';

// Both screens observe one aggregate. Notify only when its public receipt changes,
// so a duplicate acknowledgement cannot erase the card's confirmation feedback.
export function useAboutMeReceipts(port: AboutMePort, registry: MemoryReceiptRegistry) {
  const snapshot = useSyncExternalStore(port.subscribe, port.getSnapshot);
  useEffect(() => {
    let changed = false;
    for (const receipt of port.currentReceipts()) {
      const previous = receiptAliases(receipt)
        .map((alias) => registry.receipts.get(alias))
        .find(Boolean);
      const signature = previous ? receiptSignature(previous) : '';
      const next = rememberReceipt(registry.receipts, receipt);
      if (signature !== receiptSignature(next)) changed = true;
    }
    if (changed) registry.notify();
  }, [port, registry, snapshot]);
}
