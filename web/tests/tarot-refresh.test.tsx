import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ReadingPanel } from '../src/tarot/ReadingPanel';
import { operationNamespace, useAuth } from '../src/api/client';
import type { Reading } from '../src/tarot/public';

// Exercise the real loadReadings -> api -> public projection, not a mocked hook.
function gate<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function saved(id: string, answer: string, version = 1): Reading {
  return { id, version, status: 'success', answer, appendix: '' };
}
function response(...rows: Reading[]) {
  return new Response(
    JSON.stringify(
      rows.map((row) => ({
        id: row.id,
        version: row.version,
        status: row.status,
        result: { answer: row.answer, professional_appendix: row.appendix },
      })),
    ),
    { headers: { 'Content-Type': 'application/json' } },
  );
}
const refresh = () => fireEvent.click(screen.getByRole('button', { name: '刷新解读记录' }));
function transport(...requests: ReturnType<typeof gate<Response>>[]) {
  let index = 0;
  const fetcher = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method && init.method !== 'GET') throw new Error('Unexpected write in refresh test');
    if (!/^\/api\/tarot\/draws\/[^/]+\/readings$/.test(url)) throw new Error('Unexpected refresh endpoint');
    const request = requests[index++];
    if (!request) throw new Error('Unexpected additional refresh');
    return request.promise;
  });
  vi.stubGlobal('fetch', fetcher);
  return fetcher;
}
function assertReadsOnly(fetcher: ReturnType<typeof transport>, paths: string[]) {
  expect(fetcher.mock.calls.map(([url]) => url)).toEqual(paths);
  for (const [, options] of fetcher.mock.calls) {
    expect(options?.method ?? 'GET').toBe('GET');
    expect(options?.body).toBeUndefined();
    expect(options?.headers).toBeInstanceOf(Headers);
  }
}
beforeEach(() => {
  sessionStorage.clear();
  useAuth.getState().setToken(`synthetic-refresh-${crypto.randomUUID()}`);
});
afterEach(() => vi.unstubAllGlobals());

