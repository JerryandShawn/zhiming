import { StrictMode } from 'react';
import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { createStudyPort } from '../src/study/port';
import type { StudyPort } from '../src/study/types';
import { useStudyTermsController } from '../src/study/useStudyTermsController';
import { bundle, evidenceRef } from './study-test-fixtures';
import { controlledStudyPort } from './study-ui-test-fixtures';

beforeEach(() => history.replaceState({ page: 'study' }, '', '/#/chat'));
const baseHistory = () => waitFor(() => expect(history.state).toEqual({ page: 'study' }));
function trigger() {
  render(
    <main id="main" tabIndex={-1}>
      <button type="button">词条触发位置</button>
    </main>,
  );
  return screen.getByRole('button', { name: '词条触发位置' });
}

describe('term detail hook owns only its own reads and history entry', () => {
  it('survives StrictMode replay without disposing the shared catalog or retaining the first index scope', async () => {
    const controlled = controlledStudyPort();
    const { result, unmount } = renderHook(() => useStudyTermsController(controlled.port), {
      wrapper: StrictMode,
    });
    await waitFor(() => expect(result.current.indexStatus).toBe('ready'));
    expect(result.current.terms).toHaveLength(212);
    expect(controlled.scopes).toHaveLength(2);
    expect(controlled.scopes[0].dispose).toHaveBeenCalledTimes(1);
    expect(controlled.scopes[1].dispose).not.toHaveBeenCalled();
    expect(controlled.port.dispose).not.toHaveBeenCalled();
    unmount();
    expect(controlled.scopes[1].dispose).toHaveBeenCalledTimes(1);
    expect(controlled.port.metadata().glossary.entry_count).toBe(212);
    controlled.port.dispose();
  });

  it('does not reopen after close when an already successful detail read is delivered late', async () => {
    const controlled = controlledStudyPort({ term: true });
    const { result } = renderHook(() => useStudyTermsController(controlled.port));
    const origin = trigger(),
      termId = bundle().terms.entries[0].term_id;
    act(() => result.current.openTerm(termId, origin));
    expect(result.current.open).toBe(true);
    expect(result.current.view?.phase).toBe('loading');
    const pending = controlled.termReads[0];
    await act(async () => pending.settled);
    act(() => result.current.close());
    expect(pending.signal?.aborted).toBe(true);
    expect(pending.scope.dispose).toHaveBeenCalledTimes(1);
    await act(async () => pending.release());
    await baseHistory();
    expect(result.current.open).toBe(false);
    expect(result.current.view).toBeUndefined();
    act(() => result.current.returnFocus());
    expect(origin).toHaveFocus();
  });

  it('stops a closed label lookup before it can chain a detail read', async () => {
    const controlled = controlledStudyPort({ resolve: true, term: true });
    const { result } = renderHook(() => useStudyTermsController(controlled.port));
    const origin = trigger();
    act(() => result.current.openLabel(bundle().terms.entries[0].term, origin));
    const pending = controlled.resolutions[0];
    await act(async () => pending.settled);
    act(() => result.current.close());
    await act(async () => pending.release());
    await baseHistory();
    expect(controlled.termReads).toHaveLength(0);
    expect(result.current.view).toBeUndefined();
    expect(result.current.open).toBe(false);
  });

  it('lets browser Back close a pending detail and keeps Forward and late delivery inert', async () => {
    const controlled = controlledStudyPort({ term: true });
    const { result } = renderHook(() => useStudyTermsController(controlled.port));
    const origin = trigger();
    act(() => result.current.openTerm(bundle().terms.entries[0].term_id, origin));
    const marker = history.state.__mingjing_panel,
      pending = controlled.termReads[0];
    await act(async () => pending.settled);
    act(() => history.back());
    await baseHistory();
    await waitFor(() => expect(result.current.open).toBe(false));
    expect(pending.signal?.aborted).toBe(true);
    expect(pending.scope.dispose).toHaveBeenCalledTimes(1);
    await act(async () => pending.release());
    act(() => history.forward());
    await waitFor(() => expect(history.state.__mingjing_panel).toBe(marker));
    expect(result.current.open).toBe(false);
    expect(result.current.view).toBeUndefined();
  });

  it('hides a retiring detail on port replacement and prevents its late result from replacing the new owner', async () => {
    const a = controlledStudyPort({ term: true }),
      b = controlledStudyPort({ term: true });
    const { result, rerender } = renderHook(
      ({ port }: { port: StudyPort | undefined }) => useStudyTermsController(port),
      {
        initialProps: { port: a.port },
      },
    );
    const origin = trigger(),
      entries = bundle().terms.entries;
    act(() => result.current.openTerm(entries[0].term_id, origin));
    const old = a.termReads[0];
    await act(async () => old.settled);
    rerender({ port: b.port });
    expect(result.current.view).toBeUndefined();
    expect(result.current.open).toBe(false);
    expect(old.signal?.aborted).toBe(true);
    await baseHistory();
    act(() => result.current.openTerm(entries[1].term_id, origin));
    const current = b.termReads[0];
    await act(async () => current.settled);
    await act(async () => current.release());
    expect(result.current.view).toMatchObject({ phase: 'ready', detail: { term: { term_id: entries[1].term_id } } });
    await act(async () => old.release());
    expect(result.current.view).toMatchObject({ phase: 'ready', detail: { term: { term_id: entries[1].term_id } } });
    expect(result.current.open).toBe(true);
    act(() => result.current.close());
    await baseHistory();
  });

  it('does not publish the first A index when the port identity changes A→B→A', async () => {
    const a = controlledStudyPort({ search: true }),
      b = controlledStudyPort({ search: true });
    const { result, rerender } = renderHook(
      ({ port }: { port: StudyPort | undefined }) => useStudyTermsController(port),
      {
        initialProps: { port: a.port },
      },
    );
    const oldA = a.searches[0];
    await act(async () => oldA.settled);
    rerender({ port: b.port });
    const oldB = b.searches[0];
    await act(async () => oldB.settled);
    rerender({ port: a.port });
    const newA = a.searches[1];
    expect(result.current.indexStatus).toBe('loading');
    expect(result.current.terms).toHaveLength(0);
    await act(async () => {
      oldA.release();
      oldB.release();
    });
    expect(result.current.indexStatus).toBe('loading');
    expect(result.current.terms).toHaveLength(0);
    await act(async () => newA.release());
    expect(result.current.indexStatus).toBe('ready');
    expect(result.current.terms).toHaveLength(212);
    expect(oldA.signal?.aborted).toBe(true);
    expect(oldB.signal?.aborted).toBe(true);
  });

  it('keeps the newest A detail when earlier A succeeds or B fails after A→B→A selections', async () => {
    const controlled = controlledStudyPort({ term: true });
    const { result } = renderHook(() => useStudyTermsController(controlled.port));
    const origin = trigger(),
      [a, b] = bundle().terms.entries;
    act(() => result.current.openTerm(a.term_id, origin));
    await act(async () => controlled.termReads[0].settled);
    act(() => result.current.openTerm(b.term_id, origin));
    await act(async () => controlled.termReads[1].settled);
    act(() => result.current.openTerm(a.term_id, origin));
    const [oldA, oldB, newA] = controlled.termReads;
    await act(async () => newA.release());
    expect(result.current.view).toMatchObject({ phase: 'ready', detail: { term: { term_id: a.term_id } } });
    await act(async () => {
      oldA.release();
      oldB.reject(new Error('retired synthetic failure'));
    });
    expect(result.current.view).toMatchObject({ phase: 'ready', detail: { term: { term_id: a.term_id } } });
    expect(oldA.signal?.aborted).toBe(true);
    expect(oldB.signal?.aborted).toBe(true);
    expect(oldA.scope.dispose).toHaveBeenCalledTimes(1);
    expect(oldB.scope.dispose).toHaveBeenCalledTimes(1);
    expect(newA.scope.dispose).not.toHaveBeenCalled();
    act(() => result.current.close());
    await baseHistory();
  });

  it('does not let the retiring Back of an explicit close cancel a newly requested detail', async () => {
    const controlled = controlledStudyPort({ term: true });
    const { result } = renderHook(() => useStudyTermsController(controlled.port));
    const origin = trigger(),
      [a, b] = bundle().terms.entries;
    act(() => result.current.openTerm(a.term_id, origin));
    await act(async () => controlled.termReads[0].settled);
    act(() => {
      result.current.close();
      result.current.openTerm(b.term_id, origin);
    });
    const current = controlled.termReads[1];
    await act(async () => current.release());
    await waitFor(() => expect(result.current.open).toBe(true));
    expect(result.current.view).toMatchObject({ phase: 'ready', detail: { term: { term_id: b.term_id } } });
    expect(current.signal?.aborted).toBe(false);
    await act(async () => controlled.termReads[0].release());
    expect(result.current.view).toMatchObject({ phase: 'ready', detail: { term: { term_id: b.term_id } } });
    act(() => result.current.close());
    await baseHistory();
  });

  it('requires an explicit choice for a cross-system alias and never invalidates a sibling learning scope', async () => {
    const data = bundle(),
      first = data.terms.entries.find((entry) => entry.system === 'bazi')!,
      second = data.terms.entries.find((entry) => entry.system === 'ziwei')!;
    first.aliases.push('合成共享别名');
    second.aliases.push('合成共享别名');
    const port = createStudyPort(data),
      sibling = port.createScope(),
      sample = data.learning[0],
      ref = evidenceRef(sample);
    await sibling.readLearning(sample.sample_id);
    const { result, unmount } = renderHook(() => useStudyTermsController(port));
    const origin = trigger();
    await waitFor(() => expect(result.current.indexStatus).toBe('ready'));
    expect(sibling.resolveEvidence(ref)).toMatchObject({
      document_id: ref.document_id,
      alias: ref.alias,
      claim_id: ref.claim_id,
    });
    act(() => result.current.openLabel('合成共享别名', origin));
    await waitFor(() => expect(result.current.view?.phase).toBe('choose'));
    expect(result.current.view).toMatchObject({
      phase: 'choose',
      candidates: [
        expect.objectContaining({ term_id: first.term_id }),
        expect.objectContaining({ term_id: second.term_id }),
      ],
    });
    act(() => result.current.choose(second.term_id));
    await waitFor(() =>
      expect(result.current.view).toMatchObject({ phase: 'ready', detail: { term: { term_id: second.term_id } } }),
    );
    expect(sibling.resolveEvidence(ref)).toBeDefined();
    act(() => result.current.close());
    await baseHistory();
    expect(sibling.resolveEvidence(ref)).toBeDefined();
    unmount();
    expect(sibling.resolveEvidence(ref)).toBeDefined();
    sibling.dispose();
    port.dispose();
  });

  it('does not steal focus back while a new opening is pending, and uses main when the old origin is removed', async () => {
    const controlled = controlledStudyPort({ term: true });
    const { result } = renderHook(() => useStudyTermsController(controlled.port));
    const origin = trigger(),
      main = screen.getByRole('main'),
      [a, b] = bundle().terms.entries;
    act(() => result.current.openTerm(a.term_id, origin));
    act(() => result.current.close());
    await baseHistory();
    act(() => result.current.openTerm(b.term_id, origin));
    main.focus();
    act(() => result.current.returnFocus());
    expect(main).toHaveFocus();
    act(() => result.current.close());
    await baseHistory();
    origin.remove();
    act(() => result.current.returnFocus());
    expect(main).toHaveFocus();
    await act(async () => {
      for (const pending of controlled.termReads) pending.release();
    });
  });

  it('keeps the index unavailable when no catalog is connected', () => {
    const { result } = renderHook(() => useStudyTermsController(undefined));
    const origin = trigger();
    act(() => result.current.openTerm('not-an-id', origin));
    expect(result.current.indexStatus).toBe('unavailable');
    expect(result.current.terms).toHaveLength(0);
    expect(result.current.open).toBe(false);
    expect(result.current.view).toBeUndefined();
    expect(history.state).toEqual({ page: 'study' });
  });
});
