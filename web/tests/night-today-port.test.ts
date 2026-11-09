import { describe, expect, it } from 'vitest';
import day21 from '../src/night/today/data/2026-10-21.json';
import { createTodayPort, dailyEvidenceKey, previewNoticePolicy, projectPublicDailySample } from '../src/night/today';
import type { DailyTransitView, NoticePolicyInput } from '../src/night/today';

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
async function ready(date = '2026-10-21') {
  const port = createTodayPort(),
    result = await port.read(date);
  expect(result.status).toBe('ready');
  if (result.status !== 'ready') throw new Error('Expected the synthetic published fixture');
  return { port, transit: result.transit };
}
function changed(change: (sample: DailyTransitView) => void) {
  const sample = structuredClone(day21) as DailyTransitView;
  change(sample);
  return sample;
}

describe('public daily-transit date port', () => {
  it('reads all seven pinned actual-engine synthetic dates, normalizes Beijing noon and has no private source fields', async () => {
    const port = createTodayPort();
    expect(port.availableDates).toEqual(Array.from({ length: 7 }, (_, index) => `2026-10-${21 + index}`));
    for (const date of port.availableDates) {
      const result = await port.read(date);
      expect(result.status).toBe('ready');
      if (result.status !== 'ready') throw new Error('Missing fixture');
      expect(result.transit.snapshotAtBeijing).toBe(`${date}T12:00:00+08:00`);
      expect(result.transit.provenance).toMatchObject({
        sourceCommit: 'b51470b8e32eb72b8151df4eca7eee2e1584bee5',
        mode: 'published-synthetic-engine',
        contractStatus: 'aligned',
        integrity: 'document-and-alias-digests-verified',
      });
      expect(new Set(result.transit.highlights.map((item) => item.system))).toEqual(
        new Set(['bazi', 'ziwei', 'astro']),
      );
      expect(JSON.stringify(result)).not.toMatch(
        /owner_user_id|subject_id|coordinate_datetime|natal_at_utc|1994-03-12|08:20|104\.07|30\.67/,
      );
      expect(Object.isFrozen(result.transit.highlights[0].refs[0])).toBe(true);
    }
    const { transit } = await ready();
    expect(transit.dayGanzhi).toBe('戊辰');
    expect(transit.dayTenGod).toBe('伤官');
  });

  it('resolves aliases only within the exact date and document, including reused short aliases', async () => {
    const port = createTodayPort();
    const days = await Promise.all(['2026-10-21', '2026-10-22'].map((date) => port.read(date)));
    const views = days.map((result) => {
      if (result.status !== 'ready') throw new Error('Missing fixture');
      return result.transit;
    });
    for (const view of views)
      for (const item of view.evidence) {
        expect(port.resolveEvidence(item.ref)).toEqual(item);
        expect(port.resolveEvidence({ ...item.ref, date: '2026-10-28' })).toBeUndefined();
        const other = views.find((candidate) => candidate.documentId !== view.documentId)!;
        expect(port.resolveEvidence({ ...item.ref, documentId: other.documentId })).toBeUndefined();
      }
    const keys = views.flatMap((view) => view.evidence.map((item) => dailyEvidenceKey(item.ref)));
    expect(new Set(keys).size).toBe(keys.length);
    expect(
      views[0].evidence.some((first) => views[1].evidence.some((second) => first.ref.alias === second.ref.alias)),
    ).toBe(true);
    expect(
      port.resolveEvidence({ date: views[0].date, documentId: views[0].documentId, alias: 'c9999' }),
    ).toBeUndefined();
  });

  it.each(['2026-02-30', '2026-2-03', '2026-10-21T00:00:00Z', '1900-12-31', '2100-01-01', 'private-birth-sentinel'])(
    'rejects invalid or unsupported date %s without echoing it',
    async (date) => {
      await expect(createTodayPort().read(date)).rejects.toMatchObject({ code: 'INVALID_DATE' });
      await expect(createTodayPort().read(date)).rejects.not.toThrow(date);
    },
  );

  it('keeps empty data distinct from failure and supports a deterministic delayed adapter', async () => {
    const gate = deferred();
    const port = createTodayPort({
      wait: () => gate.promise,
      emptyDates: ['2026-10-22'],
      failureDates: ['2026-10-23'],
    });
    let received = false;
    const pending = port.read('2026-10-21').then((result) => {
      received = true;
      return result;
    });
    await Promise.resolve();
    expect(received).toBe(false);
    gate.resolve();
    expect((await pending).status).toBe('ready');
    await expect(port.read('2026-10-22')).resolves.toMatchObject({ status: 'empty', date: '2026-10-22' });
    await expect(port.read('2026-10-23')).rejects.toMatchObject({ code: 'UNAVAILABLE' });
    await expect(port.read('2026-10-28')).resolves.toMatchObject({ status: 'empty', date: '2026-10-28' });
  });

  it('does not return a delayed result after its date request is aborted', async () => {
    const gate = deferred(),
      controller = new AbortController();
    const pending = createTodayPort({ wait: () => gate.promise }).read('2026-10-21', controller.signal);
    controller.abort(new DOMException('Date changed', 'AbortError'));
    gate.resolve();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });

  it.each([
    (sample: DailyTransitView) => {
      sample.evidence[0].ref.date = '2026-10-22';
    },
    (sample: DailyTransitView) => {
      sample.highlights[0].refs[0].documentId = 'tool-' + '0'.repeat(64);
    },
    (sample: DailyTransitView) => {
      sample.evidence.push(structuredClone(sample.evidence[0]));
    },
    (sample: DailyTransitView) => {
      sample.highlights[0].refs[0].alias = 'c9999';
    },
    (sample: DailyTransitView) => {
      sample.snapshotAtBeijing = '2026-10-21T13:00:00+09:00';
    },
  ])('rejects inconsistent public projections instead of resolving another day or raw value', (mutate) => {
    expect(() => projectPublicDailySample(changed(mutate))).toThrow('公开投影核对');
  });

  it('rejects raw/private additional fields at every public layer with a sanitized error', () => {
    const privateValue = { owner_user_id: 'private-owner-sentinel', birth: { date: 'private-birth-sentinel' } };
    for (const sample of [
      { ...day21, scope: privateValue },
      { ...day21, time_basis: privateValue },
      { ...day21, provenance: { ...day21.provenance, source: privateValue } },
      { ...day21, evidence: [{ ...day21.evidence[0], value: privateValue }] },
    ]) {
      expect(() => projectPublicDailySample(sample)).toThrow('公开投影核对');
      expect(() => projectPublicDailySample(sample)).not.toThrow('private-');
    }
    expect(() => createTodayPort({ samples: [day21, day21] })).toThrow('日期重复');
  });
});

