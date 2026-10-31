import { DemoDenied, type DemoSignInPort, type DemoSession } from './demoSignIn';

export type DemoScenario = 'success' | 'denied' | 'unavailable' | 'timeout' | 'expired';

/** Fresh per preview: no fetch, SDK, browser storage, cookie or real authentication store. */
export function fakeSignInPort(scenario: DemoScenario, clock = Date.now): DemoSignInPort {
  let issued = 0;
  const codes = new Set<string>();
  const sessions = new Map<string, DemoSession>();
  const delay = (signal: AbortSignal) =>
    new Promise<void>((resolve, reject) => {
      if (signal.aborted) {
        reject(new Error());
        return;
      }
      const abort = () => {
        clearTimeout(timer);
        reject(new Error());
      };
      const timer = setTimeout(() => {
        signal.removeEventListener('abort', abort);
        resolve();
      }, 250);
      signal.addEventListener('abort', abort, { once: true });
    });
  return {
    async requestCode(signal) {
      await delay(signal);
      if (scenario === 'denied') throw new DemoDenied();
      if (scenario === 'unavailable') throw new Error();
      if (scenario === 'timeout')
        await new Promise<void>((_, reject) =>
          signal.addEventListener('abort', () => reject(new Error()), { once: true }),
        );
      const code = `synthetic-code-${++issued}`;
      codes.add(code);
      return code;
    },
    async exchange(code, signal) {
      if (!codes.delete(code)) throw new Error();
      await delay(signal);
      const session = {
        id: `synthetic-session-${issued}`,
        name: '合成访客',
        expiresAt: clock() + (scenario === 'expired' ? -1 : 60000),
      };
      sessions.set(session.id, session);
      return session;
    },
    async revoke(session) {
      sessions.delete(session.id);
    },
  };
}
