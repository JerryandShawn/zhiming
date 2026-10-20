import { validDate } from '../../calendar/data';
import { beijingDateKey, beijingTimestamp, BEIJING_TIME_ZONE } from '../../time/beijing';

export type NoticePolicyInput = {
  kind: 'daily' | 'followup' | 'explicit-reminder';
  dueAt: string;
  now: Date;
  dndStart?: string;
  dndEnd?: string;
};
export type NoticePolicy = {
  placement: 'ready' | 'scheduled' | 'quiet-hold' | 'inbox-only';
  lateMinutes: number;
  message: string;
  notBefore?: string;
};
const timePattern = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const minutes = (value: string) => Number(value.slice(0, 2)) * 60 + Number(value.slice(3));

/** K1/K2 display preview only: this function has no sender, persistence or notification permission. */
export function previewNoticePolicy(input: NoticePolicyInput): NoticePolicy {
  const start = input.dndStart ?? '22:00',
    end = input.dndEnd ?? '08:00';
  const due = Date.parse(input.dueAt),
    now = input.now.getTime();
  if (
    !['daily', 'followup', 'explicit-reminder'].includes(input.kind) ||
    !Number.isFinite(due) ||
    !Number.isFinite(now) ||
    !validDate(input.dueAt.split('T')[0]) ||
    !/T(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?:Z|[+-](?:0\d|1[0-4]):[0-5]\d)$/.test(input.dueAt) ||
    !timePattern.test(start) ||
    !timePattern.test(end) ||
    start === end
  )
    throw new Error('请核对明确时刻与免打扰时段。');
  const lateMs = Math.max(0, now - due),
    lateMinutes = Math.ceil(lateMs / 60000);
  if (now < due)
    return {
      placement: 'scheduled',
      lateMinutes: 0,
      message: '尚未到设定时间。',
      notBefore: beijingTimestamp(new Date(due)),
    };
  if (input.kind === 'daily')
    return { placement: 'ready', lateMinutes, message: '晨报按你设定的时间安排，不受免打扰限制；这里只预览。' };
  if (input.kind === 'explicit-reminder' && lateMs > 12 * 60 * 60000)
    return { placement: 'inbox-only', lateMinutes, message: '已迟到超过12小时，仅在应用内显示，不再推送。' };
  const local = new Intl.DateTimeFormat('en-GB', {
    timeZone: BEIJING_TIME_ZONE,
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(input.now);
  const current = minutes(local),
    from = minutes(start),
    to = minutes(end);
  const quiet = from < to ? current >= from && current < to : current >= from || current < to;
  if (quiet && (input.kind === 'followup' || lateMs > 60 * 60000)) {
    // K2 explicitly fixes overdue reminders at 08:00; ordinary follow-ups use the user's quiet end.
    const resumeTime = input.kind === 'explicit-reminder' ? '08:00' : end;
    let next = Date.parse(`${beijingDateKey(input.now)}T${resumeTime}:00+08:00`);
    if (next <= now) next += 24 * 60 * 60000;
    return {
      placement: 'quiet-hold',
      lateMinutes,
      message: '免打扰中，预览为时段结束后处理。',
      notBefore: beijingTimestamp(new Date(next)),
    };
  }
  return {
    placement: 'ready',
    lateMinutes,
    message:
      input.kind === 'explicit-reminder'
        ? `${lateMs > 0 ? `晚了 ${lateMinutes} 分钟；` : ''}明确提醒按约定时刻安排，免打扰不拦截；这里只预览。`
        : '当前不在免打扰时段；这里只预览跟进安排。',
  };
}
