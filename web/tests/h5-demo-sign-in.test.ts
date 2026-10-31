import { afterEach, describe, expect, it, vi } from 'vitest';
import { createDemoSignIn, DemoDenied, type DemoSignInPort, type DemoSession } from '../src/embed/demoSignIn';
import { fakeSignInPort } from '../src/embed/fakeSignInPort';

afterEach(() => vi.useRealTimers());
function fixture(patch: Partial<DemoSignInPort> = {}) {
  const port = {
    requestCode: vi.fn(async () => 'SECRET_ONE_TIME_CODE'),
    exchange: vi.fn(async () => ({ id: 'session-1', name: '合成访客', expiresAt: 10000 })),
    revoke: vi.fn(async () => undefined),
    ...patch,
  };
  const clock = { now: 1000 };
  const session = createDemoSignIn(port, () => clock.now);
  return { port, clock, session };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => {
    resolve = accept;
  });
  return { promise, resolve };
}
const tick = async () => {
  for (let i = 0; i < 8; i++) await Promise.resolve();
};

describe('isolated H5 demonstration sign-in lifecycle', () => {
  it('constructs without authentication, requests, credentials or code in public state', async () => {
    const f = fixture();
    expect(f.session.getSnapshot()).toEqual({ phase: 'idle' });
    expect(f.port.requestCode).not.toHaveBeenCalled();
    const states: string[] = [];
    f.session.subscribe(() => states.push(JSON.stringify(f.session.getSnapshot())));
    await f.session.signIn();
    expect(f.session.getSnapshot().phase).toBe('ready');
    expect(states.join()).not.toContain('SECRET_ONE_TIME_CODE');
    expect(f.port.exchange).toHaveBeenCalledTimes(1);
    f.session.dispose();
  });

  it('does not duplicate authorization or exchange on double click', async () => {
    const pending = deferred<string>();
    const f = fixture({ requestCode: vi.fn(() => pending.promise) });
    const first = f.session.signIn();
    await f.session.signIn();
    pending.resolve('synthetic-code');
    await first;
    expect(f.port.requestCode).toHaveBeenCalledTimes(1);
    expect(f.port.exchange).toHaveBeenCalledTimes(1);
    await f.session.signIn();
    expect(f.port.requestCode).toHaveBeenCalledTimes(1);
    f.session.dispose();
  });

  it.each(['authorization', 'exchange'])('cancel during %s prevents a late authenticated state', async (stage) => {
    const code = deferred<string>(),
      accepted = deferred<DemoSession>();
    const f = fixture(
      stage === 'authorization' ? { requestCode: () => code.promise } : { exchange: () => accepted.promise },
    );
    const task = f.session.signIn();
    await tick();
    f.session.cancel();
    code.resolve('synthetic-code');
    accepted.resolve({ id: 'late', name: '迟到访客', expiresAt: 10000 });
    await task;
    expect(f.session.getSnapshot()).toEqual({ phase: 'idle' });
    f.session.dispose();
  });

  it('times out an ignored abort, without automatically replaying the authorization code', async () => {
    vi.useFakeTimers();
    const f = fixture({ exchange: vi.fn(() => new Promise<DemoSession>(() => {})) });
    const task = f.session.signIn();
    await vi.advanceTimersByTimeAsync(5000);
    await task;
    expect(f.session.getSnapshot()).toEqual({ phase: 'failed', reason: 'timeout' });
    expect(f.port.requestCode).toHaveBeenCalledTimes(1);
    expect(f.port.exchange).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
    f.session.dispose();
  });

  it.each([new DemoDenied(), new Error('SECRET_PROVIDER_BODY')])(
    'keeps denial/failure controlled and code-free',
    async (error) => {
      const f = fixture({
        requestCode: async () => {
          throw error;
        },
      });
      await f.session.signIn();
      expect(f.session.getSnapshot().phase).toBe(error instanceof DemoDenied ? 'denied' : 'failed');
      expect(JSON.stringify(f.session.getSnapshot())).not.toContain('SECRET');
      expect(f.port.exchange).not.toHaveBeenCalled();
      f.session.dispose();
    },
  );

  it.each([0, NaN, Infinity])('does not treat malformed or expired timestamp %s as a login', async (expiresAt) => {
    const f = fixture({ exchange: async () => ({ id: 's', name: '合成访客', expiresAt }) });
    await f.session.signIn();
    expect(f.session.getSnapshot().phase).toBe(expiresAt === 0 ? 'expired' : 'failed');
    expect(f.session.getSnapshot().session).toBeUndefined();
    f.session.dispose();
  });

  it('expires exactly at the injected deadline, clears identity and can start a fresh flow', async () => {
    const f = fixture();
    await f.session.signIn();
    f.clock.now = 9999;
    f.session.checkExpiry();
    expect(f.session.getSnapshot().phase).toBe('ready');
    f.clock.now = 10000;
    f.session.checkExpiry();
    expect(f.session.getSnapshot()).toEqual({ phase: 'expired' });
    f.clock.now = 1000;
    await f.session.signIn();
    expect(f.port.requestCode).toHaveBeenCalledTimes(2);
    f.session.dispose();
  });

  it('local sign-out clears identity immediately while a remote revocation is unconfirmed', async () => {
    const pending = deferred<void>();
    const f = fixture({ revoke: () => pending.promise });
    await f.session.signIn();
    const task = f.session.signOut();
    expect(f.session.getSnapshot()).toEqual({ phase: 'signed-out' });
    await f.session.signIn();
    pending.resolve();
    await task;
    expect(f.session.getSnapshot().phase).toBe('ready');
    f.session.dispose();
  });

  it('failed revocation is not misreported as confirmed remote logout', async () => {
    const f = fixture({
      revoke: async () => {
        throw new Error('SECRET_REVOKE');
      },
    });
    await f.session.signIn();
    await f.session.signOut();
    expect(f.session.getSnapshot()).toEqual({ phase: 'signed-out', reason: 'revoke-unconfirmed' });
    f.session.dispose();
  });

  it('unmount clears public identity, timers and subscription callbacks', async () => {
    vi.useFakeTimers();
    const pending = deferred<DemoSession>();
    const f = fixture({ exchange: () => pending.promise });
    const listener = vi.fn();
    f.session.subscribe(listener);
    const task = f.session.signIn();
    await tick();
    f.session.dispose();
    const count = listener.mock.calls.length;
    pending.resolve({ id: 'late', name: '迟到', expiresAt: 10000 });
    await task;
    expect(f.session.getSnapshot()).toEqual({ phase: 'idle' });
    expect(listener).toHaveBeenCalledTimes(count);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('fake exchange consumes each issued code once and uses no fetch or browser storage', async () => {
    vi.useFakeTimers();
    const fetcher = vi.spyOn(globalThis, 'fetch');
    const storage = vi.spyOn(Storage.prototype, 'setItem');
    try {
      const port = fakeSignInPort('success', () => 1000);
      const signal = new AbortController().signal;
      const issuing = port.requestCode(signal);
      await vi.advanceTimersByTimeAsync(250);
      const code = await issuing;
      const exchanging = port.exchange(code, signal);
      await vi.advanceTimersByTimeAsync(250);
      const session = await exchanging;
      expect(session.name).toBe('合成访客');
      await expect(port.exchange(code, signal)).rejects.toThrow();
      await port.revoke(session);
      expect(fetcher).not.toHaveBeenCalled();
      expect(storage).not.toHaveBeenCalled();
    } finally {
      fetcher.mockRestore();
      storage.mockRestore();
    }
  });
});
