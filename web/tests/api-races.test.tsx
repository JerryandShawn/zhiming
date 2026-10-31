import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, useAuth } from '../src/api/client';
import { pendingPayload, write } from '../src/api/operations';

beforeEach(() => {
  sessionStorage.clear();
  useAuth.getState().setToken(`owner-A-${crypto.randomUUID()}`);
});
afterEach(() => {
  vi.unstubAllGlobals();
});
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

describe('authentication boundaries during in-flight requests', () => {
  it('does not let an old owner receipt erase the new owner pending operation', async () => {
    let finishOld!: (value: Response) => void;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url === '/old-owner')
          return new Promise<Response>((resolve) => {
            finishOld = resolve;
          });
        throw new TypeError('synthetic ambiguous disconnect');
      }),
    );
    const old = write('race', 'POST', '/old-owner', { content: '合成旧用户' }).catch(() => undefined);
    useAuth.getState().setToken(`owner-B-${crypto.randomUUID()}`);
    await expect(write('race', 'POST', '/new-owner', { content: '合成新用户' })).rejects.toThrow();
    finishOld(response({ id: 'old-receipt' }));
    await old;
    expect(pendingPayload('race')).toEqual({ content: '合成新用户' });
  });
  it('does not let an old owner 401 invalidate the new login', async () => {
    let finishOld!: (value: Response) => void;
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            finishOld = resolve;
          }),
      ),
    );
    const old = api('/old-owner').catch(() => undefined);
    useAuth.getState().setToken(`owner-B-${crypto.randomUUID()}`);
    finishOld(response({}, 401));
    await old;
    expect(useAuth.getState().loginRequired).toBe(false);
  });
  it('rejects an old owner successful body after the identity changed', async () => {
    let finishOld!: (value: Response) => void;
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            finishOld = resolve;
          }),
      ),
    );
    const old = api<{ content: string }>('/old-owner');
    useAuth.getState().setToken(`owner-B-${crypto.randomUUID()}`);
    finishOld(response({ content: '合成旧用户正文' }));
    await expect(old).rejects.toThrow();
  });
});
