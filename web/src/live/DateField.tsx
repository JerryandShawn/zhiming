import { useState } from 'react';
import * as Popover from '@radix-ui/react-popover';
import { Button, Input } from '../components/ui/Controls';

export default function DateField({
  label,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const [month, setMonth] = useState(() =>
    /^\d{4}-\d\d-\d\d$/.test(value) ? value.slice(0, 7) : new Date().toISOString().slice(0, 7),
  );
  const [open, setOpen] = useState(false);
  const [year, number] = month.split('-').map(Number);
  const count = new Date(year, number, 0).getDate();
  function move(delta: number) {
    const next = new Date(year, number - 1 + delta, 1);
    setMonth(`${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`);
  }
  return (
    <div className="field">
      <label>
        {label}
        <Input
          aria-label={label}
          placeholder="YYYY-MM-DD"
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger asChild>
          <Button disabled={disabled} aria-label={`选择${label}`}>
            {`选择${label}`}
          </Button>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content className="popover calendar-popover" role="dialog" aria-label={`选择${label}`}>
            <div className="row between">
              <Button aria-label="上个月" onClick={() => move(-1)}>
                上个月
              </Button>
              <h3>
                {year}年{number}月
              </h3>
              <Button aria-label="下个月" onClick={() => move(1)}>
                下个月
              </Button>
            </div>
            <div className="calendar-grid">
              {Array.from({ length: count }, (_, index) => {
                const date = `${month}-${String(index + 1).padStart(2, '0')}`;
                return (
                  <button
                    type="button"
                    className={`calendar-day ${date === value ? 'selected' : ''}`}
                    key={date}
                    aria-label={date}
                    aria-pressed={date === value}
                    onClick={() => {
                      onChange(date);
                      setOpen(false);
                    }}>
                    {index + 1}
                  </button>
                );
              })}
            </div>
            <p className="meta">阳历日期。手动输入时请使用 YYYY-MM-DD。</p>
            <Popover.Close className="button secondary">关闭日期选择</Popover.Close>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </div>
  );
}
