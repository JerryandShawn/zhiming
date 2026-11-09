import { useState } from 'react';
import { Button } from './ui/Controls';
import { Select, TimePicker } from './ui/Selection';
import { useUi } from '../state';

export function ReportOptions({ index }: { index: number }) {
  const [weekday, setWeekday] = useState('1');
  const [day, setDay] = useState('1');
  const notify = useUi((state) => state.notify);
  return (
    <div className="stack">
      <div className="field">
        发送时间
        <TimePicker label="发送时间" initial="07:00" />
      </div>
      <p className="meta">北京时间 · 提前15分钟准备</p>
      {index === 1 && (
        <div className="field">
          星期
          <Select
            label="报告星期"
            value={weekday}
            onChange={setWeekday}
            options={['一', '二', '三', '四', '五', '六', '日'].map((label, number) => ({
              value: String(number + 1),
              label: `星期${label}`,
            }))}
          />
        </div>
      )}
      {index > 1 && (
        <div className="field">
          日期
          <Select
            label="报告日期"
            value={day}
            onChange={setDay}
            options={Array.from({ length: 31 }, (_, number) => ({
              value: String(number + 1),
              label: `${number + 1}日`,
            }))}
          />
        </div>
      )}
      <Button variant="primary" onClick={() => notify()}>
        保存时间
      </Button>
    </div>
  );
}
