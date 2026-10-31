import { afterEach, describe, expect, it, vi } from 'vitest';
import { createSettingsPort } from '../src/night/settings/port';
import { schedulePayload, scheduleReceipt, validSchedules } from '../src/live/ReportSchedule';
import { createOnboardingController } from '../src/night/onboarding/controller';
import { createBirthPort } from '../src/night/onboarding/birth';
import { createAboutMeStore } from '../src/night/me/port';
import type { SettingsCommand } from '../src/night/settings/types';

afterEach(() => vi.restoreAllMocks());
describe('local settings policies', () => {
  it('seeds four contract-compatible reports and stable immutable snapshots', () => {
    const port = createSettingsPort(),
      first = port.getSnapshot();
    expect(validSchedules(first.reports)).toBe(true);
    for (const report of first.reports.schedules) expect(scheduleReceipt(report, report.kind, report)).toBe(true);
    expect(first.reports.schedules.map((report) => [report.kind, report.enabled, report.time])).toEqual([
      ['daily', true, '07:00'],
      ['weekly', true, '07:00'],
      ['monthly', false, '07:00'],
      ['quarterly', false, '07:00'],
    ]);
    expect(port.getSnapshot()).toBe(first);
    expect(() => first.devices.pop()).toThrow();
    expect(first.mode).toBe('local-demo');
  });
  it.each(['daily', 'weekly', 'monthly', 'quarterly'] as const)(
    'saves %s with the existing exact payload and projected receipt contract',
    async (kind) => {
      const port = createSettingsPort(),
        before = port.getSnapshot();
      const draft = {
        enabled: true,
        time: '09:30',
        ...(kind === 'weekly' ? { weekday: 7 } : {}),
        ...(['monthly', 'quarterly'].includes(kind) ? { day: 'last' as const } : {}),
      };
      const result = await port.execute({ type: 'report-save', kind, draft, expectedRevision: 1, requestId: kind });
      expect(result.report).toBeDefined();
      expect(scheduleReceipt(result.report!, kind, draft)).toBe(true);
      expect(schedulePayload(kind, 1, draft)).toEqual({
        kind,
        expected_revision: 1,
        enabled: true,
        time: '09:30',
        ...(kind === 'weekly' ? { weekday: 7 } : {}),
        ...(['monthly', 'quarterly'].includes(kind) ? { day: 'last' } : {}),
      });
      expect(result.report?.revision).toBe(2);
      for (const other of before.reports.schedules.filter((report) => report.kind !== kind))
        expect(port.getSnapshot().reports.schedules.find((report) => report.kind === other.kind)).toEqual(other);
    },
  );
  it('preserves the exact idempotent result and rejects changed intent or stale CAS without mutation', async () => {
    const port = createSettingsPort(),
      listener = vi.fn();
    port.subscribe(listener);
    const command: SettingsCommand = {
      type: 'report-save',
      kind: 'daily',
      expectedRevision: 1,
      requestId: 'save',
      draft: { enabled: false, time: '08:00' },
    };
    const receipt = await port.execute(command),
      before = port.getSnapshot();
    expect(await port.execute(command)).toBe(receipt);
    await expect(port.execute({ ...command, draft: { enabled: true, time: '09:00' } })).rejects.toMatchObject({
      code: 'REPLAY_CHANGED',
      status: 409,
    });
    await expect(port.execute({ ...command, requestId: 'stale' })).rejects.toMatchObject({ status: 409 });
    expect(port.getSnapshot()).toBe(before);
    expect(listener).toHaveBeenCalledTimes(1);
  });
  it('applies DND only to follow-up policy and keeps every designated report time unchanged', async () => {
    const port = createSettingsPort(),
      reports = port.getSnapshot().reports;
    await port.execute({
      type: 'contact-save',
      expectedRevision: 1,
      requestId: 'dnd',
      draft: { followup: false, dailyCap: 3, dndStart: '21:00', dndEnd: '09:00', disabledCategories: ['health'] },
    });
    expect(port.getSnapshot().reports).toEqual(reports);
    expect(port.getSnapshot().contact).toMatchObject({ revision: 2, dailyCap: 3, followup: false, dndStart: '21:00' });
  });
  it.each([0, 4])('rejects an invalid follow-up cap %s without saving', async (dailyCap) => {
    const port = createSettingsPort(),
      before = port.getSnapshot();
    await expect(
      port.execute({
        type: 'contact-save',
        expectedRevision: 1,
        requestId: 'invalid',
        draft: { ...before.contact, dailyCap },
      } as SettingsCommand),
    ).rejects.toMatchObject({ status: 422 });
    expect(port.getSnapshot()).toBe(before);
  });
  it('preserves saved DND and daily cap when onboarding opts out while disabling all contact', async () => {
    const port = createSettingsPort();
    await port.execute({
      type: 'contact-save',
      requestId: 'custom-contact-before-opt-out',
      expectedRevision: 1,
      draft: { followup: true, dailyCap: 3, dndStart: '23:15', dndEnd: '07:45', disabledCategories: ['health'] },
    });
    const receipt = await port.applyContactPreference({ requestId: 'off-preserves-policy', choice: 'off' });
    expect(port.getSnapshot().contact).toMatchObject({
      revision: 3,
      followup: false,
      dailyCap: 3,
      dndStart: '23:15',
      dndEnd: '07:45',
      disabledCategories: ['health'],
    });
    expect(receipt.projection).toMatchObject({
      followup: false,
      dailyEnabled: false,
      dailyCap: 3,
      dndStart: '23:15',
      dndEnd: '07:45',
    });
    expect(port.getSnapshot().reports.schedules.every((report) => !report.enabled)).toBe(true);
  });
  it('shares typed onboarding choices, closes every report on opt-out, and preserves other report choices on opt-in', async () => {
    const port = createSettingsPort(),
      preference = { requestId: 'intro-off', choice: 'off' as const };
    const ack = await port.applyContactPreference(preference);
    expect(ack.projection).toMatchObject({ followup: false, dailyEnabled: false, local: true });
    expect(port.getSnapshot().reports.schedules.every((report) => !report.enabled)).toBe(true);
    expect(await port.applyContactPreference(preference)).toBe(ack);
    await expect(port.applyContactPreference({ ...preference, choice: 'allow' })).rejects.toMatchObject({
      status: 409,
    });
    await port.applyContactPreference({ requestId: 'intro-custom', choice: 'custom-time', time: '09:30' });
    expect(port.readContactPreference()).toMatchObject({ time: '09:30', dailyEnabled: true, followup: true });
    expect(
      port
        .getSnapshot()
        .reports.schedules.filter((item) => item.kind !== 'daily')
        .every((item) => !item.enabled),
    ).toBe(true);
  });
  it('revokes only a known remote mock device and never revokes the current one', async () => {
    const port = createSettingsPort();
    await expect(
      port.execute({ type: 'device-revoke', id: 'mock-current', expectedRevision: 1, requestId: 'current' }),
    ).rejects.toMatchObject({ status: 422 });
    await expect(
      port.execute({ type: 'device-revoke', id: 'unknown', expectedRevision: 1, requestId: 'unknown' }),
    ).rejects.toMatchObject({ status: 404 });
    const command: SettingsCommand = {
      type: 'device-revoke',
      id: 'mock-phone',
      expectedRevision: 1,
      requestId: 'phone',
    };
    const result = await port.execute(command);
    expect(result.device).toMatchObject({ id: 'mock-phone', status: 'revoked', revision: 2 });
    expect(await port.execute(command)).toBe(result);
    expect(port.getSnapshot().devices.find((item) => item.current)?.status).toBe('active');
  });
  it('ends only the local demo, blocks new writes and retains previous idempotent receipts without touching auth', async () => {
    const port = createSettingsPort(),
      fetcher = vi.spyOn(globalThis, 'fetch'),
      set = vi.spyOn(Storage.prototype, 'setItem'),
      remove = vi.spyOn(Storage.prototype, 'removeItem');
    const command: SettingsCommand = { type: 'local-logout', expectedRevision: 1, requestId: 'local-exit' };
    const result = await port.execute(command);
    expect(port.getSnapshot().localSessionEnded).toBe(true);
    expect(await port.execute(command)).toBe(result);
    await expect(
      port.execute({ type: 'device-revoke', id: 'mock-phone', expectedRevision: 1, requestId: 'after-exit' }),
    ).rejects.toMatchObject({ status: 409 });
    expect(fetcher).not.toHaveBeenCalled();
    expect(set).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
  });
});

