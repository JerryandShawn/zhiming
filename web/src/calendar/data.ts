export type DayNote = {
  holiday?: 'rest' | 'work';
  festivals?: string[];
  terms?: string[];
  arrangements?: string[];
};
export type CalendarMonthData = {
  source: 'synthetic' | 'verified' | 'unavailable';
  holidayStatus: 'covered' | 'unknown' | 'unpublished';
  notes: Record<string, DayNote>;
};
export type CalendarSource = (month: string) => CalendarMonthData;

export function validDate(value: string) {
  if (!/^\d{4}-\d\d-\d\d$/.test(value)) return false;
  const parsed = new Date(`${value}T12:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}
export function monthDays(month: string) {
  const [year, number] = month.split('-').map(Number);
  const offset = (new Date(Date.UTC(year, number - 1, 1)).getUTCDay() + 6) % 7;
  const count = new Date(Date.UTC(year, number, 0)).getUTCDate();
  return Array.from({ length: Math.ceil((offset + count) / 7) * 7 }, (_, index) => {
    const value = new Date(Date.UTC(year, number - 1, index - offset + 1));
    return {
      day: value.getUTCDate(),
      inside: value.getUTCMonth() === number - 1,
      date: value.toISOString().slice(0, 10),
    };
  });
}
export function moveMonth(month: string, delta: number) {
  const [year, number] = month.split('-').map(Number);
  return new Date(Date.UTC(year, number - 1 + delta, 1)).toISOString().slice(0, 7);
}
export function dateLabel(date: string, note: DayNote) {
  return [
    date,
    note.holiday === 'rest' ? '法定假日' : note.holiday === 'work' ? '调休上班' : '',
    ...(note.festivals ?? []),
    ...(note.terms ?? []),
    ...(note.arrangements?.length ? [`你的安排：${note.arrangements.join('、')}`] : []),
  ]
    .filter(Boolean)
    .join(' ');
}
export function statusMessage(data: CalendarMonthData) {
  if (data.holidayStatus === 'unpublished') return '该年放假安排尚未公布';
  if (data.source === 'unavailable') return '节假日、节气、节日及你的安排尚未接入，当前仅显示公历。';
  if (data.holidayStatus === 'unknown') return '该月节假日与调休数据暂未载入。';
  return '';
}
// A missing transport is not an empty schedule or proof that an official year is unpublished.
export const unavailableCalendar: CalendarSource = () => ({
  source: 'unavailable',
  holidayStatus: 'unknown',
  notes: {},
});
