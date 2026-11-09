import { useEffect, useRef, useState } from 'react';
import type { SettingsCommand, SettingsPort, SettingsReceipt } from './types';

export function useSettingsCommand(port: SettingsPort) {
  const pending = useRef<SettingsCommand>(),
    active = useRef(false),
    mounted = useRef(true);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [conflict, setConflict] = useState(false),
    [saved, setSaved] = useState(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  async function run(
    command: SettingsCommand,
    validate: (receipt: SettingsReceipt, command: SettingsCommand) => boolean,
  ) {
    if (active.current || conflict) return;
    const original = pending.current ?? command;
    pending.current = original;
    active.current = true;
    setBusy(true);
    setError('');
    setSaved(false);
    try {
      const receipt = await port.execute(original);
      if (!mounted.current) return;
      if (
        receipt.requestId !== original.requestId ||
        receipt.kind !== original.type ||
        !Number.isInteger(receipt.revision) ||
        (original.type === 'report-save'
          ? receipt.revision < original.expectedRevision
          : receipt.revision <= original.expectedRevision) ||
        !Number.isInteger(receipt.snapshotRevision) ||
        receipt.snapshotRevision < 1 ||
        !validate(receipt, original)
      )
        throw new Error('INVALID_RECEIPT');
      pending.current = undefined;
      setSaved(true);
      return receipt;
    } catch (reason) {
      if (!mounted.current) return;
      const status = reason && typeof reason === 'object' && 'status' in reason ? reason.status : undefined;
      if (status === 422) pending.current = undefined;
      setConflict(status === 409);
      setError(
        status === 409
          ? '设置已变化，草稿仍保留，请先核对当前设置。'
          : status === 422
            ? '请核对设置内容，尚未保存。'
            : '尚未收到有效确认，请用原设置重试。',
      );
    } finally {
      active.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  function reset() {
    if (!active.current) {
      pending.current = undefined;
      setError('');
      setConflict(false);
      setSaved(false);
    }
  }
  return { run, reset, busy, error, conflict, saved, hasPending: Boolean(pending.current) };
}
