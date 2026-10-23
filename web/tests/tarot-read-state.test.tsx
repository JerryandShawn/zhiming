import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { operationNamespace, useAuth } from '../src/api/client';
import { ReadingPanel } from '../src/tarot/ReadingPanel';
import { useReadingVersions } from '../src/tarot/useReadingVersions';

function gate<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
const noop = () => {};
function Viewer({ id, activation = 0 }: { id: string | undefined; activation?: number }) {
  const { versions, versionsState, acceptVersions } = useReadingVersions(id, activation);
  if (!id) return <p>合成新问题</p>;
  return (
    <ReadingPanel
      key={id}
      drawId={id}
      versions={versions}
      versionsState={versionsState}
      readActivation={activation}
      onChange={acceptVersions}
      onBusy={noop}
    />
  );
}
const respond = (value: unknown) =>
  new Response(JSON.stringify(value), {
    headers: { 'Content-Type': 'application/json' },
  });
const saved = (id: string) => [{ id, version: 1, status: 'success', result: { answer: `${id}已保存的版本` } }];
const generate = () => screen.getByRole('button', { name: /^(生成 AI 解读|重新解读 · 不换牌)$/ });
const refresh = () => screen.getByRole('button', { name: '刷新解读记录' });
function requests(...gates: ReturnType<typeof gate<Response>>[]) {
  let n = 0;
  const fetcher = vi.fn((url: string, options?: RequestInit) => {
    if ((options?.method ?? 'GET') !== 'GET') throw new Error('Unexpected write in read-state test');
    if (!/^\/api\/tarot\/draws\/[^/]+\/readings$/.test(url)) throw new Error('Unexpected synthetic GET');
    const next = gates[n++];
    if (!next) throw new Error('Unexpected additional GET');
    return next.promise;
  });
  vi.stubGlobal('fetch', fetcher);
  return fetcher;
}
function assertGetOnly(fetcher: ReturnType<typeof requests>, count: number) {
  expect(fetcher).toHaveBeenCalledTimes(count);
  expect(fetcher.mock.calls.every(([, options]) => (options?.method ?? 'GET') === 'GET' && !options?.body)).toBe(true);
  expect(
    Object.keys(sessionStorage).some(
      (key) => key.startsWith('mingjing:tarot:reading:') || key.startsWith('mingjing-write:'),
    ),
  ).toBe(false);
}
beforeEach(() => {
  sessionStorage.clear();
  useAuth.getState().setToken(`synthetic-read-state-${crypto.randomUUID()}`);
});
afterEach(() => vi.unstubAllGlobals());

