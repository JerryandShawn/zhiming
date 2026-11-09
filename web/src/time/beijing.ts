export const BEIJING_TIME_ZONE = 'Asia/Shanghai';
export type Clock = { now: () => Date };
export const systemClock: Clock = { now: () => new Date() };

export function beijingTimestamp(date: Date): string {
  if (!Number.isFinite(date.getTime())) throw new RangeError('时间无效');
  return new Date(date.getTime() + 8 * 60 * 60 * 1000).toISOString().replace('Z', '+08:00');
}

export function beijingDateKey(date: Date): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: BEIJING_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date);
  const part = (name: string) => parts.find((entry) => entry.type === name)!.value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}
