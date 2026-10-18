import { useEffect, useState } from 'react';
import { BookmarkCheck, Undo2 } from 'lucide-react';
import { ApiError } from '../../api/client';
import { Button } from '../../components/ui/Controls';
import { publicChatText } from '../publicProjection';
import { validMemoryReceipt, type MemoryAction, type MemoryCommands } from './contracts';
import type { DisplayReceipt } from './memoryProjection';
import { useInteractionGuard } from './useInteractionGuard';

export function MemoryCard({
  receipt,
  commands,
  onAttempt,
}: {
  receipt: DisplayReceipt;
  commands: MemoryCommands;
  onAttempt?: () => void;
}) {
  const [busy, setBusy] = useState<MemoryAction>(),
    [error, setError] = useState(''),
    [conflicted, setConflicted] = useState(false);
  const guard = useInteractionGuard();
  useEffect(() => {
    setError('');
    setConflicted(false);
  }, [receipt.revision, receipt.fact_id, receipt.proposal_id]);
  const pending = ['pending', 'pending_confirmation'].includes(receipt.write_status);
  const undone = ['stopped', 'deleted', 'dismissed'].includes(receipt.write_status);
  const supports = (action: MemoryAction) =>
    (action !== 'remember-category' || Boolean(receipt.category)) && commands.supports(action, receipt);
  async function act(action: MemoryAction) {
    if (conflicted || !supports(action) || !guard.begin()) return;
    onAttempt?.();
    setBusy(action);
    setError('');
    try {
      const result = await commands.execute(action, receipt);
      if (!guard.current()) return;
      if (!validMemoryReceipt(action, receipt, result))
        throw new Error('没有收到有效确认，记忆状态没有改变，请用原操作重试');
    } catch (reason) {
      if (!guard.current()) return;
      if (reason instanceof ApiError && reason.status === 409) setConflicted(true);
      setError(reason instanceof Error ? reason.message : '尚未收到确认，请用原操作重试');
    } finally {
      guard.end();
      if (guard.current()) setBusy(undefined);
    }
  }
  if (undone)
    return (
      <p className="meta row" role="status">
        <Undo2 className="icon small" aria-hidden="true" />
        {receipt.write_status === 'dismissed' ? '这次不记，尚未保存为有效记忆' : '已撤销，不会再提起'}
      </p>
    );
  const actions: { action: MemoryAction; label: string; variant: 'primary' | 'secondary' | 'ghost' }[] = [
    { action: 'remember', label: '记住', variant: 'primary' },
    { action: 'dismiss', label: '不用', variant: 'secondary' },
    { action: 'remember-category', label: '以后这类都记', variant: 'ghost' },
  ];
  return (
    <section
      className={pending ? 'pending-receipt' : 'memory-receipt'}
      aria-label={pending ? '待确认记忆' : '记忆记录'}>
      <div>
        {pending ? (
          <>
            <p>这个比较私人，要不要我记住？</p>
            <p className="small-text">{publicChatText(receipt.summary)}</p>
            <p className="meta">待你确认，尚未保存为有效记忆</p>
          </>
        ) : receipt.write_status === 'saved' ? (
          <p className="row small-text">
            <BookmarkCheck className="icon small jade-text" aria-hidden="true" />
            {`已记下${receipt.summary ? `：${publicChatText(receipt.summary)}` : ''}`}
          </p>
        ) : (
          <p className="meta">尚未确认保存成功</p>
        )}
        {receipt.category_saved && (
          <p className="meta" role="status">
            本地同类记忆偏好已更新。
          </p>
        )}
        {error && (
          <p role="alert" className="interaction-error">
            {error}
          </p>
        )}
        {conflicted && (
          <a className="text-link quiet-link" href="#/me?section=memory">
            核对最新记忆
          </a>
        )}
      </div>
      {pending ? (
        <>
          <div className="row wrap">
            {actions.map((item) => (
              <Button
                key={item.action}
                variant={item.variant}
                loading={busy === item.action}
                disabled={Boolean(busy) || conflicted || !supports(item.action)}
                onClick={() => void act(item.action)}>
                {item.label}
              </Button>
            ))}
          </div>
          {!actions.some((item) => supports(item.action)) && (
            <p className="meta">这些确认操作尚未接入，此条不会自动保存。</p>
          )}
        </>
      ) : (
        receipt.write_status === 'saved' &&
        (supports('undo') ? (
          <Button
            variant="ghost"
            aria-label="撤销使用"
            loading={busy === 'undo'}
            disabled={Boolean(busy) || conflicted}
            onClick={() => void act('undo')}>
            撤销
          </Button>
        ) : (
          <a className="text-link quiet-link" href="#/me?section=memory">
            查看原话与撤销
          </a>
        ))
      )}
    </section>
  );
}
