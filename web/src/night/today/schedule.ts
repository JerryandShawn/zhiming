import { beijingDateKey } from '../../time/beijing';
import type { SettingsSnapshot } from '../settings/types';
import { previewNoticePolicy } from './policy';

export type TodayPlan = { id: string; kind: 'followup' | 'explicit-reminder'; title: string; dueAt: string };
export type TodayPlanView = TodayPlan & { placement: string; note: string };

/** All records are synthetic. This is the single replacement point for a future reminder reader. */
export function createTodaySchedule(date: string): TodayPlan[] {
  const noon = Date.parse(`${date}T12:00:00+08:00`);
  if (!Number.isFinite(noon)) return [];
  const yesterday = beijingDateKey(new Date(noon - 24 * 60 * 60 * 1000));
  return [
    {
      id: 'demo-reminder-today',
      kind: 'explicit-reminder',
      title: '核对出门清单（合成）',
      dueAt: `${date}T09:00:00+08:00`,
    },
    { id: 'demo-followup-today', kind: 'followup', title: '回看项目进展（合成）', dueAt: `${date}T18:30:00+08:00` },
    {
      id: 'demo-reminder-overdue',
      kind: 'explicit-reminder',
      title: '查看尚未处理的提醒（合成）',
      dueAt: `${yesterday}T18:00:00+08:00`,
    },
  ];
}

export function todaySchedule(now: Date, settings: SettingsSnapshot, records?: readonly TodayPlan[]): TodayPlanView[] {
  if (!Number.isFinite(now.getTime())) return [];
  const source = records ?? createTodaySchedule(beijingDateKey(now));
  return source.map((item) => {
    if (
      item.kind === 'followup' &&
      (!settings.contact.followup || settings.contact.disabledCategories.includes('followup'))
    )
      return { ...item, placement: 'paused', note: '主动跟进已关闭，只在这里查看。' };
    const result = previewNoticePolicy({
      kind: item.kind,
      dueAt: item.dueAt,
      now,
      dndStart: settings.contact.dndStart,
      dndEnd: settings.contact.dndEnd,
    });
    return { ...item, placement: result.placement, note: result.message };
  });
}

export function morningReportNote(date: string, settings: SettingsSnapshot): string {
  const report = settings.reports.schedules.find(({ kind }) => kind === 'daily');
  if (!report?.enabled) return '晨报已暂停；你仍可以手动查看今日页。';
  return `晨报按北京时间 ${report.time} 订阅，不受免打扰时段限制。此页仅预览，不会发送。${date ? '' : '请先核对本地时间。'}`;
}
