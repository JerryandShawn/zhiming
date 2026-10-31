import { useRef, useState } from 'react';
import { Check, ChevronDown, Clock3 } from 'lucide-react';
import * as Popover from '@radix-ui/react-popover';

type Option = { value: string; label: string };

export function Select({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly Option[];
  value: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const current = Math.max(
    0,
    options.findIndex((option) => option.value === value),
  );
  const choose = (next: string) => {
    onChange(next);
    setOpen(false);
  };
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger
        className="input select-trigger"
        role="combobox"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        onKeyDown={(event) => {
          if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
            event.preventDefault();
            setOpen(true);
          }
        }}>
        <span>{options[current]?.label}</span>
        <ChevronDown className="icon small" aria-hidden="true" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="popover select-menu"
          aria-label={`${label}选项`}
          sideOffset={4}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            list.current?.querySelectorAll<HTMLButtonElement>('[role="option"]')[current]?.focus();
          }}>
          <div
            ref={list}
            role="listbox"
            aria-label={label}
            onKeyDown={(event) => {
              const items = Array.from(list.current?.querySelectorAll<HTMLButtonElement>('[role="option"]') ?? []);
              const index = items.indexOf(document.activeElement as HTMLButtonElement);
              const next = { ArrowDown: index + 1, ArrowUp: index - 1, Home: 0, End: items.length - 1 }[event.key];
              if (next !== undefined) {
                event.preventDefault();
                items[(next + items.length) % items.length]?.focus();
              }
            }}>
            {options.map((option, index) => (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={value === option.value}
                tabIndex={current === index ? 0 : -1}
                onClick={() => choose(option.value)}>
                <span>{option.label}</span>
                {value === option.value && <Check className="icon small" aria-hidden="true" />}
              </button>
            ))}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function TimePicker({ label, initial }: { label: string; initial: string }) {
  const [value, setValue] = useState(initial);
  const [hour, minute] = value.split(':');
  const options = (count: number) =>
    Array.from({ length: count }, (_, number) => ({
      value: String(number).padStart(2, '0'),
      label: String(number).padStart(2, '0'),
    }));
  return (
    <Popover.Root>
      <Popover.Trigger className="button secondary time-trigger" aria-label={`${label} ${value}`}>
        <Clock3 className="icon small" aria-hidden="true" />
        {value}
        <ChevronDown className="icon small" aria-hidden="true" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="popover" sideOffset={4} aria-label={`${label}选择`}>
          <p className="small-text">{label}</p>
          <div className="time-options">
            <div className="field">
              小时
              <Select
                label={`${label}小时`}
                options={options(24)}
                value={hour}
                onChange={(next) => setValue(`${next}:${minute}`)}
              />
            </div>
            <div className="field">
              分钟
              <Select
                label={`${label}分钟`}
                options={options(60)}
                value={minute}
                onChange={(next) => setValue(`${hour}:${next}`)}
              />
            </div>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
