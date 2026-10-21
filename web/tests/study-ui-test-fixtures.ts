import { vi } from 'vitest';
import { createStudyPort } from '../src/study/port';
import type { StudyLoadSession } from '../src/study/staticLoader';
import type {
  SearchQuery,
  StudyPort,
  StudyRead,
  StudyScope,
  TermDetail,
  TermResolution,
  TermSummary,
} from '../src/study/types';
import { bundle, gate } from './study-test-fixtures';

export const newStudyPort = () => createStudyPort(bundle());

/** Full session shape with controllable completions. Abort is intentionally
 * ignored after a request has started, to test the consuming hook's own guard. */
export function controlledStudySession() {
  const requests: (ReturnType<typeof gate<StudyPort>> & { signal?: AbortSignal })[] = [];
  let active: StudyPort | undefined,
    disposed = false;
  const reset = vi.fn(() => {
    active?.dispose();
    active = undefined;
  });
  const session: StudyLoadSession = {
    reset,
    dispose: vi.fn(() => {
      disposed = true;
      reset();
    }),
    reload: vi.fn((signal?: AbortSignal) => {
      if (disposed) return Promise.reject(new Error('Disposed test session'));
      reset();
      const request = { ...gate<StudyPort>(), signal };
      requests.push(request);
      return request.promise.then((port) => {
        if (!disposed) active = port;
        return port;
      });
    }),
  };
  return { session, requests };
}

type HeldRead = { signal?: AbortSignal; settled: Promise<void>; release(): void; reject(reason?: unknown): void };
function delay<T>(result: Promise<T>, signal?: AbortSignal) {
  const blocker = gate<void>();
  // Attach a rejection handler immediately; a real scope can be disposed while
  // the artificial transport delay remains pending.
  const outcome = result.then(
    (value) => ({ status: 'resolved' as const, value }),
    (error: unknown) => ({ status: 'rejected' as const, error }),
  );
  const request: HeldRead = {
    signal,
    settled: outcome.then(() => {}),
    release: () => blocker.resolve(),
    reject: blocker.reject,
  };
  return {
    request,
    promise: blocker.promise.then(async () => {
      const settled = await outcome;
      if (settled.status === 'rejected') throw settled.error;
      return settled.value;
    }),
  };
}

/** This is a real validated catalog and full StudyScope. Only selected reads'
 * returned promises are delayed, and deliberately ignore the caller's abort so
 * late-consumer protection is tested independently of the port's own guard. */
export function controlledStudyPort(options: { term?: boolean; resolve?: boolean; search?: boolean } = {}) {
  const real = newStudyPort();
  const termReads: (HeldRead & { termId: string; scope: StudyScope })[] = [];
  const resolutions: (HeldRead & { label: string; scope: StudyScope })[] = [];
  const searches: (HeldRead & { query: SearchQuery; scope: StudyScope })[] = [];
  const scopes: StudyScope[] = [];
  const port: StudyPort = {
    metadata: real.metadata,
    dispose: vi.fn(real.dispose),
    createScope: vi.fn(() => {
      const inner = real.createScope();
      const scope: StudyScope = {
        metadata: inner.metadata,
        reset: vi.fn(inner.reset),
        dispose: vi.fn(inner.dispose),
        resolveEvidence: inner.resolveEvidence,
        readLearning: inner.readLearning,
        search(query, signal): Promise<StudyRead<TermSummary[]>> {
          if (!options.search) return inner.search(query, signal);
          const held = delay(inner.search(query), signal);
          searches.push({ ...held.request, query, scope });
          return held.promise;
        },
        resolveTerm(label, system, signal): Promise<TermResolution> {
          if (!options.resolve) return inner.resolveTerm(label, system, signal);
          const held = delay(inner.resolveTerm(label, system), signal);
          resolutions.push({ ...held.request, label, scope });
          return held.promise;
        },
        readTerm(termId, signal): Promise<StudyRead<TermDetail>> {
          if (!options.term) return inner.readTerm(termId, signal);
          const held = delay(inner.readTerm(termId), signal);
          termReads.push({ ...held.request, termId, scope });
          return held.promise;
        },
      };
      scopes.push(scope);
      return scope;
    }),
  };
  return { port, scopes, termReads, resolutions, searches };
}