describe('fixed tarot versions are unknown until a successful GET', () => {
  it('keeps stopping a known pending run reachable when its initial versions read is pending or fails', async () => {
    const first = gate<Response>();
    const calls: { url: string; method: string }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, options?: RequestInit) => {
        const method = options?.method ?? 'GET';
        calls.push({ url, method });
        if (url === '/api/tarot/draws/a/readings' && method === 'GET') return first.promise;
        if (url === '/api/runs/synthetic-pending/cancel' && method === 'POST')
          return Promise.resolve(respond({ ok: true, run_id: 'synthetic-pending' }));
        if (url === '/api/runs/synthetic-pending' && method === 'GET')
          return Promise.resolve(respond({ id: 'synthetic-pending', status: 'cancelled' }));
        throw new Error('Unexpected synthetic stop request');
      }),
    );
    sessionStorage.setItem(
      `mingjing:tarot:reading:${operationNamespace()}:a`,
      JSON.stringify({
        request_id: 'synthetic-existing',
        supplement: '保留原背景',
        run_id: 'synthetic-pending',
      }),
    );
    render(<Viewer id="a" />);
    const retry = screen.getByRole('button', { name: '重试原解读 · 不换牌' });
    expect(retry).toBeDisabled();
    expect(screen.getByRole('button', { name: '停止解读' })).toBeEnabled();
    await act(async () => {
      first.reject(new Error('PRIVATE_READ_FAILED'));
    });
    expect(await screen.findByText('解读版本暂时无法读取。先刷新记录，再决定是否开始新解读。')).toBeVisible();
    expect(retry).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '停止解读' }));
    expect(await screen.findByText('这次解读已停止，牌阵保持不变。')).toBeVisible();
    expect(screen.getByRole('button', { name: '明确开始另一版解读' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: '停止解读' })).not.toBeInTheDocument();
    expect(calls).toEqual([
      { method: 'GET', url: '/api/tarot/draws/a/readings' },
      { method: 'POST', url: '/api/runs/synthetic-pending/cancel' },
      { method: 'GET', url: '/api/runs/synthetic-pending' },
    ]);
    expect(screen.getByRole('textbox', { name: '补充现实背景' })).toHaveValue('保留原背景');
    expect(document.body).not.toHaveTextContent('PRIVATE_READ_FAILED');
  });

  it('disables generation during the first read without discarding editable background', async () => {
    const first = gate<Response>(),
      fetcher = requests(first);
    render(<Viewer id="a" />);
    expect(await screen.findByText('正在读取已保存的解读版本…')).toBeVisible();
    expect(generate()).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: '补充现实背景' }), { target: { value: '保留合成背景' } });
    fireEvent.click(generate());
    expect(screen.getByRole('textbox', { name: '补充现实背景' })).toHaveValue('保留合成背景');
    assertGetOnly(fetcher, 1);
    await act(async () => {
      first.resolve(respond([]));
    });
    await waitFor(() => expect(generate()).toBeEnabled());
    assertGetOnly(fetcher, 1);
  });

  it('keeps generation disabled after failed initial read and unlocks only on GET retry success', async () => {
    const first = gate<Response>(),
      retry = gate<Response>(),
      fetcher = requests(first, retry);
    render(<Viewer id="a" />);
    fireEvent.change(screen.getByRole('textbox', { name: '补充现实背景' }), { target: { value: '背景不能丢' } });
    await act(async () => {
      first.reject(new Error('PRIVATE_FAILED_READ'));
    });
    expect(await screen.findByText('解读版本暂时无法读取。先刷新记录，再决定是否开始新解读。')).toBeVisible();
    expect(generate()).toBeDisabled();
    fireEvent.click(generate());
    fireEvent.click(refresh());
    expect(generate()).toBeDisabled();
    assertGetOnly(fetcher, 2);
    await act(async () => {
      retry.resolve(respond(saved('a')));
    });
    expect(await screen.findByText('a已保存的版本')).toBeVisible();
    expect(generate()).toHaveTextContent('重新解读 · 不换牌');
    expect(generate()).toBeEnabled();
    expect(screen.getByRole('textbox', { name: '补充现实背景' })).toHaveValue('背景不能丢');
    expect(document.body).not.toHaveTextContent('PRIVATE_FAILED_READ');
    assertGetOnly(fetcher, 2);
  });

  it.each([null, {}, 'not-a-list'])('does not treat a non-array successful body %j as empty', async (body) => {
    const first = gate<Response>(),
      fetcher = requests(first);
    render(<Viewer id="a" />);
    await act(async () => {
      first.resolve(respond(body));
    });
    expect(await screen.findByText('解读版本暂时无法读取。先刷新记录，再决定是否开始新解读。')).toBeVisible();
    expect(generate()).toBeDisabled();
    assertGetOnly(fetcher, 1);
  });

  it('a newer manual read can settle unknown state, and the older first failure cannot lock it again', async () => {
    const first = gate<Response>(),
      retry = gate<Response>(),
      fetcher = requests(first, retry);
    render(<Viewer id="a" />);
    fireEvent.click(refresh());
    await act(async () => {
      retry.resolve(respond(saved('latest')));
    });
    expect(await screen.findByText('latest已保存的版本')).toBeVisible();
    await act(async () => {
      first.reject(new Error('PRIVATE_OLD_ERROR'));
    });
    expect(generate()).toBeEnabled();
    expect(screen.queryByText('解读版本暂时无法读取。先刷新记录，再决定是否开始新解读。')).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent('PRIVATE_OLD_ERROR');
    assertGetOnly(fetcher, 2);
  });

  it('a corrected/new draw ID starts its own read and cannot reuse the old ready state', async () => {
    const first = gate<Response>(),
      corrected = gate<Response>(),
      fetcher = requests(first, corrected);
    const mounted = render(<Viewer id="old" />);
    await act(async () => {
      first.resolve(respond(saved('old')));
    });
    expect(await screen.findByText('old已保存的版本')).toBeVisible();
    mounted.rerender(<Viewer id="corrected" />);
    expect(generate()).toBeDisabled();
    expect(screen.queryByText('old已保存的版本')).not.toBeInTheDocument();
    await act(async () => {
      corrected.resolve(respond([]));
    });
    await waitFor(() => expect(generate()).toBeEnabled());
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      '/api/tarot/draws/old/readings',
      '/api/tarot/draws/corrected/readings',
    ]);
    assertGetOnly(fetcher, 2);
  });

  it('ignores the prior selected draw success without unlocking the new pending draw', async () => {
    const a = gate<Response>(),
      b = gate<Response>(),
      fetcher = requests(a, b);
    const mounted = render(<Viewer id="a" />);
    mounted.rerender(<Viewer id="b" />);
    await act(async () => {
      a.resolve(respond(saved('a')));
    });
    expect(generate()).toBeDisabled();
    expect(screen.queryByText('a已保存的版本')).not.toBeInTheDocument();
    await act(async () => {
      b.resolve(respond(saved('b')));
    });
    expect(await screen.findByText('b已保存的版本')).toBeVisible();
    assertGetOnly(fetcher, 2);
  });

  it('does not resurrect a confirmed snapshot when the same draw is reopened from new question', async () => {
    const first = gate<Response>(),
      reopened = gate<Response>(),
      fetcher = requests(first, reopened);
    const mounted = render(<Viewer id="a" />);
    await act(async () => {
      first.resolve(respond(saved('previous-a')));
    });
    expect(await screen.findByText('previous-a已保存的版本')).toBeVisible();
    mounted.rerender(<Viewer id={undefined} />);
    mounted.rerender(<Viewer id="a" />);
    expect(generate()).toBeDisabled();
    expect(screen.queryByText('previous-a已保存的版本')).not.toBeInTheDocument();
    await act(async () => {
      reopened.resolve(respond([]));
    });
    await waitFor(() => expect(generate()).toBeEnabled());
    assertGetOnly(fetcher, 2);
  });

  it('re-reads an explicitly reopened same ID without refetching unrelated rerenders', async () => {
    const first = gate<Response>(),
      reopened = gate<Response>(),
      fetcher = requests(first, reopened);
    const mounted = render(<Viewer id="a" activation={1} />);
    await act(async () => {
      first.resolve(respond(saved('previous-open')));
    });
    expect(await screen.findByText('previous-open已保存的版本')).toBeVisible();
    mounted.rerender(<Viewer id="a" activation={1} />);
    expect(generate()).toBeEnabled();
    assertGetOnly(fetcher, 1);
    mounted.rerender(<Viewer id="a" activation={2} />);
    expect(generate()).toBeDisabled();
    expect(screen.queryByText('previous-open已保存的版本')).not.toBeInTheDocument();
    await act(async () => {
      reopened.resolve(respond(saved('fresh-open')));
    });
    expect(await screen.findByText('fresh-open已保存的版本')).toBeVisible();
    expect(generate()).toBeEnabled();
    assertGetOnly(fetcher, 2);
  });

  it('keeps A2 loading after A1 -> B -> A2 when the first same-ID GET returns late', async () => {
    const a1 = gate<Response>(),
      b = gate<Response>(),
      a2 = gate<Response>(),
      fetcher = requests(a1, b, a2);
    const mounted = render(<Viewer id="a" />);
    mounted.rerender(<Viewer id="b" />);
    mounted.rerender(<Viewer id="a" />);
    await act(async () => {
      a1.resolve(respond(saved('a1-late')));
      b.resolve(respond(saved('b-late')));
    });
    expect(generate()).toBeDisabled();
    expect(screen.queryByText('a1-late已保存的版本')).not.toBeInTheDocument();
    expect(screen.queryByText('b-late已保存的版本')).not.toBeInTheDocument();
    await act(async () => {
      a2.resolve(respond(saved('a2-current')));
    });
    expect(await screen.findByText('a2-current已保存的版本')).toBeVisible();
    assertGetOnly(fetcher, 3);
  });

  it('a same-ID activation change prevents an old manual GET from publishing status or versions', async () => {
    const first = gate<Response>(),
      stale = gate<Response>(),
      fetcher = requests(first, stale);
    const changed = vi.fn(),
      busy = vi.fn();
    const oldVersion = { id: 'old', version: 1, status: 'success', answer: '旧激活已确认版本', appendix: '' };
    const newVersion = { ...oldVersion, id: 'new', version: 2, answer: '新激活已确认版本' };
    const mounted = render(
      <ReadingPanel drawId="a" readActivation={1} versions={[oldVersion]} onChange={changed} onBusy={busy} />,
    );
    fireEvent.click(refresh());
    await act(async () => {
      first.resolve(respond(saved('first-confirmed')));
    });
    expect(await screen.findByText('解读记录已刷新。')).toBeVisible();
    changed.mockClear();
    fireEvent.click(refresh());
    mounted.rerender(
      <ReadingPanel drawId="a" readActivation={2} versions={[newVersion]} onChange={changed} onBusy={busy} />,
    );
    expect(screen.queryByText('解读记录已刷新。')).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: '补充现实背景' }), {
      target: { value: '同牌阵背景继续保留' },
    });
    await act(async () => {
      stale.resolve(respond(saved('late-before-reopen')));
    });
    expect(changed).not.toHaveBeenCalled();
    expect(screen.queryByText('解读记录已刷新。')).not.toBeInTheDocument();
    expect(screen.getByText('新激活已确认版本')).toBeVisible();
    expect(screen.getByRole('textbox', { name: '补充现实背景' })).toHaveValue('同牌阵背景继续保留');
    assertGetOnly(fetcher, 2);
  });

  it('re-reads the same ID when namespace changes and ignores the old owner result', async () => {
    const a = gate<Response>(),
      b = gate<Response>(),
      fetcher = requests(a, b);
    render(<Viewer id="a" />);
    act(() => useAuth.getState().setToken(`new-owner-${crypto.randomUUID()}`));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    await act(async () => {
      a.resolve(respond(saved('private-old-owner')));
    });
    expect(generate()).toBeDisabled();
    expect(document.body).not.toHaveTextContent('private-old-owner');
    await act(async () => {
      b.resolve(respond(saved('new-owner')));
    });
    expect(await screen.findByText('new-owner已保存的版本')).toBeVisible();
    expect(generate()).toBeEnabled();
    assertGetOnly(fetcher, 2);
  });

  it('does not publish a pending first read after unmount', async () => {
    const first = gate<Response>(),
      fetcher = requests(first);
    const mounted = render(<Viewer id="a" />);
    mounted.unmount();
    await act(async () => {
      first.resolve(respond(saved('late')));
    });
    expect(screen.queryByText('late已保存的版本')).not.toBeInTheDocument();
    assertGetOnly(fetcher, 1);
  });
});
