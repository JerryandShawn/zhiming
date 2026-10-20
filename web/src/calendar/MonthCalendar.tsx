import { useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';
import { dateLabel, monthDays, moveMonth, statusMessage, type CalendarSource, type DayNote } from './data';

function Markers({ note }: { note: DayNote }) {
  return (
    <>
      {note.holiday === 'rest' && <span className="calendar-mark jade-text">休</span>}
      {note.holiday === 'work' && <span className="calendar-mark amber-text">班</span>}
      {[...(note.festivals ?? []), ...(note.terms ?? [])].map((name, index) => (
        <span className="calendar-festival" key={`${name}-${index}`}>
          {name}
        </span>
      ))}
      <span className="calendar-dots">
        {Boolean(note.terms?.length) && <span className="calendar-term" aria-hidden="true" />}
        {Boolean(note.arrangements?.length) && (
          <span className="calendar-event" role="img" aria-label={note.arrangements!.join('、')} />
        )}
      </span>
    </>
  );
}
export function CalendarLegend() {
  return (
    <p className="meta calendar-legend">
      <span>
        <span className="jade-text">休</span> 法定假日
      </span>
      <span>
        <span className="amber-text">班</span> 调休上班
      </span>
      <span>
        <span className="calendar-legend-dot term" aria-hidden="true" /> 节气
      </span>
      <span className="gold-text">古金字 · 节日</span>
      <span>
        <span className="calendar-legend-dot event" aria-hidden="true" /> 你的安排
      </span>
    </p>
  );
}
export function MonthCalendar({
  today,
  selected = today,
  onSelect,
  source,
}: {
  today: string;
  selected?: string;
  onSelect?: (date: string) => void;
  source: CalendarSource;
}) {
  const [view, setView] = useState({ selected, month: selected.slice(0, 7) });
  // Remember each new selection, so returning to a previously selected day also
  // returns to its month instead of reviving an old browsing month.
  if (view.selected !== selected) setView({ selected, month: selected.slice(0, 7) });
  const month = view.selected === selected ? view.month : selected.slice(0, 7);
  const [year, number] = month.split('-').map(Number);
  const data = source(month);
  const notice = statusMessage(data);
  return (
    <section
      className="mini-calendar"
      aria-label={`${year}年${number}月日历`}
      data-calendar-source={data.source}
      data-holiday-status={data.holidayStatus}>
      <div className="row between">
        <h3 className="row">
          <CalendarDays className="icon" />
          {year}年{number}月
        </h3>
        {onSelect ? (
          <div className="row calendar-navigation">
            {([-1, 1] as const).map((delta) => (
              <button
                type="button"
                key={delta}
                className="icon-button"
                aria-label={delta < 0 ? '上个月' : '下个月'}
                onClick={() => setView({ selected, month: moveMonth(month, delta) })}>
                {delta < 0 ? <ChevronLeft className="icon" /> : <ChevronRight className="icon" />}
              </button>
            ))}
          </div>
        ) : (
          <a href="#/settings/reports" className="icon-button" aria-label="查看报告与提醒">
            <ChevronRight className="icon" />
          </a>
        )}
      </div>
      {data.source === 'synthetic' && <p className="meta">合成日历示例 · 不代表真实安排</p>}
      {notice && (
        <p className="meta" role="status">
          {notice}
        </p>
      )}
      <div className="calendar-grid">
        {['一', '二', '三', '四', '五', '六', '日'].map((day) => (
          <span className="meta" key={day}>
            {day}
          </span>
        ))}
        {monthDays(month).map(({ day, inside, date }) => {
          const note = inside ? (data.notes[date] ?? {}) : {};
          const chosen = Boolean(onSelect) && date === selected;
          const className = `calendar-day ${date === today ? 'today' : ''} ${inside ? '' : 'outside'} ${chosen ? 'selected' : ''}`;
          const visibleName = [
            String(day),
            note.holiday === 'rest' ? '休' : note.holiday === 'work' ? '班' : '',
            ...(note.festivals ?? []),
            ...(note.terms ?? []),
          ]
            .filter(Boolean)
            .join(' ');
          const content = (
            <>
              {day}
              <Markers note={note} />
            </>
          );
          const attributes = {
            className,
            'data-date': date,
            'aria-current': date === today ? ('date' as const) : undefined,
            'aria-label': onSelect ? `${dateLabel(date, note)} ${visibleName}` : dateLabel(date, note),
          };
          return onSelect ? (
            <button type="button" key={date} {...attributes} aria-pressed={chosen} onClick={() => onSelect(date)}>
              {content}
            </button>
          ) : (
            <div key={date} role="group" {...attributes}>
              {content}
            </div>
          );
        })}
      </div>
      <CalendarLegend />
    </section>
  );
}
