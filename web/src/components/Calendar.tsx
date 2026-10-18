import { Tag } from './ui/Controls';
import { MonthCalendar } from '../calendar/MonthCalendar';
import { exampleCalendar, exampleToday } from '../calendar/examples';
export { exampleToday } from '../calendar/examples';

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

export function MiniCalendar({
  selected = exampleToday,
  onSelect,
}: {
  selected?: string;
  onSelect?: (date: string) => void;
}) {
  return <MonthCalendar today={exampleToday} selected={selected} onSelect={onSelect} source={exampleCalendar} />;
}
