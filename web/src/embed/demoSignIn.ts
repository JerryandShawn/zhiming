import { abortable } from '../chat/followV1Async';

/** Demo-only in-memory port. This is not a proposed HTTP/cookie authentication contract. */
export type DemoSession = { id: string; name: string; expiresAt: number };
export type DemoSignInPort = {
  requestCode: (signal: AbortSignal) => Promise<string>;
  exchange: (code: string, signal: AbortSignal) => Promise<DemoSession>;
  revoke: (session: DemoSession) => Promise<void>;
};
export type DemoSignInState = {
  phase: 'idle' | 'authorizing' | 'exchanging' | 'ready' | 'denied' | 'failed' | 'expired' | 'signed-out';
  reason?: 'timeout' | 'unavailable' | 'revoke-unconfirmed';
  session?: DemoSession;
};
export class DemoDenied extends Error {}

export function createDemoSignIn(port: DemoSignInPort, clock = Date.now, timeoutMs = 5000) {
  let state: DemoSignInState = { phase: 'idle' },
    epoch = 0,
    disposed = false;
  let controller: AbortController | undefined;
  const listeners = new Set<() => void>();
  const publish = (next: DemoSignInState) => {
    if (disposed) return;
    state = next;
    listeners.forEach((listener) => listener());
  };
  const retire = () => {
    epoch++;
    controller?.abort();
    controller = undefined;
  };
  async function signIn() {
    if (disposed || ['authorizing', 'exchanging', 'ready'].includes(state.phase)) return;
    retire();
    const owner = epoch;
    const attempt = new AbortController();
    controller = attempt;
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      attempt.abort();
    }, timeoutMs);
    const current = () => !disposed && epoch === owner;
    publish({ phase: 'authorizing' });
    try {
      const code = await abortable(port.requestCode(attempt.signal), attempt.signal);
      if (!current()) return;
      if (typeof code !== 'string' || !code.trim()) throw new Error();
      publish({ phase: 'exchanging' });
      const session = await abortable(port.exchange(code, attempt.signal), attempt.signal);
      if (!current()) return;
      if (
        !session ||
        typeof session.id !== 'string' ||
        !session.id ||
        typeof session.name !== 'string' ||
        !session.name.trim() ||
        !Number.isFinite(session.expiresAt)
      )
        throw new Error();
      if (session.expiresAt <= clock()) publish({ phase: 'expired' });
      else publish({ phase: 'ready', session: { id: session.id, name: session.name, expiresAt: session.expiresAt } });
    } catch (error) {
      if (current())
        publish(
          error instanceof DemoDenied
            ? { phase: 'denied' }
            : {
                phase: 'failed',
                reason: timedOut ? 'timeout' : 'unavailable',
              },
        );
    } finally {
      clearTimeout(timer);
      attempt.abort();
      if (current()) controller = undefined;
    }
  }
  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    signIn,
    cancel() {
      retire();
      publish({ phase: 'idle' });
    },
    checkExpiry() {
      if (state.session && state.session.expiresAt <= clock()) {
        retire();
        publish({ phase: 'expired' });
      }
    },
    async signOut() {
      if (disposed) return;
      const session = state.session;
      retire();
      const owner = epoch;
      publish({ phase: 'signed-out' });
      if (!session) return;
      try {
        await port.revoke(session);
      } catch {
        if (!disposed && epoch === owner) publish({ phase: 'signed-out', reason: 'revoke-unconfirmed' });
      }
    },
    dispose() {
      retire();
      disposed = true;
      state = { phase: 'idle' };
      listeners.clear();
    },
  };
}
