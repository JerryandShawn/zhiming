import { useEffect, useRef, useState } from 'react';
import { Button } from '../../components/ui/Controls';
import type { AboutMeCommand, AboutMePort, AboutMeReceipt } from './types';

function validReceipt(command: AboutMeCommand, receipt: AboutMeReceipt, category?: string) {
  const status =
    command.type === 'proposal-act'
      ? command.action === 'dismiss'
        ? 'dismissed'
        : 'saved'
      : ['profile-delete', 'memory-delete', 'symbol-delete'].includes(command.type)
        ? 'deleted'
        : command.type === 'memory-stop'
          ? 'stopped'
          : 'saved';
  return (
    receipt?.id === command.id &&
    receipt.kind === command.type &&
    receipt.requestId === command.requestId &&
    receipt.write_status === status &&
    Number.isInteger(receipt.revision) &&
    receipt.revision > command.expectedRevision &&
    Number.isInteger(receipt.snapshotRevision) &&
    receipt.snapshotRevision > 0 &&
    Array.isArray(receipt.affectedIds) &&
    receipt.affectedIds.includes(command.id) &&
    (command.type !== 'memory-delete' || receipt.snapshotRevision > command.expectedSnapshotRevision) &&
    (command.type !== 'proposal-act' ||
      command.action !== 'remember-category' ||
      (receipt.memoryReceipt?.category_saved === true && receipt.memoryReceipt.category === category))
  );
}

export function useMeCommand(port: AboutMePort, category?: string) {
  const pending = useRef<AboutMeCommand>();
  const active = useRef(false),
    mounted = useRef(true);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const [conflict, setConflict] = useState(false),
    [receipt, setReceipt] = useState<AboutMeReceipt>();
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  async function run(command: AboutMeCommand) {
    if (active.current || conflict || receipt) return;
    active.current = true;
    const original = pending.current ?? command;
    pending.current = original;
    setBusy(true);
    setError('');
    try {
      const result = await port.execute(original);
      if (!mounted.current) return;
      if (!validReceipt(original, result, category)) throw new Error('INVALID_RECEIPT');
      setReceipt(result);
      return result;
    } catch (reason: unknown) {
      if (!mounted.current) return;
      const status = reason && typeof reason === 'object' && 'status' in reason ? reason.status : undefined;
      setConflict(status === 409);
      setError(
        status === 409
          ? '内容已更新，草稿仍保留。请先核对当前版本，再继续。'
          : status === 429
            ? '这次暂时忙，原操作和内容已保留，可以再试一次。'
            : '尚未收到有效确认，原操作和内容已保留，可以再试一次。',
      );
    } finally {
      active.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  function reset() {
    if (active.current) return;
    pending.current = undefined;
    setError('');
    setConflict(false);
    setReceipt(undefined);
  }
  return { run, reset, busy, error, conflict, receipt, hasPending: Boolean(pending.current) };
}

export function CommandFeedback({
  operation,
  success,
}: {
  operation: ReturnType<typeof useMeCommand>;
  success: string;
}) {
  return (
    <>
      {operation.error && (
        <p role="alert" className="interaction-error">
          {operation.error}
        </p>
      )}
      {operation.receipt && (
        <p role="status" className="night-me-feedback">
          {success}
        </p>
      )}
    </>
  );
}

export function CancelButton({ close, disabled = false }: { close: () => void; disabled?: boolean }) {
  return (
    <Button variant="ghost" onClick={close} disabled={disabled}>
      取消
    </Button>
  );
}
