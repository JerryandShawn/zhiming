import { useEffect, useRef, useState } from 'react';
import * as Popover from '@radix-ui/react-popover';
import { ChevronDown } from 'lucide-react';
import { Button } from '../components/ui/Controls';
import type { OrganizeEdit } from './EditDialog';

const desktopQuery = '(min-width: 1024px)';
const edits = [
  { kind: 'rename', text: '改名' },
  { kind: 'merge', text: '合并' },
  { kind: 'split', text: '拆分' },
  { kind: 'move', text: '移动' },
] as const;

export default function TopicActions({
  id,
  title,
  disabled,
  onEdit,
  onIgnore,
}: {
  id: string;
  title: string;
  disabled: boolean;
  onEdit: (edit: OrganizeEdit) => void;
  onIgnore: () => void;
}) {
  const [desktop, setDesktop] = useState(() => window.matchMedia(desktopQuery).matches);
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const initialFocus = useRef(0);
  const pendingAction = useRef<(() => void) | null>(null);
  useEffect(() => {
    const media = window.matchMedia(desktopQuery);
    const update = () => {
      setDesktop(media.matches);
      setOpen(false);
    };
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);
  const select = (action: () => void) => {
    pendingAction.current = action;
    setOpen(false);
  };
  return (
    <div className="row wrap organize-topic-actions" role="group" aria-label={`${title}操作`}>
      {(desktop ? edits : edits.filter(({ kind }) => kind === 'rename' || kind === 'move')).map((action) => (
        <Button key={action.kind} variant="ghost" disabled={disabled} onClick={() => onEdit({ kind: action.kind, id })}>
          {action.text}
        </Button>
      ))}
      {desktop ? (
        <Button variant="ghost" disabled={disabled} onClick={onIgnore}>
          忽略本批
        </Button>
      ) : (
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
                  initialFocus.current = event.key === 'ArrowUp' ? -1 : 0;
                  setOpen(true);
                }
              }}>
              更多
              <ChevronDown className="icon small" aria-hidden="true" />
            </Button>
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content
              ref={menu}
              className="popover organize-topic-menu"
              role="menu"
              aria-label={`${title}更多操作`}
              align="start"
              sideOffset={4}
              onOpenAutoFocus={(event) => {
                event.preventDefault();
                const items = menu.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]');
                items?.item(initialFocus.current < 0 ? items.length - 1 : 0)?.focus();
                initialFocus.current = 0;
              }}
              onCloseAutoFocus={(event) => {
                const action = pendingAction.current;
                pendingAction.current = null;
                if (action) {
                  event.preventDefault();
                  // The editor records this stable trigger for its own focus return.
                  trigger.current?.focus();
                  action();
                }
              }}
              onKeyDown={(event) => {
                const items = Array.from(menu.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? []);
                const index = items.indexOf(document.activeElement as HTMLButtonElement);
                const next = { ArrowDown: index + 1, ArrowUp: index - 1, Home: 0, End: items.length - 1 }[event.key];
                if (next !== undefined && items.length) {
                  event.preventDefault();
                  items[(next + items.length) % items.length]?.focus();
                }
              }}>
              {edits
                .filter(({ kind }) => kind === 'merge' || kind === 'split')
                .map((action) => (
                  <Button
                    key={action.kind}
                    role="menuitem"
                    tabIndex={-1}
                    variant="ghost"
                    disabled={disabled}
                    onClick={() => select(() => onEdit({ kind: action.kind, id }))}>
                    {action.text}
                  </Button>
                ))}
              <Button
                role="menuitem"
                tabIndex={-1}
                variant="ghost"
                disabled={disabled}
                onClick={() => select(onIgnore)}>
                忽略本批
              </Button>
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
      )}
    </div>
  );
}
