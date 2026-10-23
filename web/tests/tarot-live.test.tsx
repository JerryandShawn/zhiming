import { act, render as testingRender, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement } from 'react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Tarot from '../src/live/Tarot';
import { useAuth } from '../src/api/client';
import { createDraw, mutateDraw } from '../src/tarot/draws';
import { draw, reading } from '../src/tarot/public';
import { pendingReading, requestReading } from '../src/tarot/readings';
import { ServerSpread } from '../src/tarot/ServerSpread';
import { QuestionForm } from '../src/tarot/QuestionForm';
import { ReadingPanel } from '../src/tarot/ReadingPanel';
import { DrawPanel } from '../src/tarot/DrawPanel';

function render(ui: ReactElement) {
  return testingRender(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {ui}
    </QueryClientProvider>,
  );
}

const publicCard = {
  card_id: 'major-17',
  name: '星星',
  upright: '先核对现实条件',
  reversed: '放慢节奏',
  misreading: '不是保证',
  question: '下一步怎么做？',
};
const rawDraw = {
  id: 'saved-draw',
  question: '如何安排学习？',
  case_id: 'synthetic-case',
  draw_source: 'auto',
  status: 'pending_reveal',
  reversals: true,
  spread_id: 'focus1',
  spread: { id: 'focus1', name: '关注点', positions: ['现在'] },
  created_at: '2026-10-18T01:00:00Z',
  revision: 1,
  cards: [{ position: 1, label: '现在', back_id: 'opaque-A', revealed: false }],
  backs: [],
  options: { A: '学习', B: '休息' },
  private_deck: ['PRIVATE_ORDER'],
  context_snapshot: { birth: 'PRIVATE_BIRTH' },
};
const completed = {
  id: 'reading-1',
  version: 1,
  status: 'success',
  result: {
    answer: '第一版：先核对现实安排。',
    professional_appendix: '象征性反思。',
    meta: { profile: 'PRIVATE_PROFILE' },
  },
};
const respond = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const events = (values: unknown[]) =>
  new Response(values.map((value) => `data: ${JSON.stringify(value)}\n\n`).join('') + 'data: [DONE]\n\n', {
    headers: { 'Content-Type': 'text/event-stream' },
  });
beforeEach(() => {
  sessionStorage.clear();
  useAuth.getState().setToken(`synthetic-${crypto.randomUUID()}`);
  window.history.replaceState(null, '', '#/tarot');
});

