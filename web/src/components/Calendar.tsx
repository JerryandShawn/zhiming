import { CalendarDays, ChevronRight } from 'lucide-react';
import { Tag } from './ui/Controls';

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

export function MiniCalendar() {
  const days = Array.from({ length: 35 }, (_, index) => index - 2);
  return (
    <section className="mini-calendar" aria-label="2026年10月日历">
      <div className="row between">
        <h3 className="row">
          <CalendarDays className="icon" />
          2026年10月
        </h3>
        <a href="#/settings/reports" className="icon-button" aria-label="查看报告与提醒">
          <ChevronRight className="icon" />
        </a>
      </div>
      <div className="calendar-grid">
        {['一', '二', '三', '四', '五', '六', '日'].map((day) => (
          <span className="meta" key={day}>
            {day}
          </span>
        ))}
        {days.map((day) => (
          <div
            key={day}
            className={`calendar-day ${day === 17 ? 'today' : ''} ${day < 1 || day > 31 ? 'outside' : ''}`}
            aria-current={day === 17 ? 'date' : undefined}>
            {day < 1 ? day + 30 : day > 31 ? day - 31 : day}
            {day >= 1 && day <= 7 && <span className="calendar-mark jade-text">休</span>}
            {day === 10 && <span className="calendar-mark gold-text">班</span>}
            {[1, 8, 18, 23].includes(day) && (
              <span className="calendar-festival">{{ 1: '国庆', 8: '寒露', 18: '重阳', 23: '霜降' }[day]}</span>
            )}
            {day === 21 && <span className="calendar-event" role="img" aria-label="面试安排" />}
          </div>
        ))}
      </div>
      <p className="meta">休 · 法定假日 · 班 · 调休上班</p>
    </section>
  );
}