describe('manual fixed-tarot reading refresh ownership', () => {
  it('does not publish an old GET after the panel unmounts', async () => {
    const pending = gate<Response>(),
      fetcher = transport(pending),
      changed = vi.fn();
    const mounted = render(<ReadingPanel drawId="draw-a" versions={[]} onChange={changed} onBusy={vi.fn()} />);
    refresh();
    mounted.unmount();
    await act(async () => {
      pending.resolve(response(saved('old', '卸载后的旧解读')));
      await pending.promise;
    });
    expect(changed).not.toHaveBeenCalled();
    assertReadsOnly(fetcher, ['/api/tarot/draws/draw-a/readings']);
  });

  it('keeps the newly opened fixed draw when the prior keyed panel finishes late', async () => {
    const pending = gate<Response>(),
      fetcher = transport(pending),
      changed = vi.fn(),
      busy = vi.fn();
    const old = saved('a', 'A牌阵已确认版本'),
      current = saved('b', 'B牌阵已确认版本');
    const mounted = render(
      <ReadingPanel key="draw-a" drawId="draw-a" versions={[old]} onChange={changed} onBusy={busy} />,
    );
    refresh();
    expect(busy.mock.calls.every(([value]) => value === false)).toBe(true);
    mounted.rerender(
      <ReadingPanel key="draw-b" drawId="draw-b" versions={[current]} onChange={changed} onBusy={busy} />,
    );
    await act(async () => {
      pending.resolve(response(saved('a-late', 'A牌阵迟到版本')));
      await pending.promise;
    });
    expect(changed).not.toHaveBeenCalled();
    expect(screen.getByText(current.answer)).toBeVisible();
    expect(screen.queryByText('A牌阵迟到版本')).not.toBeInTheDocument();
    assertReadsOnly(fetcher, ['/api/tarot/draws/draw-a/readings']);
  });

  it('also invalidates a prior read when drawId changes without relying on a key', async () => {
    const pending = gate<Response>(),
      fetcher = transport(pending),
      changed = vi.fn(),
      busy = vi.fn();
    const mounted = render(<ReadingPanel drawId="draw-a" versions={[]} onChange={changed} onBusy={busy} />);
    refresh();
    mounted.rerender(
      <ReadingPanel drawId="draw-b" versions={[saved('b', 'B牌阵仍在')]} onChange={changed} onBusy={busy} />,
    );
    await act(async () => {
      pending.resolve(response(saved('a-late', '旧A版本')));
      await pending.promise;
    });
    expect(changed).not.toHaveBeenCalled();
    expect(screen.getByText('B牌阵仍在')).toBeVisible();
    assertReadsOnly(fetcher, ['/api/tarot/draws/draw-a/readings']);
  });

  it('applies only the newest refresh when two GETs complete in reverse order', async () => {
    const first = gate<Response>(),
      second = gate<Response>(),
      fetcher = transport(first, second),
      changed = vi.fn();
    render(<ReadingPanel drawId="draw-a" versions={[]} onChange={changed} onBusy={vi.fn()} />);
    refresh();
    refresh();
    const newest = saved('latest', '第二次刷新的最新版本', 2);
    await act(async () => {
      second.resolve(response(newest));
      await second.promise;
    });
    await waitFor(() => expect(changed).toHaveBeenCalledWith([newest]));
    await act(async () => {
      first.resolve(response(saved('stale', '第一次刷新的旧版本')));
      await first.promise;
    });
    expect(changed).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status')).toHaveTextContent('解读记录已刷新。');
    assertReadsOnly(fetcher, Array(2).fill('/api/tarot/draws/draw-a/readings'));
  });

  it('does not let an old failed GET replace a newer successful refresh status', async () => {
    const first = gate<Response>(),
      second = gate<Response>(),
      fetcher = transport(first, second),
      changed = vi.fn();
    render(<ReadingPanel drawId="draw-a" versions={[]} onChange={changed} onBusy={vi.fn()} />);
    refresh();
    refresh();
    await act(async () => {
      second.resolve(response(saved('latest', '已刷新的版本')));
      await second.promise;
    });
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
    await act(async () => {
      first.reject(new Error('PRIVATE_OLD_NETWORK_DETAIL'));
    });
    expect(screen.getByRole('status')).toHaveTextContent('解读记录已刷新。');
    expect(screen.queryByText('解读记录暂时无法读取。')).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent('PRIVATE_OLD_NETWORK_DETAIL');
    assertReadsOnly(fetcher, Array(2).fill('/api/tarot/draws/draw-a/readings'));
  });

  it('ignores the old namespace rejection after a new owner refresh succeeds', async () => {
    const first = gate<Response>(),
      second = gate<Response>(),
      fetcher = transport(first, second),
      changed = vi.fn();
    render(<ReadingPanel drawId="draw-a" versions={[]} onChange={changed} onBusy={vi.fn()} />);
    const oldNamespace = operationNamespace();
    refresh();
    act(() => useAuth.getState().setToken(`new-owner-${crypto.randomUUID()}`));
    expect(operationNamespace()).not.toBe(oldNamespace);
    refresh();
    const fresh = saved('owner-b', '新会话自己的版本');
    await act(async () => {
      second.resolve(response(fresh));
      await second.promise;
    });
    await waitFor(() => expect(changed).toHaveBeenCalledWith([fresh]));
    await act(async () => {
      first.resolve(response(saved('owner-a', '旧会话迟到版本')));
      await first.promise;
    });
    expect(changed).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status')).toHaveTextContent('解读记录已刷新。');
    expect(document.body).not.toHaveTextContent('旧会话迟到版本');
    const tokens = fetcher.mock.calls.map(([, options]) => new Headers(options?.headers).get('X-Token'));
    expect(tokens[0]).not.toBe(tokens[1]);
    assertReadsOnly(fetcher, Array(2).fill('/api/tarot/draws/draw-a/readings'));
  });

  it('keeps confirmed versions on failure, then clears failure only after a successful GET retry', async () => {
    const first = gate<Response>(),
      second = gate<Response>(),
      fetcher = transport(first, second),
      changed = vi.fn();
    const confirmed = saved('saved', '已经确认的旧版本');
    render(<ReadingPanel drawId="draw-a" versions={[confirmed]} onChange={changed} onBusy={vi.fn()} />);
    refresh();
    await act(async () => {
      first.reject(new Error('PRIVATE_RESPONSE_DETAIL'));
    });
    expect(await screen.findByText('解读记录暂时无法读取。')).toBeVisible();
    expect(screen.getByText(confirmed.answer)).toBeVisible();
    expect(changed).not.toHaveBeenCalled();
    expect(document.body).not.toHaveTextContent('PRIVATE_RESPONSE_DETAIL');
    refresh();
    const newest = saved('saved-2', '重新刷新的已保存版本', 2);
    await act(async () => {
      second.resolve(response(confirmed, newest));
      await second.promise;
    });
    await waitFor(() => expect(changed).toHaveBeenCalledWith([confirmed, newest]));
    expect(screen.getByRole('status')).toHaveTextContent('解读记录已刷新。');
    expect(screen.queryByText('解读记录暂时无法读取。')).not.toBeInTheDocument();
    expect(
      Object.keys(sessionStorage).some(
        (key) => key.startsWith('mingjing:tarot:reading:') || key.startsWith('mingjing-write:'),
      ),
    ).toBe(false);
    assertReadsOnly(fetcher, Array(2).fill('/api/tarot/draws/draw-a/readings'));
  });
  it('cannot let a manual refresh replace a later confirmed generated version', async () => {
    const oldRead = gate<Response>(),
      changed = vi.fn();
    const newest = saved('reading-new', '本次保存的新版本', 2);
    let reads = 0;
    const fetcher = vi.fn((url: string, init?: RequestInit): Promise<Response> => {
      if (url.startsWith('/api/runs/reading%3A')) return Promise.resolve(new Response('{}', { status: 404 }));
      if (url === '/api/tarot/draws/draw-a/readings' && init?.method === 'POST')
        return Promise.resolve(
          new Response(
            'data: ' +
              JSON.stringify({ type: 'started', run_id: 'new-run', reading_id: newest.id }) +
              '\n\n' +
              'data: {"type":"result"}\n\ndata: [DONE]\n\n',
            { headers: { 'Content-Type': 'text/event-stream' } },
          ),
        );
      if (url === '/api/tarot/draws/draw-a/readings')
        return ++reads === 1 ? oldRead.promise : Promise.resolve(response(newest));
      throw new Error('Unexpected synthetic reading route');
    });
    vi.stubGlobal('fetch', fetcher);
    render(
      <ReadingPanel drawId="draw-a" versions={[saved('old', '原来保存的版本')]} onChange={changed} onBusy={vi.fn()} />,
    );
    refresh();
    fireEvent.click(screen.getByRole('button', { name: '重新解读 · 不换牌' }));
    await waitFor(() => expect(changed).toHaveBeenCalledWith([newest]));
    await act(async () => {
      oldRead.resolve(response(saved('stale', '生成前迟到的版本')));
      await oldRead.promise;
    });
    expect(changed).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status')).toHaveTextContent('解读已保存，固定牌阵没有变化。');
    expect(fetcher.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
  });
});
