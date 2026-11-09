import { StrictMode } from 'react';
import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import StudyWorkspace from '../src/study/StudyWorkspace';
import { useStudyCatalog } from '../src/study/useStudyCatalog';
import { controlledStudySession, newStudyPort } from './study-ui-test-fixtures';

describe('study catalog ownership and persistent conversation children', () => {
  it('creates a fresh session during StrictMode replay and disposes a late first activation without remounting the draft', async () => {
    const sessions: ReturnType<typeof controlledStudySession>[] = [];
    const createSession = () => {
      const next = controlledStudySession();
      sessions.push(next);
      return next.session;
    };
    const { container, unmount } = render(
      <StrictMode>
        <StudyWorkspace createSession={createSession}>
          <textarea aria-label="保留的对话草稿" defaultValue="合成草稿" />
        </StudyWorkspace>
      </StrictMode>,
    );
    const draft = screen.getByRole('textbox', { name: '保留的对话草稿' });
    await userEvent.type(draft, '，继续编辑');
    await waitFor(() => expect(sessions).toHaveLength(2));
    expect(sessions[0].session.dispose).toHaveBeenCalledTimes(1);
    expect(sessions[0].requests[0].signal?.aborted).toBe(true);
    const retired = newStudyPort(),
      disposeRetired = vi.spyOn(retired, 'dispose');
    await act(async () => sessions[0].requests[0].resolve(retired));
    expect(disposeRetired).toHaveBeenCalledTimes(1);
    expect(container.querySelector('[data-runtime="study-workspace"]')).toHaveAttribute('data-study-state', 'loading');
    const current = newStudyPort();
    await act(async () => sessions[1].requests[0].resolve(current));
    await waitFor(() =>
      expect(container.querySelector('[data-runtime="study-workspace"]')).toHaveAttribute('data-study-state', 'ready'),
    );
    expect(screen.getByRole('textbox', { name: '保留的对话草稿' })).toBe(draft);
    expect(draft).toHaveValue('合成草稿，继续编辑');
    unmount();
    expect(sessions[1].session.dispose).toHaveBeenCalledTimes(1);
  });

  it('retains draft DOM, unsaved text and dictionary search across a failed reload and successful retry', async () => {
    const controlled = controlledStudySession();
    const createSession = () => controlled.session;
    const { container } = render(
      <StudyWorkspace createSession={createSession}>
        <textarea aria-label="保留的对话草稿" />
      </StudyWorkspace>,
    );
    const draft = screen.getByRole('textbox', { name: '保留的对话草稿' });
    await userEvent.type(draft, '只留在当前界面的合成草稿');
    await act(async () => controlled.requests[0].resolve(newStudyPort()));
    await userEvent.click(screen.getByRole('button', { name: '术语词典' }));
    const search = screen.getByRole('searchbox', { name: '搜索术语' });
    await userEvent.type(search, '日主');
    await screen.findByRole('button', { name: '查看术语：日主 八字 · 日元、日干' });
    fireEvent.click(screen.getByText('研习资料的口径与限制', { selector: 'summary' }));
    await userEvent.click(screen.getByRole('button', { name: '重新载入研习资料' }));
    expect(container.querySelector('[data-runtime="study-workspace"]')).toHaveAttribute('data-study-state', 'loading');
    expect(screen.queryByRole('button', { name: '查看术语：日主 八字 · 日元、日干' })).not.toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: '搜索术语' })).toBe(search);
    expect(search).toHaveValue('日主');
    expect(draft.isConnected).toBe(true);
    expect(draft).toHaveValue('只留在当前界面的合成草稿');
    await act(async () => controlled.requests[1].reject(new Error('synthetic failure')));
    expect(screen.getByRole('alert')).toHaveTextContent('研习资料没有载入');
    expect(search).toHaveValue('日主');
    await userEvent.click(screen.getByRole('button', { name: '重新载入研习资料' }));
    await act(async () => controlled.requests[2].resolve(newStudyPort()));
    await screen.findByRole('button', { name: '查看术语：日主 八字 · 日元、日干' });
    expect(screen.getByRole('searchbox', { name: '搜索术语' })).toBe(search);
    await userEvent.click(screen.getByRole('button', { name: '对话' }));
    expect(screen.getByRole('textbox', { name: '保留的对话草稿' })).toBe(draft);
    expect(draft).toHaveValue('只留在当前界面的合成草稿');
  });

  it('treats factory A→B→A as three activations, including late success from the first identical factory', async () => {
    const aSessions: ReturnType<typeof controlledStudySession>[] = [];
    const b = controlledStudySession();
    const factoryA = () => {
      const session = controlledStudySession();
      aSessions.push(session);
      return session.session;
    };
    const factoryB = () => b.session;
    const { result, rerender, unmount } = renderHook(({ factory }) => useStudyCatalog(factory), {
      initialProps: { factory: factoryA },
    });
    expect(aSessions).toHaveLength(1);
    const a1 = aSessions[0];
    rerender({ factory: factoryB });
    expect(result.current.view.status).toBe('loading');
    rerender({ factory: factoryA });
    expect(result.current.view.status).toBe('loading');
    expect(aSessions).toHaveLength(2);
    const a2 = aSessions[1],
      current = newStudyPort(),
      obsoleteA = newStudyPort(),
      obsoleteB = newStudyPort();
    const disposeA = vi.spyOn(obsoleteA, 'dispose'),
      disposeB = vi.spyOn(obsoleteB, 'dispose');
    await act(async () => a2.requests[0].resolve(current));
    expect(result.current.view).toMatchObject({ status: 'ready', port: current });
    await act(async () => {
      a1.requests[0].resolve(obsoleteA);
      b.requests[0].resolve(obsoleteB);
    });
    expect(result.current.view).toMatchObject({ status: 'ready', port: current });
    expect(disposeA).toHaveBeenCalledTimes(1);
    expect(disposeB).toHaveBeenCalledTimes(1);
    expect(a1.requests[0].signal?.aborted).toBe(true);
    expect(b.requests[0].signal?.aborted).toBe(true);
    unmount();
  });

  it('ignores a retired failure while the current catalog is ready, and disposes a result delivered after unmount', async () => {
    const first = controlledStudySession(),
      second = controlledStudySession();
    const factoryA = () => first.session,
      factoryB = () => second.session;
    const { result, rerender, unmount } = renderHook(({ factory }) => useStudyCatalog(factory), {
      initialProps: { factory: factoryA },
    });
    rerender({ factory: factoryB });
    const current = newStudyPort();
    await act(async () => second.requests[0].resolve(current));
    await act(async () => first.requests[0].reject(new Error('retired synthetic failure')));
    expect(result.current.view).toMatchObject({ status: 'ready', port: current });
    act(() => result.current.reload());
    const late = newStudyPort(),
      disposeLate = vi.spyOn(late, 'dispose');
    unmount();
    await act(async () => second.requests[1].resolve(late));
    expect(disposeLate).toHaveBeenCalledTimes(1);
    expect(second.requests[1].signal?.aborted).toBe(true);
  });

  it('refuses a returned port whose metadata was already revoked and recovers with a fresh port', async () => {
    const controlled = controlledStudySession(),
      factory = () => controlled.session;
    const { result } = renderHook(() => useStudyCatalog(factory));
    const revoked = newStudyPort();
    revoked.dispose();
    await act(async () => controlled.requests[0].resolve(revoked));
    expect(result.current.view.status).toBe('error');
    act(() => result.current.reload());
    const fresh = newStudyPort();
    await act(async () => controlled.requests[1].resolve(fresh));
    expect(result.current.view).toMatchObject({ status: 'ready', port: fresh });
  });
});
