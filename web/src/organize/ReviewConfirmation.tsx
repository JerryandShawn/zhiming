import { useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { Button } from '../components/ui/Controls';
import type { ConfirmationScope, ConfirmationTicket, OrganizePort } from './types';

export type ReviewConfirmationState = { ticket: ConfirmationTicket; scope: ConfirmationScope; requestId: string };
export default function ReviewConfirmation({
  confirmation,
  port,
  onClose,
  onRenew,
  onSuccess,
}: {
  confirmation: ReviewConfirmationState;
  port: OrganizePort;
  onClose: () => void;
  onRenew: (scope: ConfirmationScope) => void;
  onSuccess: (message: string) => void;
}) {
  const returnFocus = useRef(document.activeElement as HTMLElement | null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [expired, setExpired] = useState(false);
  const apply = confirmation.ticket.action === 'apply';
  async function execute() {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await port.execute({ request_id: confirmation.requestId, ticket_id: confirmation.ticket.id });
      if (result.request_id !== confirmation.requestId || result.revision !== port.getSnapshot().revision) {
        setError('这次回执尚未核对成功，请重试原操作。');
      } else if (result.status === 'accepted') onSuccess(result.message);
      else {
        setError(result.message);
        setExpired(result.code === 'confirmation_expired' || /过期/.test(result.message));
      }
    } catch {
      setError('这次操作尚未确认，整理仍保留。请重试。');
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog.Root open onOpenChange={(open) => !open && !busy && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content
          className="dialog review-confirmation"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const target = returnFocus.current;
            if (target?.isConnected && !target.hasAttribute('disabled')) target.focus({ preventScroll: true });
            else document.getElementById('review-title')?.focus({ preventScroll: true });
          }}>
          <Dialog.Title asChild>
            <h2 className="dialog-heading">{apply ? '应用已接受的整理？' : '撤销这部分整理？'}</h2>
          </Dialog.Title>
          <Dialog.Description className="small-text secondary-text">
            {apply
              ? '只改变已接受片段的本地归区标签。未处理和已拒绝的片段保留原归属。'
              : '只恢复仍与本批结果一致的字段；后来编辑过的值会保留。'}
            原消息不会改写或删除。
          </Dialog.Description>
          <Dialog.Close className="icon-button dialog-close" aria-label="关闭确认" disabled={busy}>
            <X className="icon" />
          </Dialog.Close>
          <div className="dialog-body stack">
            <p>
              本次确认15分钟内有效。
              {confirmation.scope.fields ? `已选择 ${confirmation.scope.fields.length} 项关联字段。` : ''}
            </p>
            {error && <p role="alert">{error}</p>}
            <div className="row wrap">
              {expired ? (
                <Button variant="primary" onClick={() => onRenew(confirmation.scope)}>
                  重新确认
                </Button>
              ) : (
                <Button variant="primary" loading={busy} onClick={execute}>
                  {apply ? '确认应用' : '确认撤销'}
                </Button>
              )}
              <Button disabled={busy} onClick={onClose}>
                取消
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
