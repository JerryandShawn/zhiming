import type { CalendarSource, DayNote } from './data';

export const exampleToday = '2026-10-17';
const october: Record<string, DayNote> = Object.fromEntries(
  Array.from({ length: 7 }, (_, index) => [`2026-10-0${index + 1}`, { holiday: 'rest' }]),
);
Object.assign(october, {
  '2026-10-01': { holiday: 'rest', festivals: ['国庆'] },
  '2026-10-08': { terms: ['寒露'] },
  '2026-10-10': { holiday: 'work' },
  '2026-10-18': { festivals: ['重阳'] },
  '2026-10-21': { arrangements: ['面试安排'] },
  '2026-10-23': { terms: ['霜降'] },
});
// These are frozen design fixtures, including an explicitly unpublished example year.
// Publication status is fixture metadata, never inferred from the current year.
const exampleYears: Record<string, 'unpublished' | undefined> = { '2027': 'unpublished' };
export const exampleCalendar: CalendarSource = (month) => ({
  source: 'synthetic',
  holidayStatus: month === '2026-10' ? 'covered' : (exampleYears[month.slice(0, 4)] ?? 'unknown'),
  notes: month === '2026-10' ? october : {},
});
export const todayExampleCalendar: CalendarSource = (month) => {
  const data = exampleCalendar(month);
  return month === '2026-10'
    ? { ...data, notes: { ...data.notes, '2026-10-23': { terms: ['霜降'], arrangements: ['合成复盘安排'] } } }
    : data;
};
