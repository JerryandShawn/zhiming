import { useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';
import { Tag } from './ui/Controls';

export const exampleToday = '2026-10-17';
type DayNote = { holiday?: boolean; work?: boolean; festival?: string; term?: string };
const october: Record<number, DayNote> = {
  1: { holiday: true, festival: '国庆' },
  2: { holiday: true },
  3: { holiday: true },
  4: { holiday: true },
  5: { holiday: true },
  6: { holiday: true },
  7: { holiday: true },
  8: { term: '寒露' },
  10: { work: true },
  18: { festival: '重阳' },
  23: { term: '霜降' },
};

export function NowCard() {
  return (
    <section className="now-card" aria-label="此刻">
      <p className="meta">此刻</p>
      <h2>10月17日 星期六</h2>
      <p className="small-text secondary-text">农历九月初八 · 甲子日</p>
      <div className="row wrap">
        <Tag tone="rest">周末休息</Tag>
        <Tag tone="festival">明天重阳</Tag>
      </div>
      <p className="meta">霜降 10月23日 · 元旦还有76天</p>
      <p className="meta">2027年放假安排尚未公布</p>
    </section>
  );
}

function monthDays(year: number, month: number) {
  const offset = (new Date(Date.UTC(year, month - 1, 1)).getUTCDay() + 6) % 7;
  const length = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return Array.from({ length: Math.ceil((offset + length) / 7) * 7 }, (_, index) => {
    const date = new Date(Date.UTC(year, month - 1, index - offset + 1));
    return { day: date.getUTCDate(), inside: date.getUTCMonth() === month - 1, date: date.toISOString().slice(0, 10) };
  });
}

export function MiniCalendar({
  selected = exampleToday,
  onSelect,
}: {
  selected?: string;
  onSelect?: (date: string) => void;
}) {
  const [month, setMonth] = useState(selected.slice(0, 7));
  const [year, number] = month.split('-').map(Number);
  const sample = month === '2026-10';
  const move = (offset: number) => setMonth(new Date(Date.UTC(year, number - 1 + offset, 1)).toISOString().slice(0, 7));
  return (
    <section className="mini-calendar" aria-label={`${year}年${number}月日历`}>
      <div className="row between">
        <h3 className="row">
          <CalendarDays className="icon" />
          {year}年{number}月
        </h3>
        {onSelect ? (
          <div className="row calendar-navigation">
            <button type="button" className="icon-button" aria-label="上个月" onClick={() => move(-1)}>
              <ChevronLeft className="icon" />
            </button>
            <button type="button" className="icon-button" aria-label="下个月" onClick={() => move(1)}>
              <ChevronRight className="icon" />
            </button>
          </div>
        ) : (
          <a href="#/settings/reports" className="icon-button" aria-label="查看报告与提醒">
            <ChevronRight className="icon" />
          </a>
        )}
      </div>
      {!sample && <p className="meta">{year >= 2027 ? '该年放假安排尚未公布' : '此示例未加载该月节气与放假标记'}</p>}
      <div className="calendar-grid">
        {['一', '二', '三', '四', '五', '六', '日'].map((day) => (
          <span className="meta" key={day}>
            {day}
          </span>
        ))}
        {monthDays(year, number).map(({ day, inside, date }) => {
          const note = sample && inside ? (october[day] ?? {}) : {};
          const chosen = Boolean(onSelect) && date === selected;
          const className = `calendar-day ${date === exampleToday ? 'today' : ''} ${inside ? '' : 'outside'} ${chosen ? 'selected' : ''}`;
          const content = (
            <>
              {day}
              {note.holiday && <span className="calendar-mark jade-text">休</span>}
              {note.work && <span className="calendar-mark amber-text">班</span>}
              {(note.festival || note.term) && <span className="calendar-festival">{note.festival ?? note.term}</span>}
              {note.term && <span className="calendar-term" aria-hidden="true" />}
              {sample && day === 21 && inside && <span className="calendar-event" role="img" aria-label="面试安排" />}
            </>
          );
          return onSelect ? (
            <button
              type="button"
              key={date}
              className={className}
              data-date={date}
              aria-pressed={chosen}
              aria-current={date === exampleToday ? 'date' : undefined}
              aria-label={`${date}${note.holiday ? ' 法定假日' : ''}${note.work ? ' 调休上班' : ''}${note.festival ? ` ${note.festival}` : ''}${note.term ? ` ${note.term}` : ''}`}
              onClick={() => onSelect(date)}>
              {content}
            </button>
          ) : (
            <div key={date} className={className} aria-current={date === exampleToday ? 'date' : undefined}>
              {content}
            </div>
          );
        })}
      </div>
      <p className="meta calendar-legend">休 · 法定假日 · 班 · 调休上班 · 古金圆点为节气</p>
    </section>
  );
}
