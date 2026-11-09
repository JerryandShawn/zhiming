import { describe, expect, it, vi } from 'vitest';
import { followV1 } from '../src/chat/followV1';
import {
  createRecoveryPort,
  localRecoveryTransportAllowed,
  recoveryPortForLocation,
  RECOVERY_FIXTURE_PATH,
} from '../src/night/recovery/port';

describe('recovery demo adapter boundary', () => {
  it('discards the actual truncated mock frame and reconnects from sequence three', async () => {
    const port = createRecoveryPort({
      rejectFirst: false,
      delayMs: 0,
      now: () => new Date('2026-10-21T07:00:00+08:00'),
    });
    const cursors: (string | undefined)[] = [],
      seq: number[] = [];
    const result = await followV1(port.runId, {
      signal: new AbortController().signal,
      retryMs: 0,
      connect: (cursor, signal) => {
        cursors.push(cursor);
        return port.connect(cursor, signal);
      },
      accept: (event) => {
        seq.push(event.seq!);
      },
    });
    expect(result.reason).toBe('final');
    expect(cursors).toEqual([undefined, '3']);
    expect(seq).toEqual([1, 2, 3, 4, 5, 6]);
  });
  it.each([
    'https://example.test/?recoveryTransport=local-fixture',
    'http://127.0.0.1/?recoveryTransport=production',
    'http://127.0.0.1/',
  ])('keeps %s in memory without invoking fetch', async (address) => {
    const fetcher = vi.fn<typeof fetch>();
    const url = new URL(address);
    expect(localRecoveryTransportAllowed(url)).toBe(false);
    const port = recoveryPortForLocation(url, fetcher);
    expect(port.mode).toBe('memory');
    await expect(port.connect(undefined, new AbortController().signal)).rejects.toThrow('合成连接');
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('uses only the explicit loopback fixture path with an anonymous no-store cursor request', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(''));
    const port = recoveryPortForLocation(new URL('http://127.0.0.1:4173/?recoveryTransport=local-fixture'), fetcher);
    const signal = new AbortController().signal;
    await port.connect('3', signal);
    const [url, options] = fetcher.mock.calls[0];
    expect(String(url)).toBe('http://127.0.0.1:4173' + RECOVERY_FIXTURE_PATH);
    expect(new Headers(options?.headers).get('Last-Event-ID')).toBe('3');
    expect(options).toMatchObject({ signal, credentials: 'omit', cache: 'no-store' });
    expect(RECOVERY_FIXTURE_PATH).not.toMatch(/^\/(?:api|__test__)(?:\/|$)/);
    await expect(port.connect('not-a-sequence', signal)).rejects.toThrow('恢复位置');
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
