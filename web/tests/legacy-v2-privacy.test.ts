import { afterEach, describe, expect, it, vi } from 'vitest';
import { followV2 } from '../src/chat/v2';
import { reduceChat } from '../src/chat/reducer';
import { initialStream, type ChatEvent } from '../src/chat/types';
import { hiddenProfile } from '../src/chat/publicProjection';

const runId = 'synthetic-private';
const key = `mingjing-sse-v2:${runId}`;
function memoryFixture() {
  const values = new Map<string, string>(),
    writes: string[] = [];
  const storage: Storage = {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    key: (index) => [...values.keys()][index] ?? null,
    getItem: (name) => values.get(name) ?? null,
    setItem: (name, value) => {
      writes.push(value);
      values.set(name, value);
    },
    removeItem: (name) => {
      values.delete(name);
    },
  };
  return { storage, writes };
}
function stream(events: { type: string; body: Record<string, unknown> }[]) {
  return new Response(
    events
      .map(
        ({ type, body }, index) =>
          `id: ${index + 1}\nevent: ${type}\ndata: ${JSON.stringify({ ...body, v: 1, run_id: runId, seq: index + 1, ts: '2026-10-21T02:00:00+08:00' })}\n\n`,
      )
      .join(''),
    { headers: { 'Content-Type': 'text/event-stream' } },
  );
}
function final(answer: string): Record<string, unknown> {
  return {
    message_id: 'synthetic-message',
    envelope: {
      schema: 'core4.0',
      message_id: 'synthetic-message',
      text: answer,
      receipts: [],
      used_fact_ids: [],
      used_claim_ids: [],
      asked: null,
      options: null,
      review: { state: 'passed', reasons: [] },
      usage: {},
    },
  };
}
const harmless = [
  { type: 'text_delta', body: { text: '公开合成正文' } },
  { type: 'final', body: final('公开合成正文') },
];
const source =
  (events = harmless): typeof fetch =>
  async (input) =>
    String(input).endsWith('/events') ? stream(events) : Response.json({ status: 'running' });
afterEach(() => vi.restoreAllMocks());

