import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { Button } from '../../components/ui/Controls';
import { usePanelHistory } from '../../usePanelHistory';
import { BirthForm } from './BirthForm';
import type { BirthPort, BirthReceipt } from './types';

export function BirthConfirmSheet({
  port,
  accepted,
  disabled,
}: {
  port: BirthPort;
  accepted: (receipt: BirthReceipt) => boolean;
  disabled: boolean;
}) {
  const panel = usePanelHistory();
  return (
    <Dialog.Root open={panel.open} onOpenChange={panel.onOpenChange}>
      <Dialog.Trigger asChild>
        <Button disabled={disabled} data-birth-trigger>
          补充出生资料
        </Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content
          className="dialog sheet onboarding-birth-sheet"
          onCloseAutoFocus={(event) => {
            const trigger = document.querySelector<HTMLElement>('[data-step="birth"] [data-birth-trigger]');
            if (trigger?.isConnected) return;
            event.preventDefault();
            (
              document.querySelector<HTMLElement>('[data-runtime="night-onboarding"] textarea') ||
              document.querySelector<HTMLElement>('[data-runtime="night-onboarding"] button')
            )?.focus({ preventScroll: true });
          }}>
          <Dialog.Title asChild>
            <h2 className="dialog-heading">核对出生资料</h2>
          </Dialog.Title>
          <Dialog.Description className="small-text secondary-text">
            出生原值只在这张资料卡里核对，不会复制进聊天或画像文字。
          </Dialog.Description>
          <Dialog.Close className="icon-button dialog-close" aria-label="关闭">
            <X className="icon" aria-hidden="true" />
          </Dialog.Close>
          <div className="dialog-body">
            <BirthForm port={port} accepted={accepted} close={() => panel.onOpenChange(false)} />
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
