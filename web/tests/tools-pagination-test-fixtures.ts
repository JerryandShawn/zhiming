import { vi } from 'vitest';
import type { ToolPort, ToolRead, WindowQuery, WindowSample } from '../src/tools/types';
import { gate } from './tools-test-fixtures';
import { countedTools } from './tools-form-test-fixtures';

export const fullQuery: WindowQuery = {
  purpose: '签约',
  startDate: '2026-10-21',
  endDate: '2026-10-27',
  offset: 0,
  limit: 31,
};
export const middleQuery: WindowQuery = { ...fullQuery, offset: 3, limit: 3 };
export const emptyQuery: WindowQuery = { ...fullQuery, offset: 7, limit: 3 };
export const nextUnpublishedQuery: WindowQuery = { ...fullQuery, offset: 6, limit: 3 };
export const previousUnpublishedQuery: WindowQuery = { ...fullQuery, offset: 0, limit: 3 };

/** A complete real port with one extra local transport delay. The port's own
 * completed result is retained before a reset, then deliberately delivered late
 * without consulting signal to exercise the consumer's independent stale guard.
 * Public sample bytes, provenance, ranking and evidence are never modified. */
export function delayedWindowTools() {
  const controlled = countedTools();
  const reads: {
    query: WindowQuery;
    signal?: AbortSignal;
    settled: Promise<void>;
    release(): void;
    reject(reason?: unknown): void;
  }[] = [];
  const wrap = (inner: ToolPort): ToolPort => ({
    windows: inner.windows,
    reset: inner.reset,
    createScope: () => wrap(inner.createScope()),
    resolveEvidence: inner.resolveEvidence,
    synastry: inner.synastry,
    windowSearch: vi.fn((query, signal): Promise<ToolRead<WindowSample>> => {
      const blocked = gate<void>();
      const outcome = inner.windowSearch(query).then(
        (value) => ({ status: 'resolved' as const, value }),
        (error: unknown) => ({ status: 'rejected' as const, error }),
      );
      reads.push({
        query: structuredClone(query),
        signal,
        settled: outcome.then(() => {}),
        release: () => blocked.resolve(),
        reject: blocked.reject,
      });
      return blocked.promise.then(async () => {
        const result = await outcome;
        if (result.status === 'rejected') throw result.error;
        return result.value;
      });
    }),
  });
  return { ...controlled, port: wrap(controlled.port), reads };
}
