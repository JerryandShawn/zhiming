import { useEffect, useState } from 'react';
import { ChevronDown, X } from 'lucide-react';
import * as Dialog from '@radix-ui/react-dialog';
import * as Popover from '@radix-ui/react-popover';
import { exampleToday, MiniCalendar } from './Calendar';

export function DatePicker() {
  const [selected, setSelected] = useState(exampleToday);
  const [open, setOpen] = useState(false);
  const [desktop, setDesktop] = useState(() => window.matchMedia('(min-width: 1024px)').matches);
  useEffect(() => {
    const media = window.matchMedia('(min-width: 1024px)');
    const change = () => {
      setDesktop(media.matches);
      setOpen(false);
    };
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, []);
  const [, month, day] = selected.split('-').map(Number);
  const trigger = (
    <button type="button" className="button secondary date-trigger">
      看哪一天：{selected === exampleToday ? '今天 ' : ''}
      {month}月{day}日<ChevronDown className="icon small" aria-hidden="true" />
    </button>
  );
  const description = '合成日历示例，选择只改变日期标签，不重新排盘。仅2026年10月含节气、节假日与调休标记。';
  const calendar = (
    <MiniCalendar
      selected={selected}
      onSelect={(date) => {
        setSelected(date);
        setOpen(false);
      }}
    />
  );
  if (desktop)
    return (
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger asChild>{trigger}</Popover.Trigger>
        <Popover.Portal>
          <Popover.Content
            className="popover calendar-popover"
            sideOffset={8}
            align="start"
            aria-label="选择查看日期"
            role="dialog">
            <h2>选择查看日期</h2>
            <p className="meta">{description}</p>
            {calendar}
            <Popover.Close className="icon-button calendar-close" aria-label="关闭日期选择">
              <X className="icon" />
            </Popover.Close>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    );
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content className="dialog sheet calendar-sheet">
          <Dialog.Title className="dialog-heading">选择查看日期</Dialog.Title>
          <Dialog.Description className="meta">{description}</Dialog.Description>
          {calendar}
          <Dialog.Close className="icon-button dialog-close" aria-label="关闭日期选择">
            <X className="icon" />
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
