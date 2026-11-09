import type { ReactNode, RefObject } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';

export function MePanel({
  open,
  onOpenChange,
  title,
  description,
  returnTo,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  returnTo: RefObject<HTMLElement | undefined>;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content
          className="dialog sheet night-me-panel"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const previous = returnTo.current;
            const fallback = document.querySelector<HTMLElement>('.night-me-tabs [aria-pressed="true"]');
            (previous?.isConnected ? previous : fallback)?.focus();
          }}>
          <Dialog.Title asChild>
            <h2 className="dialog-heading">{title}</h2>
          </Dialog.Title>
          <Dialog.Description className="small-text secondary-text">{description}</Dialog.Description>
          <Dialog.Close className="icon-button dialog-close" aria-label="关闭">
            <X className="icon" aria-hidden="true" />
          </Dialog.Close>
          <div className="dialog-body">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
