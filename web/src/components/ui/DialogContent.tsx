import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { DialogContentProps } from './DeferredPanel';

export default function DialogContent({
  open,
  title,
  description,
  children,
  sheet,
  contentId,
  onOpenChange,
  onReturnFocus,
}: DialogContentProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content
          id={contentId}
          className={`dialog ${sheet ? 'sheet' : ''}`}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            onReturnFocus();
          }}>
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
