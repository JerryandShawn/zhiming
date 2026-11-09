import { schedulePayload, scheduleReceipt } from '../../live/ReportSchedule';
import type { ReportKind, Schedule } from '../../live/types';
import { AboutMeError } from '../me/types';
import type {
  ContactDraft,
  ContactPreferenceReceipt,
  OnboardingContactPreference,
  ReportDraft,
  SettingsCommand,
  SettingsPort,
  SettingsReceipt,
  SettingsSnapshot,
} from './types';

const kinds: ReportKind[] = ['daily', 'weekly', 'monthly', 'quarterly'];
const timePattern = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
function freeze<T>(value: T): T {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}
function signature(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(signature).join(',')}]`;
  if (value && typeof value === 'object')
    return `{${Object.entries(value)
      .filter(([, item]) => item !== undefined)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${signature(item)}`)
      .join(',')}}`;
  return JSON.stringify(value) ?? 'null';
}
function report(kind: ReportKind): Schedule {
  return {
    kind,
    revision: 1,
    enabled: kind === 'daily' || kind === 'weekly',
    time: '07:00',
    ...(kind === 'weekly' ? { weekday: 1 } : {}),
    ...(['monthly', 'quarterly'].includes(kind) ? { day: 1 } : {}),
    status: kind === 'daily' || kind === 'weekly' ? 'active' : 'paused',
    status_reason: '本地合成设置，不会投递真实报告。',
    configured: true,
    can_modify: true,
    next_prepare: null,
    next_delivery: null,
    receipt: { id: kind, kind: 'report_schedule', revision: 1, write_status: 'saved' },
  };
}
function saveReport(current: Schedule, draft: ReportDraft): Schedule {
  if (typeof draft.enabled !== 'boolean' || !timePattern.test(draft.time))
    throw new AboutMeError('INVALID', 422, '请核对报告开关与HH:mm时间。');
  if (current.kind === 'weekly' && (!Number.isInteger(draft.weekday) || draft.weekday! < 1 || draft.weekday! > 7))
    throw new AboutMeError('INVALID', 422, '周报星期需要1至7。');
  if (
    ['monthly', 'quarterly'].includes(current.kind) &&
    draft.day !== 'last' &&
    (!Number.isInteger(draft.day) || Number(draft.day) < 1 || Number(draft.day) > 28)
  )
    throw new AboutMeError('INVALID', 422, '报告日期需要1至28日或月末。');
  const payload = schedulePayload(current.kind, current.revision, draft);
  const next: Schedule = {
    ...current,
    enabled: payload.enabled === true,
    time: String(payload.time),
    revision: current.revision + 1,
    status: payload.enabled ? 'active' : 'paused',
    receipt: { id: current.kind, kind: 'report_schedule', revision: current.revision + 1, write_status: 'saved' },
  };
  if (current.kind === 'weekly') next.weekday = Number(payload.weekday);
  if (current.kind === 'monthly' || current.kind === 'quarterly') next.day = payload.day as number | 'last';
  if (!scheduleReceipt(next, current.kind, draft)) throw new AboutMeError('INVALID', 502, '没有匹配的报告保存回执。');
  return next;
}
function validateContact(draft: ContactDraft) {
  if (
    typeof draft.followup !== 'boolean' ||
    ![1, 2, 3].includes(draft.dailyCap) ||
    !timePattern.test(draft.dndStart) ||
    !timePattern.test(draft.dndEnd) ||
    draft.dndStart === draft.dndEnd ||
    !Array.isArray(draft.disabledCategories) ||
    draft.disabledCategories.some((value) => typeof value !== 'string' || !value.trim() || value.length > 60)
  )
    throw new AboutMeError('INVALID', 422, '请核对跟进开关、每日1至3条上限和不同的免打扰起止时间。');
}
function checkRevision(actual: number, expected: number) {
  if (!Number.isInteger(expected) || actual !== expected)
    throw new AboutMeError('CONFLICT', 409, '设置已变化，草稿保留；请读取最新设置并核对。');
}

// In-memory policies only. No authenticated transport or device/session token is used.
export function createSettingsPort(): SettingsPort {
  let snapshot: SettingsSnapshot = freeze({
    mode: 'local-demo',
    revision: 1,
    reports: { timezone: 'Asia/Shanghai', prepare_minutes: 15, schedules: kinds.map(report) },
    contact: { revision: 1, followup: true, dailyCap: 2, dndStart: '22:00', dndEnd: '08:00', disabledCategories: [] },
    devices: [
      {
        id: 'mock-current',
        label: '当前电脑（合成设备）',
        current: true,
        lastUsedAt: '2026-10-19T07:00:00+08:00',
        revision: 1,
        status: 'active',
      },
      {
        id: 'mock-phone',
        label: '手机（合成设备）',
        current: false,
        lastUsedAt: '2026-10-18T20:00:00+08:00',
        revision: 1,
        status: 'active',
      },
      {
        id: 'mock-tablet',
        label: '平板（合成设备）',
        current: false,
        lastUsedAt: '2026-10-17T18:00:00+08:00',
        revision: 1,
        status: 'active',
      },
    ],
    localSessionEnded: false,
  });
  const listeners = new Set<() => void>(),
    completed = new Map<string, { signature: string; receipt: unknown }>();
  function replay<T>(id: string, fingerprint: string): T | undefined {
    const old = completed.get(id);
    if (!old) return;
    if (old.signature !== fingerprint)
      throw new AboutMeError('REPLAY_CHANGED', 409, '原操作内容已经改变，请先处理原提交。');
    return old.receipt as T;
  }
  function commit<T>(id: string, fingerprint: string, next: SettingsSnapshot, receipt: T): T {
    snapshot = freeze(next);
    const result = freeze(receipt);
    completed.set(id, { signature: fingerprint, receipt: result });
    for (const listener of [...listeners]) listener();
    return result;
  }
  const readContactPreference = () => ({
    revision: snapshot.revision,
    followup: snapshot.contact.followup,
    dailyEnabled: snapshot.reports.schedules.find((item) => item.kind === 'daily')!.enabled,
    time: snapshot.reports.schedules.find((item) => item.kind === 'daily')!.time,
    dailyCap: snapshot.contact.dailyCap,
    dndStart: snapshot.contact.dndStart,
    dndEnd: snapshot.contact.dndEnd,
    local: true as const,
  });
  return {
    getSnapshot: () => snapshot,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    readContactPreference,
    async execute(command: SettingsCommand) {
      if (!command.requestId) throw new AboutMeError('INVALID', 422, '操作需要稳定编号。');
      const id = `settings:${command.requestId}`,
        fingerprint = signature(command),
        old = replay<SettingsReceipt>(id, fingerprint);
      if (old) return old;
      if (snapshot.localSessionEnded)
        throw new AboutMeError('INVALID', 409, '本地演示已退出，刷新可重新开始；真实登录未改变。');
      const next = structuredClone(snapshot),
        receipt: SettingsReceipt = {
          requestId: command.requestId,
          kind: command.type,
          write_status: 'saved',
          revision: 0,
          snapshotRevision: snapshot.revision + 1,
        };
      if (command.type === 'report-save') {
        const index = next.reports.schedules.findIndex((item) => item.kind === command.kind);
        if (index < 0) throw new AboutMeError('INVALID', 422, '报告类型无效。');
        checkRevision(next.reports.schedules[index].revision, command.expectedRevision);
        receipt.report = saveReport(next.reports.schedules[index], command.draft);
        next.reports.schedules[index] = receipt.report;
        receipt.revision = receipt.report.revision;
      } else if (command.type === 'contact-save') {
        checkRevision(next.contact.revision, command.expectedRevision);
        validateContact(command.draft);
        next.contact = {
          ...structuredClone(command.draft),
          disabledCategories: [...new Set(command.draft.disabledCategories)],
          revision: next.contact.revision + 1,
        };
        receipt.contact = next.contact;
        receipt.revision = next.contact.revision;
      } else if (command.type === 'device-revoke') {
        const device = next.devices.find((item) => item.id === command.id);
        if (!device) throw new AboutMeError('NOT_FOUND', 404, '没有这台合成设备。');
        checkRevision(device.revision, command.expectedRevision);
        if (device.current || device.status !== 'active')
          throw new AboutMeError('INVALID', 422, '当前设备不能在这里吊销，已吊销设备不能重复操作。');
        device.status = 'revoked';
        device.revision++;
        receipt.device = device;
        receipt.revision = device.revision;
        receipt.write_status = 'revoked';
      } else if (command.type === 'local-logout') {
        checkRevision(next.revision, command.expectedRevision);
        next.localSessionEnded = true;
        receipt.revision = next.revision + 1;
      } else throw new AboutMeError('INVALID', 422, '未知本地设置操作。');
      next.revision++;
      return commit(id, fingerprint, next, receipt);
    },
    async applyContactPreference(preference: OnboardingContactPreference) {
      const id = `onboarding:${preference.requestId}`,
        fingerprint = signature(preference),
        old = replay<ContactPreferenceReceipt>(id, fingerprint);
      if (old) return old;
      if (
        !preference.requestId ||
        !['allow', 'off', 'custom-time'].includes(preference.choice) ||
        (preference.choice === 'custom-time' && (!preference.time || !timePattern.test(preference.time))) ||
        snapshot.localSessionEnded
      )
        throw new AboutMeError('INVALID', 422, '请核对本地联系选择与时间。');
      const next = structuredClone(snapshot),
        enabled = preference.choice !== 'off';
      next.contact = {
        ...next.contact,
        followup: enabled,
        dndStart: preference.choice === 'off' ? next.contact.dndStart : '22:00',
        dndEnd: preference.choice === 'off' ? next.contact.dndEnd : '08:00',
        revision: next.contact.revision + 1,
      };
      next.reports.schedules = next.reports.schedules.map((item) =>
        preference.choice === 'off'
          ? saveReport(item, { ...item, enabled: false })
          : item.kind === 'daily'
            ? saveReport(item, {
                ...item,
                enabled: true,
                time: preference.choice === 'custom-time' ? preference.time! : '07:00',
              })
            : item,
      );
      next.revision++;
      // Commit before reading the projection so both surfaces share the exact saved state.
      snapshot = freeze(next);
      const receipt: ContactPreferenceReceipt = {
        requestId: preference.requestId,
        kind: 'contact-preference',
        write_status: 'saved',
        revision: next.revision,
        projection: readContactPreference(),
      };
      return commit(id, fingerprint, next, receipt);
    },
  };
}
