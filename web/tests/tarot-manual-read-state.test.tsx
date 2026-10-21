import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Tarot from '../src/live/Tarot';
import { useAuth } from '../src/api/client';

const card = {
  card_id: 'major-17',
  name: '星星',
  upright: '先核对现实条件',
  reversed: '放慢节奏',
  misreading: '不是保证',
  question: '下一步怎么做？',
};
const spread = { id: 'focus1', name: '关注点', positions: ['现在'] };
const draw = (id: string, ready: boolean) => ({
  id,
  question: '合成实体牌安排',
  case_id: 'synthetic-case',
  draw_source: 'manual',
  status: ready ? 'ready' : 'pending_reveal',
  reversals: true,
  spread_id: spread.id,
  spread,
  created_at: '2026-10-21T00:00:00Z',
  revision: id === 'old' ? 1 : 2,
  cards: [{ position: 1, label: '现在', back_id: 'opaque', revealed: ready, card, orientation: 'upright' }],
  backs: [],
  options: {},
  previous_draw_id: id === 'old' ? '' : 'old',
});
const respond = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const oldReading = { id: 'old-reading', version: 1, status: 'success', result: { answer: '旧录入的已保存版本' } };
beforeEach(() => {
  sessionStorage.clear();
  useAuth.getState().setToken(`synthetic-manual-state-${crypto.randomUUID()}`);
  window.history.replaceState(null, '', '#/tarot?draw=old');
});
afterEach(() => vi.unstubAllGlobals());

describe('manual fixed draw correction requires its own readings GET', () => {
  it('a same-ID history open fetches versions again rather than reviving the prior ready snapshot', async () => {
    let finishReopen!: (response: Response) => void;
    const reopened = new Promise<Response>((resolve) => {
      finishReopen = resolve;
    });
    let reads = 0;
    const fetcher = vi.fn(async (url: string, options?: RequestInit): Promise<Response> => {
      if ((options?.method ?? 'GET') !== 'GET') throw new Error('Unexpected write in explicit reopen');
      if (url === '/api/tarot/deck') return respond({ cards: [card], spreads: [spread], reversals: true });
      if (url === '/api/tarot/draws') return respond([draw('old', true)]);
      if (url === '/api/cases') return respond([]);
      if (url === '/api/tarot/draws/old') return respond(draw('old', true));
      if (url === '/api/tarot/draws/old/readings') return ++reads === 1 ? respond([oldReading]) : reopened;
      throw new Error('Unexpected synthetic explicit-open GET');
    });
    vi.stubGlobal('fetch', fetcher);
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Tarot />
      </QueryClientProvider>,
    );
    expect(await screen.findByText('旧录入的已保存版本')).toBeVisible();
    const history = document.querySelector('.tarot-history');
    expect(history).not.toBeNull();
    fireEvent.click(within(history as HTMLElement).getByRole('button', { name: /合成实体牌安排/ }));
    await waitFor(() => expect(reads).toBe(2));
    expect(screen.getByRole('button', { name: '生成 AI 解读' })).toBeDisabled();
    expect(screen.queryByText('旧录入的已保存版本')).not.toBeInTheDocument();
    await act(async () => {
      finishReopen(respond([{ ...oldReading, id: 'fresh', version: 2, result: { answer: '重新打开后核实的版本' } }]));
    });
    expect(await screen.findByText('重新打开后核实的版本')).toBeVisible();
    expect(screen.getByRole('button', { name: '重新解读 · 不换牌' })).toBeEnabled();
    expect(fetcher.mock.calls.filter(([url]) => url === '/api/tarot/draws/old')).toHaveLength(2);
    expect(fetcher.mock.calls.every(([, options]) => (options?.method ?? 'GET') === 'GET')).toBe(true);
  });

  it('does not reuse old ready versions after the correction receipt returns a new ID', async () => {
    let rejectCorrected!: (reason?: unknown) => void;
    const correctedRead = new Promise<Response>((_, reject) => {
      rejectCorrected = reject;
    });
    let correctedReadCount = 0;
    const fetcher = vi.fn((url: string, options?: RequestInit): Promise<Response> => {
      const method = options?.method ?? 'GET';
      if (url === '/api/tarot/deck')
        return Promise.resolve(respond({ cards: [card], spreads: [spread], reversals: true }));
      if (url === '/api/tarot/draws') return Promise.resolve(respond([draw('old', true)]));
      if (url === '/api/cases') return Promise.resolve(respond([]));
      if (url === '/api/tarot/draws/old' && method === 'GET') return Promise.resolve(respond(draw('old', true)));
      if (url === '/api/tarot/draws/old/readings' && method === 'GET') return Promise.resolve(respond([oldReading]));
      if (url === '/api/tarot/draws/old/manual' && method === 'PATCH')
        return Promise.resolve(respond(draw('corrected', false)));
      if (url === '/api/tarot/draws/corrected/reveal' && method === 'POST')
        return Promise.resolve(respond(draw('corrected', true)));
      if (url === '/api/tarot/draws/corrected/readings' && method === 'GET')
        return ++correctedReadCount === 1 ? correctedRead : Promise.resolve(respond([]));
      throw new Error('Unexpected synthetic manual transport');
    });
    vi.stubGlobal('fetch', fetcher);
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Tarot />
      </QueryClientProvider>,
    );
    expect(await screen.findByText('旧录入的已保存版本')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '更正实体牌录入' }));
    fireEvent.change(screen.getByRole('textbox', { name: '更正原因' }), { target: { value: '合成录入修正' } });
    fireEvent.click(screen.getByRole('button', { name: '保存录入更正' }));
    await waitFor(() => expect(correctedReadCount).toBe(1));
    expect(screen.queryByText('旧录入的已保存版本')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: /^(全部揭开|全部揭开 · 跳过动画)$/ })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /^(全部揭开|全部揭开 · 跳过动画)$/ }));
    expect(await screen.findByText('正在读取已保存的解读版本…')).toBeVisible();
    expect(screen.getByRole('button', { name: '生成 AI 解读' })).toBeDisabled();
    await act(async () => {
      rejectCorrected(new Error('PRIVATE_MANUAL_READ_FAILURE'));
    });
    expect(await screen.findByText('解读版本暂时无法读取。先刷新记录，再决定是否开始新解读。')).toBeVisible();
    expect(screen.getByRole('button', { name: '生成 AI 解读' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '刷新解读记录' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '生成 AI 解读' })).toBeEnabled());
    expect(correctedReadCount).toBe(2);
    expect(
      fetcher.mock.calls
        .filter(([, options]) => (options?.method ?? 'GET') !== 'GET')
        .map(([url, options]) => [options?.method, url]),
    ).toEqual([
      ['PATCH', '/api/tarot/draws/old/manual'],
      ['POST', '/api/tarot/draws/corrected/reveal'],
    ]);
    expect(document.body).not.toHaveTextContent('PRIVATE_MANUAL_READ_FAILURE');
  });
});
