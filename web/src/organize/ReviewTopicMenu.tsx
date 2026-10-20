import { useRef, useState } from 'react';
import * as Popover from '@radix-ui/react-popover';
import { ChevronDown } from 'lucide-react';
import { Button } from '../components/ui/Controls';
import type { ReviewTopic } from './types';

export default function ReviewTopicMenu({
  topic,
  disabled,
  onOpen,
}: {
  topic: ReviewTopic;
  disabled: boolean;
  onOpen: () => void;
}) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const item = useRef<HTMLButtonElement>(null);
  const pending = useRef(false);
  return (
    <Popover.Root open={open && !disabled} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button
          ref={trigger}
          variant="ghost"
          disabled={disabled}
          aria-haspopup="menu"
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
              event.preventDefault();
              setOpen(true);
            }
          }}>
          更多 <ChevronDown className="icon small" aria-hidden="true" />
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="popover review-topic-menu"
          role="menu"
          aria-label={`${topic.title}更多操作`}
          align="start"
          sideOffset={4}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            item.current?.focus();
          }}
          onCloseAutoFocus={(event) => {
            if (pending.current) {
              event.preventDefault();
              pending.current = false;
              trigger.current?.focus();
              onOpen();
            }
          }}>
          <Button
            ref={item}
            role="menuitem"
            variant="ghost"
            disabled={disabled}
            onClick={() => {
              pending.current = true;
              setOpen(false);
            }}>
            合并话题
          </Button>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
