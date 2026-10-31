import { useRef, useState, type AriaAttributes } from 'react';
import * as Popover from '@radix-ui/react-popover';
import { Check, ChevronDown } from 'lucide-react';

/** Viewer-only Select: shared Selection.Select currently does not forward field ARIA. */
export function ToolSelect({
  id,
  label,
  value,
  options,
  onChange,
  ...aria
}: {
  id: string;
  label: string;
  value: string;
  options: readonly { value: string; label: string }[];
  onChange: (value: string) => void;
} & Pick<AriaAttributes, 'aria-invalid' | 'aria-describedby'>) {
  const [open, setOpen] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const index = options.findIndex((option) => option.value === value);
  const selected = Math.max(0, index);
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger
        id={id}
        className="input select-trigger"
        role="combobox"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        {...aria}
        onKeyDown={(event) => {
          if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
            event.preventDefault();
            setOpen(true);
          }
        }}>
        <span>{index < 0 ? '请选择' : options[index]?.label}</span>
        <ChevronDown className="icon small" aria-hidden="true" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="popover select-menu"
          aria-label={`${label}选项`}
          sideOffset={4}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            list.current?.querySelectorAll<HTMLButtonElement>('[role="option"]')[selected]?.focus();
          }}>
          <div
            ref={list}
            role="listbox"
            aria-label={label}
            onKeyDown={(event) => {
              const items = Array.from(list.current?.querySelectorAll<HTMLButtonElement>('[role="option"]') ?? []);
              const current = items.indexOf(document.activeElement as HTMLButtonElement);
              const next = { ArrowDown: current + 1, ArrowUp: current - 1, Home: 0, End: items.length - 1 }[event.key];
              if (next !== undefined) {
                event.preventDefault();
                items[(next + items.length) % items.length]?.focus();
              }
            }}>
            {options.map((option, item) => (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={value === option.value}
                tabIndex={selected === item ? 0 : -1}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}>
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
