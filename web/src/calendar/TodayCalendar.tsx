import { useEffect, useState } from 'react';
import { CalendarDays } from 'lucide-react';
import { Button } from '../components/ui/Controls';
import { DeferredPanel } from '../components/ui/DeferredPanel';
import { MonthCalendar } from './MonthCalendar';
import { dateLabel, unavailableCalendar, type CalendarSource } from './data';

export function TodayCalendar({ today, source = unavailableCalendar }: { today: string; source?: CalendarSource }) {
  const [selected, setSelected] = useState(today);
  const [desktop, setDesktop] = useState(() => window.matchMedia('(min-width: 1024px)').matches);
  useEffect(() => {
    const media = window.matchMedia('(min-width: 1024px)');
    const update = () => setDesktop(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  const data = source(selected.slice(0, 7));
  const note = data.notes[selected] ?? {};
  const content = (
    <>
      <MonthCalendar today={today} selected={selected} onSelect={setSelected} source={source} />
      <div className="stack small calendar-selection" role="group" aria-label="所选日期详情">
        <p className="small-text">{dateLabel(selected, note)}</p>
        {data.holidayStatus !== 'covered' && <p className="meta">该日的节假日与安排数据尚未载入。</p>}
        {selected !== today && (
          <Button variant="ghost" onClick={() => setSelected(today)}>
            回到今天
          </Button>
        )}
        {data.source === 'synthetic' ? (
          <p className="meta">这里只浏览合成日历，选择不会改变排盘或保存安排。</p>
        ) : (
          <a className="text-link quiet-link" href={`#/chart?tab=bazi&date=${selected}`}>
            查看该日命盘
          </a>
        )}
      </div>
    </>
  );
  return desktop ? (
    <div className="today-calendar">{content}</div>
  ) : (
    <div className="today-calendar-entry">
      <DeferredPanel
        title="本月日历"
        description="公历日期、节气节日与已载入的安排；未提供的数据会明确说明。"
        sheet
        renderTrigger={(triggerProps) => (
          <Button {...triggerProps}>
            <CalendarDays className="icon" />
            查看本月日历
          </Button>
        )}>
        {content}
      </DeferredPanel>
    </div>
  );
}