describe('live tarot viewer and fixed-card contracts', () => {
  it('waits for initial login before loading and resumes the page after the first login', async () => {
    useAuth.getState().setToken('');
    const fetcher = vi.fn(async (url: string) =>
      url === '/api/tarot/deck' ? respond({ cards: [publicCard], spreads: [rawDraw.spread] }) : respond([]),
    );
    vi.stubGlobal('fetch', fetcher);
    render(<Tarot />);
    expect(fetcher).not.toHaveBeenCalled();
    act(() => useAuth.getState().setToken('synthetic-login'));
    expect(await screen.findByRole('form', { name: '塔罗提问' })).toBeVisible();
    expect(fetcher).toHaveBeenCalledTimes(3);
  });
  it('carries a linked case from the URL into the new draw request', async () => {
    const user = userEvent.setup(),
      submit = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => respond([{ id: 'linked-case', title: '合成学习事项' }])),
    );
    window.history.replaceState(null, '', '#/tarot?case=linked-case');
    render(
      <QuestionForm
        deck={{ cards: [publicCard], spreads: [{ ...rawDraw.spread, id: 'reflect3' }], reversals: true }}
        busy={false}
        onSubmit={submit}
      />,
    );
    await user.type(screen.getByRole('textbox', { name: '想问什么？' }), '如何安排学习？');
    await user.click(screen.getByRole('button', { name: '开始梳理' }));
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({ case_id: 'linked-case', explicit_new: false }));
  });
  it('does not store or show old reading events after the owner changes', async () => {
    let finishStream!: (value: Response) => void;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        url.startsWith('/api/runs/')
          ? respond({}, 404)
          : new Promise<Response>((resolve) => {
              finishStream = resolve;
            }),
      ),
    );
    const result = requestReading('saved-draw', '', new AbortController().signal, vi.fn());
    await waitFor(() => expect(finishStream).toBeTypeOf('function'));
    useAuth.getState().setToken(`changed-owner-${crypto.randomUUID()}`);
    finishStream(events([{ type: 'started', run_id: 'old-run', reading_id: 'old-reading' }]));
    await expect(result).rejects.toMatchObject({ name: 'AbortError' });
    expect(pendingReading('saved-draw')).toBeUndefined();
  });
  it('keeps a failed cancellation retry available after the reading stream has ended', async () => {
    const user = userEvent.setup();
    let first = true;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.startsWith('/api/runs/reading%3A')) return respond({}, 404);
        if (init?.method === 'POST' && url.endsWith('/readings'))
          return events([{ type: 'started', run_id: 'pending-run', reading_id: 'reading-1' }, { type: 'error' }]);
        if (url.endsWith('/readings')) return respond([]);
        throw new Error('unexpected');
      }),
    );
    await expect(requestReading('saved-draw', '', new AbortController().signal, vi.fn())).rejects.toThrow();
    const current = pendingReading('saved-draw');
    const key = Object.keys(sessionStorage).find((value) => value.startsWith('mingjing:tarot:reading:'))!;
    sessionStorage.setItem(key, JSON.stringify({ ...current, cancel_requested: true }));
    const cancelBodies: Record<string, unknown>[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith('/cancel')) {
          cancelBodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
          if (first) {
            first = false;
            throw new Error('lost cancel receipt');
          }
          return respond({ ok: true, run_id: 'pending-run' });
        }
        return respond({ status: 'cancelled' });
      }),
    );
    render(<ReadingPanel drawId="saved-draw" versions={[]} onChange={vi.fn()} onBusy={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: '重试停止解读' }));
    expect(await screen.findByText('停止未确认，请重试停止或刷新记录；牌阵保持不变。')).toBeVisible();
    await user.click(screen.getByRole('button', { name: '重试停止解读' }));
    expect(await screen.findByText('这次解读已停止，牌阵保持不变。')).toBeVisible();
    expect(cancelBodies[0].request_id).toBe(cancelBodies[1].request_id);
    expect(screen.getByRole('button', { name: '明确开始另一版解读' })).toBeVisible();
  });
  it('restores frozen select and physical correction retries after refresh', async () => {
    const user = userEvent.setup(),
      mutate = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('synthetic lost receipt');
      }),
    );
    await expect(mutateDraw(draw(rawDraw), 'select', { back_id: 'opaque-A' })).rejects.toThrow();
    const correction = { cards: [{ card_id: 'major-17', orientation: 'upright' }], reason: '合成实体牌录入纠错' };
    await expect(mutateDraw(draw(rawDraw), 'manual', correction)).rejects.toThrow();
    render(
      <DrawPanel
        draw={draw({ ...rawDraw, draw_source: 'manual' })}
        deck={{ cards: [publicCard], spreads: [rawDraw.spread], reversals: true }}
        busy={false}
        versions={[]}
        onChangeVersions={vi.fn()}
        mutate={mutate}
        newRound={vi.fn()}
        onReadingBusy={vi.fn()}
      />,
    );
    await user.click(screen.getByRole('button', { name: '重试未确认的选牌' }));
    expect(mutate).toHaveBeenCalledWith('select', { back_id: 'opaque-A' });
    expect(screen.getByRole('textbox', { name: '更正原因' })).toHaveValue(correction.reason);
    await user.click(screen.getByRole('button', { name: '重试未确认的实体牌更正' }));
    expect(mutate).toHaveBeenCalledWith('manual', correction);
  });
  it('projects only public visible fields and discards forged pre-reveal identities', () => {
    const projected = draw({
      ...rawDraw,
      cards: [
        { ...rawDraw.cards[0], card: publicCard, card_id: 'major-17', orientation: 'upright', raw_profile: 'PRIVATE' },
      ],
    });
    expect(projected.cards[0].card).toBeUndefined();
    expect(JSON.stringify(projected)).not.toMatch(/PRIVATE|private_deck|context_snapshot|card_id/);
    expect(reading(completed)).toEqual({
      id: 'reading-1',
      version: 1,
      status: 'success',
      answer: completed.result.answer,
      appendix: completed.result.professional_appendix,
    });
  });
  it('sends opaque back IDs, supports arrow navigation, and never exposes a pre-reveal face', async () => {
    const user = userEvent.setup(),
      mutate = vi.fn();
    render(
      <ServerSpread
        draw={draw({
          ...rawDraw,
          draw_source: 'pick',
          cards: [],
          backs: [
            { back_id: 'opaque-A', selected: false },
            { back_id: 'opaque-Z', selected: false },
          ],
        })}
        busy={false}
        mutate={mutate}
      />,
    );
    const first = screen.getByRole('button', { name: '第1张牌背' });
    first.focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('button', { name: '第2张牌背' })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(mutate).toHaveBeenCalledWith('select', { back_id: 'opaque-Z' });
    expect(document.querySelectorAll('img[src="/static/tarot/back.svg"]')).toHaveLength(2);
    expect(document.body).not.toHaveTextContent('星星');
  });
  it('keeps stable create and mutation IDs after ambiguous network failure', async () => {
    const payload = { question: rawDraw.question, draw_source: 'auto' },
      sent: Record<string, unknown>[] = [];
    let fail = true;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init: RequestInit) => {
        sent.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        if (fail) {
          fail = false;
          throw new Error('synthetic disconnect');
        }
        return respond({ draw: rawDraw });
      }),
    );
    await expect(createDraw(payload)).rejects.toThrow();
    await createDraw(payload);
    expect(sent[0].idempotency_key).toBe(sent[1].idempotency_key);
    expect(sent[0].request_id).toBe(sent[0].idempotency_key);
    const commandBodies: Record<string, unknown>[] = [];
    fail = true;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init: RequestInit) => {
        commandBodies.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        if (fail) {
          fail = false;
          throw new Error('synthetic disconnect');
        }
        return respond(rawDraw);
      }),
    );
    await expect(mutateDraw(draw(rawDraw), 'reveal', { position: 1 })).rejects.toThrow();
    await mutateDraw(draw(rawDraw), 'reveal', { position: 1 });
    expect(commandBodies[0].request_id).toBe(commandBodies[1].request_id);
    await mutateDraw(draw(rawDraw), 'reveal', { position: 1 });
    expect(commandBodies[2].request_id).not.toBe(commandBodies[1].request_id);
  });
  it.each(['cancel', 'manual'] as const)('replays ambiguous %s once with its original key', async (action) => {
    const sent: Record<string, unknown>[] = [];
    let fail = true;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init: RequestInit) => {
        sent.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        if (fail) {
          fail = false;
          throw new Error('synthetic lost receipt');
        }
        return respond(
          action === 'manual'
            ? { ...rawDraw, id: 'corrected-draw', previous_draw_id: rawDraw.id, revision: 2 }
            : { ...rawDraw, status: 'cancelled' },
        );
      }),
    );
    const payload =
      action === 'manual' ? { cards: [{ card_id: 'major-17', orientation: 'upright' }], reason: '合成录入修正' } : {};
    await expect(mutateDraw(draw(rawDraw), action, payload)).rejects.toThrow();
    const response = await mutateDraw(draw(rawDraw), action, payload);
    const idKey = action === 'manual' ? 'idempotency_key' : 'request_id';
    expect(sent[0][idKey]).toBe(sent[1][idKey]);
    if (action === 'manual') expect(response.previous_draw_id).toBe(rawDraw.id);
    else expect(response.status).toBe('cancelled');
  });
  it('reveals all without adding flip animation under reduced motion', async () => {
    const user = userEvent.setup(),
      mutate = vi.fn();
    vi.mocked(window.matchMedia).mockImplementation((query) => ({
      matches: query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    render(<ServerSpread draw={draw(rawDraw)} busy={false} mutate={mutate} />);
    await user.click(screen.getByRole('button', { name: '全部揭开 · 跳过动画' }));
    expect(mutate).toHaveBeenCalledWith('reveal', {});
    expect(document.querySelector('.revealed,.flip-front')).toBeNull();
  });
  it('restores a deep-linked draw, freezes A/B, reveals only from a server receipt, and views saved versions', async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, '', '#/tarot?draw=saved-draw');
    let revealed = false;
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/tarot/deck') return respond({ cards: [publicCard], spreads: [rawDraw.spread] });
      if (url === '/api/tarot/draws') return respond([rawDraw]);
      if (url === '/api/tarot/draws/saved-draw') return respond(rawDraw);
      if (url.endsWith('/readings'))
        return respond([
          completed,
          { ...completed, id: 'reading-2', version: 2, result: { answer: '第二版：先休息。' } },
        ]);
      if (url.endsWith('/reveal') && init?.method === 'POST') {
        revealed = true;
        return respond({
          ...rawDraw,
          status: 'ready',
          cards: [{ ...rawDraw.cards[0], revealed: true, card: publicCard, orientation: 'upright' }],
        });
      }
      throw new Error('Unexpected synthetic route');
    });
    vi.stubGlobal('fetch', fetcher);
    render(<Tarot />);
    expect(await screen.findByRole('heading', { name: rawDraw.question })).toBeVisible();
    expect(screen.getByRole('img', { name: '不透明的塔罗牌背' })).toHaveAttribute('src', '/static/tarot/back.svg');
    expect(screen.getByLabelText('冻结的A/B选项')).toHaveTextContent('A：学习');
    expect(document.body).not.toHaveTextContent('PRIVATE');
    await user.click(screen.getByRole('button', { name: /^(全部揭开|全部揭开 · 跳过动画)$/ }));
    expect(await screen.findByRole('img', { name: '星星 · 正位' })).toBeVisible();
    expect(revealed).toBe(true);
    expect(screen.getByText('第二版：先休息。')).toBeVisible();
    await user.click(screen.getByRole('combobox', { name: '查看解读版本' }));
    await user.click(screen.getByRole('option', { name: '第1版' }));
    expect(screen.getByText('第一版：先核对现实安排。')).toBeVisible();
    expect(
      fetcher.mock.calls.filter(([url, init]) => url === '/api/tarot/draws' && init?.method === 'POST'),
    ).toHaveLength(0);
  });
  it('retries a failed reading using the same run and ID without drawing again', async () => {
    const sent: { url: string; payload: Record<string, unknown> }[] = [];
    let first = true;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.startsWith('/api/runs/reading%3A'))
          return first ? respond({}, 404) : respond({ id: 'same-run', status: 'failed' });
        if (init?.method === 'POST') {
          sent.push({ url, payload: JSON.parse(String(init.body)) as Record<string, unknown> });
          if (first) {
            first = false;
            return events([
              { type: 'started', run_id: 'same-run', reading_id: 'reading-1' },
              { type: 'error', message: 'private debug ignored' },
            ]);
          }
          return events([
            { type: 'started', run_id: 'same-run', reading_id: 'reading-1' },
            { type: 'result', result: completed.result },
          ]);
        }
        if (url.endsWith('/readings')) return respond([completed]);
        throw new Error('Unexpected synthetic route');
      }),
    );
    await expect(requestReading('saved-draw', '合成补充', new AbortController().signal, vi.fn())).rejects.toThrow(
      '解释未完成',
    );
    const pendingId = pendingReading('saved-draw')?.request_id;
    expect(pendingId).toBeTruthy();
    expect((await requestReading('saved-draw', '合成补充', new AbortController().signal, vi.fn()))[0].answer).toBe(
      completed.result.answer,
    );
    expect(sent[0]).toEqual({
      url: '/api/tarot/draws/saved-draw/readings',
      payload: { request_id: pendingId, supplement: '合成补充' },
    });
    expect(sent[1].url).toBe('/api/runs/same-run/retry');
    expect(sent[1].payload.request_id).toBe(`retry:${pendingId}`);
    expect(sent.every(({ url }) => url.endsWith('/readings') || url.endsWith('/retry'))).toBe(true);
    await waitFor(() => expect(pendingReading('saved-draw')).toBeUndefined());
  });
});
