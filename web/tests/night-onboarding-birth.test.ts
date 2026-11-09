import { describe, expect, it, vi } from 'vitest';
import { createBirthPort, emptyBirthDraft } from '../src/night/onboarding/birth';

describe('isolated birth confirmation port', () => {
  it('starts empty and confirms a date-only partial without inventing midnight, city or coordinates', async () => {
    const port = createBirthPort();
    expect(Object.values(port.readPrivate().draft).every((value) => value === '')).toBe(true);
    const ack = await port.confirm({
      requestId: 'partial',
      expectedRevision: 0,
      confirmed: true,
      draft: { ...emptyBirthDraft(), date: '1998-03-12' },
    });
    expect(ack).toMatchObject({ confirmation: 'partial', confirmedFields: ['date'], revision: 1 });
    expect(port.readPrivate().draft).toEqual({ ...emptyBirthDraft(), date: '1998-03-12' });
    expect(JSON.stringify(port.readSummary())).not.toMatch(/1998-03-12|00:00|116\.4/);
    expect(port.readSummary().canComputeGift).toBe(false);
  });
  it('retains an explicit unknown precision but never a stale time or uncertainty', async () => {
    const port = createBirthPort();
    await port.confirm({
      requestId: 'unknown',
      expectedRevision: 0,
      confirmed: true,
      draft: {
        ...emptyBirthDraft(),
        date: '1998-03-12',
        precision: 'unknown',
        time: '08:15',
        uncertaintyMinutes: '20',
      },
    });
    expect(port.readPrivate().draft.time).toBe('');
    expect(port.readPrivate().draft.uncertaintyMinutes).toBe('');
  });
  it('returns the same valid receipt on replay, rejects changed intent and rejects stale revisions atomically', async () => {
    const port = createBirthPort(),
      command = {
        requestId: 'stable',
        expectedRevision: 0,
        confirmed: true as const,
        draft: { ...emptyBirthDraft(), date: '1998-03-12' },
      };
    const ack = await port.confirm(command);
    expect(await port.confirm(command)).toBe(ack);
    await expect(port.confirm({ ...command, draft: { ...command.draft, city: '新的合成城' } })).rejects.toMatchObject({
      status: 409,
      code: 'REPLAY_CHANGED',
    });
    await expect(port.confirm({ ...command, requestId: 'stale' })).rejects.toMatchObject({ status: 409 });
    expect(port.readSummary().revision).toBe(1);
  });
  it.each([
    { date: '2026-02-30' },
    { time: '08:15' },
    { date: '1998-03-12', precision: 'exact' },
    { date: '1998-03-12', time: '08:15', precision: 'approximate', uncertaintyMinutes: '0' },
    { longitude: '181' },
    { latitude: 'NaN' },
  ])('rejects invalid field combinations without confirming anything: %j', async (fields) => {
    const port = createBirthPort();
    await expect(
      port.confirm({
        requestId: 'invalid',
        expectedRevision: 0,
        confirmed: true,
        draft: { ...emptyBirthDraft(), ...fields } as ReturnType<typeof emptyBirthDraft>,
      }),
    ).rejects.toMatchObject({ status: 422 });
    expect(port.readSummary().status).toBe('unconfirmed');
  });
  it('never performs network or persistent storage operations', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch'),
      get = vi.spyOn(Storage.prototype, 'getItem'),
      set = vi.spyOn(Storage.prototype, 'setItem');
    try {
      const port = createBirthPort();
      await port.confirm({
        requestId: 'local',
        expectedRevision: 0,
        confirmed: true,
        draft: { ...emptyBirthDraft(), date: '1998-03-12' },
      });
      expect(fetcher).not.toHaveBeenCalled();
      expect(get).not.toHaveBeenCalled();
      expect(set).not.toHaveBeenCalled();
    } finally {
      vi.restoreAllMocks();
    }
  });
});