describe('K1/K2 scheduling preview without delivery', () => {
  const preview = (dueAt: string, now: string, kind: NoticePolicyInput['kind'] = 'explicit-reminder') =>
    previewNoticePolicy({ dueAt, now: new Date(now), kind });
  it('keeps the user-scheduled morning report outside DND but holds unsolicited follow-ups', () => {
    expect(preview('2026-10-21T07:00:00+08:00', '2026-10-21T07:00:00+08:00', 'daily').placement).toBe('ready');
    expect(preview('2026-10-21T07:00:00+08:00', '2026-10-21T07:00:00+08:00', 'followup')).toMatchObject({
      placement: 'quiet-hold',
      notBefore: '2026-10-21T08:00:00.000+08:00',
    });
  });
  it('previews explicit reminders during DND through exactly 60 minutes late', () => {
    expect(preview('2026-10-21T06:00:00+08:00', '2026-10-21T06:00:00+08:00').placement).toBe('ready');
    expect(preview('2026-10-21T06:00:00+08:00', '2026-10-21T07:00:00+08:00')).toMatchObject({
      placement: 'ready',
      lateMinutes: 60,
    });
    expect(preview('2026-10-21T06:00:00+08:00', '2026-10-21T07:00:00+08:00').message).toContain('晚了 60 分钟');
    expect(preview('2026-10-21T06:00:00+08:00', '2026-10-21T07:00:01+08:00')).toMatchObject({
      placement: 'quiet-hold',
      notBefore: '2026-10-21T08:00:00.000+08:00',
    });
  });
  it('keeps reminders older than twelve hours in the inbox and uses explicit instants across time zones', () => {
    expect(preview('2026-10-20T19:00:00+08:00', '2026-10-21T07:00:00+08:00').placement).toBe('quiet-hold');
    expect(preview('2026-10-20T19:00:00+08:00', '2026-10-21T07:00:01+08:00').placement).toBe('inbox-only');
    expect(preview('2026-10-21T05:00:00+08:00', '2026-10-21T08:00:00+08:00').placement).toBe('ready');
    expect(preview('2026-10-21T08:00:00+08:00', '2026-10-21T08:00:00+09:00').placement).toBe('scheduled');
    expect(preview('2026-10-21T07:00:00+08:00', '2026-10-21T00:00:00Z')).toEqual(
      preview('2026-10-21T07:00:00+08:00', '2026-10-21T08:00:00+08:00'),
    );
  });
  it('supports custom quiet hours and rejects invalid policy clocks', () => {
    expect(
      previewNoticePolicy({
        kind: 'followup',
        dueAt: '2026-10-21T10:00:00+08:00',
        now: new Date('2026-10-21T10:00:00+08:00'),
        dndStart: '09:00',
        dndEnd: '12:00',
      }),
    ).toMatchObject({ placement: 'quiet-hold', notBefore: '2026-10-21T12:00:00.000+08:00' });
    expect(() => preview('2026-02-30T07:00:00+08:00', '2026-10-21T07:00:00+08:00')).toThrow('明确时刻');
    expect(() => preview('2026-10-21T07:00:00', '2026-10-21T07:00:00+08:00')).toThrow('明确时刻');
  });
  it('keeps K2 fixed at the next Beijing 08:00 with custom DND and across midnight', () => {
    expect(
      previewNoticePolicy({
        kind: 'explicit-reminder',
        dueAt: '2026-10-21T08:00:00+08:00',
        now: new Date('2026-10-21T10:00:00+08:00'),
        dndStart: '09:00',
        dndEnd: '12:00',
      }),
    ).toMatchObject({ placement: 'quiet-hold', notBefore: '2026-10-22T08:00:00.000+08:00' });
    expect(preview('2026-10-20T22:00:00+08:00', '2026-10-21T00:00:00+08:00')).toMatchObject({
      placement: 'quiet-hold',
      notBefore: '2026-10-21T08:00:00.000+08:00',
    });
  });
});
