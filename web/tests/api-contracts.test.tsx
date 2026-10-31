import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, useAuth } from '../src/api/client';
import { discardOperation, pendingPayload, write } from '../src/api/operations';

describe('persistent mutation identity', () => {
  beforeEach(() => {
    sessionStorage.clear();
    useAuth.getState().setToken('synthetic-test-token');
  });
  afterEach(() => {
    discardOperation('test-case');
    vi.unstubAllGlobals();
  });
  it('replays the same ID after ambiguous failure, then uses a new ID after a receipt', async () => {
    const bodies: Record<string, unknown>[] = [];
    const fetcher = vi.fn(async (_url: string, init: RequestInit) => {
      bodies.push(JSON.parse(String(init.body)) as Record<string, unknown>);
      if (bodies.length === 1) throw new TypeError('synthetic network loss');
      return new Response(JSON.stringify({ id: 'case-1', revision: 1 }));
    });
    vi.stubGlobal('fetch', fetcher);
    const payload = { title: '合成事项', goal: '核对下一步' };
    const options = { receipt: (row: { id: string }) => row.id === 'case-1' };
    await expect(write('test-case', 'POST', '/api/cases', payload, options)).rejects.toThrow();
    expect(pendingPayload('test-case')).toEqual(payload);
    await write('test-case', 'POST', '/api/cases', payload, options);
    await write('test-case', 'POST', '/api/cases', payload, options);
    expect(bodies[0].request_id).toBe(bodies[1].request_id);
    expect(bodies[2].request_id).not.toBe(bodies[1].request_id);
  });
  it('keeps intent and ID when a success response lacks the expected receipt', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ answer: '模型声称已保存' }))),
    );
    await expect(write('test-case', 'PATCH', '/api/test', { value: 1 }, { receipt: () => false })).rejects.toThrow();
    await expect(write('test-case', 'PATCH', '/api/test', { value: 2 })).rejects.toThrow('原内容重试');
    expect(pendingPayload('test-case')).toEqual({ value: 1 });
  });
  it('distinguishes known conflicts from ambiguous errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{}', { status: 409 })),
    );
    await expect(write('test-case', 'PATCH', '/api/test', { expected_revision: 1 })).rejects.toBeInstanceOf(ApiError);
    expect(pendingPayload('test-case')).toBeUndefined();
  });
  it('does not send when refresh-safe operation identity cannot be stored', async () => {
    const fetcher = vi.fn();
    vi.stubGlobal('fetch', fetcher);
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Synthetic storage quota', 'QuotaExceededError');
    });
    await expect(write('test-case', 'POST', '/api/cases', { title: '合成草稿' })).rejects.toThrow('本次没有发送');
    expect(fetcher).not.toHaveBeenCalled();
    expect(pendingPayload('test-case')).toBeUndefined();
  });
});
