import type { ReactElement, ReactNode } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { usePanelHistory } from '../../usePanelHistory';
export { Toast, EmptyState, ErrorBanner, Skeleton } from './Feedback';

export function Panel({
  title,
  description,
  trigger,
  children,
  sheet = false,
}: {
  title: string;
  description: string;
  trigger: ReactElement;
  children: ReactNode;
  sheet?: boolean;
}) {
  const { open, onOpenChange } = usePanelHistory();
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content className={`dialog ${sheet ? 'sheet' : ''}`}>
          <Dialog.Title asChild>
            <h2 className="dialog-heading">{title}</h2>
          </Dialog.Title>
          <Dialog.Description className="small-text secondary-text">{description}</Dialog.Description>
          <Dialog.Close className="icon-button dialog-close" aria-label="关闭">
            <X className="icon" />
          </Dialog.Close>
          <div className="dialog-body">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