describe('typed onboarding/settings shared contact acknowledgement', () => {
  function setup() {
    const settings = createSettingsPort(),
      aboutMe = createAboutMeStore(),
      birth = createBirthPort();
    const controller = createOnboardingController({
      aboutMe,
      birth,
      onContactPreference: settings.applyContactPreference,
      readContactPreference: settings.readContactPreference,
    });
    controller.start('known');
    controller.continue();
    controller.skip();
    controller.skip();
    controller.skip();
    expect(controller.getSnapshot().step).toBe('outreach');
    return { settings, controller, aboutMe };
  }
  it('uses the same typed opt-out policy in both settings and the onboarding summary', async () => {
    const { settings, controller } = setup();
    await controller.submit('先别主动找我');
    expect(controller.getSnapshot().step).toBe('summary');
    expect(controller.getSnapshot().prompt.text).toContain('晨报已关闭，跟进关闭');
    expect(settings.getSnapshot().reports.schedules.every((item) => !item.enabled)).toBe(true);
  });
  it('refreshes the paused summary from typed shared settings after a manual change', async () => {
    const { settings, controller } = setup();
    await controller.submit('可以');
    controller.pause();
    const daily = settings.getSnapshot().reports.schedules[0];
    await settings.execute({
      type: 'report-save',
      kind: 'daily',
      expectedRevision: daily.revision,
      requestId: 'manual-daily',
      draft: { enabled: true, time: '10:00' },
    });
    controller.resume();
    expect(controller.getSnapshot().prompt.text).toContain('晨报10:00');
    expect(controller.getSnapshot().messages.at(-1)?.text).toBe(controller.getSnapshot().prompt.text);
  });
  it('does not advance on an invalid contact acknowledgement and safely retries the original operation', async () => {
    const settings = createSettingsPort(),
      aboutMe = createAboutMeStore();
    let first = true;
    const callback = vi.fn(async (preference: Parameters<typeof settings.applyContactPreference>[0]) => {
      const receipt = await settings.applyContactPreference(preference);
      if (first) {
        first = false;
        return { ...receipt, requestId: 'other' };
      }
      return receipt;
    });
    const controller = createOnboardingController({ aboutMe, birth: createBirthPort(), onContactPreference: callback });
    controller.start('known');
    controller.continue();
    controller.skip();
    controller.skip();
    controller.skip();
    await controller.submit('可以');
    expect(controller.getSnapshot()).toMatchObject({ step: 'outreach', hasPending: true });
    const revision = settings.getSnapshot().revision;
    await controller.submit('可以');
    expect(controller.getSnapshot().step).toBe('summary');
    expect(callback.mock.calls[0][0]).toEqual(callback.mock.calls[1][0]);
    expect(settings.getSnapshot().revision).toBe(revision);
  });
});