describe('provisional legacy follower remains memory-only by default', () => {
  it('does not read, write, remove or clear browser Storage, even when restore is supplied', async () => {
    const spies = (['getItem', 'setItem', 'removeItem', 'clear'] as const).map((method) =>
      vi.spyOn(Storage.prototype, method),
    );
    const events: ChatEvent[] = [];
    await followV2(runId, { fetcher: source(), restore: vi.fn(), accept: (event) => events.push(event) });
    expect(events.at(-1)?.type).toBe('final');
    spies.forEach((spy) => expect(spy).not.toHaveBeenCalled());
  });

  it.each(['localStorage', 'sessionStorage'] as const)(
    'rejects direct %s fixture binding before any storage method or transport is used',
    async (name) => {
      const storage = window[name];
      const spies = (['getItem', 'setItem', 'removeItem', 'clear'] as const).map((method) =>
        vi.spyOn(Storage.prototype, method),
      );
      const fetcher = vi.fn(source());
      await expect(followV2(runId, { fixtureStorage: storage, fetcher, accept: vi.fn() })).rejects.toThrow(
        '合成内存测试存储',
      );
      expect(fetcher).not.toHaveBeenCalled();
      spies.forEach((spy) => expect(spy).not.toHaveBeenCalled());
    },
  );

  it('writes only redacted public events and removes prior text fragments when birth data spans deltas', async () => {
    const { storage, writes } = memoryFixture();
    const events = [
      { type: 'status', body: { text: 'birth.date: 1990-01-01', phase: 'writing' } },
      { type: 'text_delta', body: { text: 'bir' } },
      { type: 'text_delta', body: { text: 'th.' } },
      { type: 'text_delta', body: { text: 'date: ' } },
      { type: 'text_delta', body: { text: '1990-01-01' } },
      { type: 'final', body: final('birth.date: 1990-01-01') },
    ];
    await followV2(runId, { fixtureStorage: storage, fetcher: source(events), accept: vi.fn() });
    expect(writes.join('\n')).not.toContain('1990-01-01');
    const cached = storage.getItem(`${key}:events`)!;
    expect(cached).toContain(hiddenProfile);
    expect(cached).not.toMatch(/"data"|"text":"bir"|"text":"th\."|birth\.date/);
    expect(JSON.parse(cached)).toMatchObject({ format: 'mingjing-public-fixture-v1', runId });
  });

  it('restores a complete legitimate public projection without re-querying or losing memory receipts', async () => {
    const { storage } = memoryFixture();
    const input = [
      {
        type: 'memory_receipt',
        body: { fact_id: 'synthetic-fact', write_status: 'saved', summary: '合成偏好', sensitive: false },
      },
      ...harmless,
    ];
    await followV2(runId, { fixtureStorage: storage, fetcher: source(input), accept: vi.fn() });
    const restore = vi.fn(),
      fetcher = vi.fn(source());
    await followV2(runId, { fixtureStorage: storage, restore, fetcher, accept: vi.fn() });
    expect(fetcher).not.toHaveBeenCalled();
    expect(restore).toHaveBeenCalledWith(
      expect.objectContaining({
        complete: true,
        text: '公开合成正文',
        receipts: [expect.objectContaining({ fact_id: 'synthetic-fact', summary: '合成偏好' })],
      }),
    );
    expect(storage.getItem(key)).toBe('3');
  });

  it.each(['invalid-tail', 'restore-throws'] as const)(
    'resets the complete snapshot and cursor after %s instead of falsely returning completed',
    async (mode) => {
      const { storage } = memoryFixture();
      await followV2(runId, { fixtureStorage: storage, fetcher: source(), accept: vi.fn() });
      if (mode === 'invalid-tail') {
        const cached = JSON.parse(storage.getItem(`${key}:events`)!) as { events: unknown[] };
        cached.events.push({ id: '3', projection: { type: 'not-a-public-event' } });
        storage.setItem(`${key}:events`, JSON.stringify(cached));
      }
      const fetcher = vi.fn(source()),
        headers: Headers[] = [];
      fetcher.mockImplementation(async (input, init) => {
        if (String(input).endsWith('/events')) headers.push(new Headers(init?.headers));
        return source()(input, init);
      });
      let state = initialStream();
      await followV2(runId, {
        fixtureStorage: storage,
        fetcher,
        restore: () => {
          if (mode === 'restore-throws') throw new Error('Synthetic consumer failure');
        },
        accept: (event) => {
          state = reduceChat(state, event);
        },
      });
      expect(fetcher).toHaveBeenCalled();
      expect(headers[0].get('Last-Event-ID')).toBeNull();
      expect(state).toMatchObject({ complete: true, text: '公开合成正文' });
    },
  );

  it('never records an incognito synthetic run, even through the explicit fixture seam', async () => {
    const { storage, writes } = memoryFixture();
    const events = [
      { type: 'started', body: { thread_id: 'private-thread', message_id: 'private-message', incognito: true } },
      { type: 'text_delta', body: { text: 'PRIVATE_SYNTHETIC_MESSAGE' } },
      { type: 'final', body: final('PRIVATE_SYNTHETIC_MESSAGE') },
    ];
    await followV2(runId, { fixtureStorage: storage, fetcher: source(events), accept: vi.fn() });
    expect(writes).toEqual([]);
    expect(storage.length).toBe(0);
  });

  it('still refuses malformed explicit v1 instead of treating its projected cache format as wire', async () => {
    const { storage } = memoryFixture();
    const accepted: ChatEvent[] = [];
    const fetcher: typeof fetch = async (input) =>
      String(input).endsWith('/events')
        ? new Response('id: 1\nevent: final\ndata: {"v":1,"envelope":{"answer":"must not downgrade"}}\n\n')
        : Response.json({ status: 'running' });
    await expect(
      followV2(runId, { fixtureStorage: storage, fetcher, maxReconnects: 0, accept: (event) => accepted.push(event) }),
    ).rejects.toThrow('连接仍未恢复');
    expect(accepted).toEqual([]);
    expect(storage.length).toBe(0);
  });
});
