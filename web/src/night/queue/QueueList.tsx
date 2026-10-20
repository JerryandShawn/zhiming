import { Button } from '../../components/ui/Controls';
import { BEIJING_TIME_ZONE } from '../../time/beijing';
import type { QueueItem } from './types';
import './queue.css';

const times = new Intl.DateTimeFormat('zh-CN', {
  timeZone: BEIJING_TIME_ZONE,
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});
const states = {
  pending: '正在接收，尚未确认',
  queued: '已收到，这段说完一起看',
  canceling: '正在取消，尚未收到确认',
  failed: '这次尚未确认，请重试',
} as const;

export default function QueueList({
  items,
  onCancel,
  onRetry,
  resetHint,
}: {
  items: readonly QueueItem[];
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
  resetHint?: string;
}) {
  if (!items.length) return null;
  return (
    <section className="chat-queue" aria-label="排队消息">
      <h2 className="small-text">接着聊 · {items.length} 条</h2>
      {resetHint && <p className="meta">{resetHint}</p>}
      <ol className="chat-queue-list" aria-label="排队消息列表">
        {items.map((item, index) => (
          <li className="chat-queue-item" key={item.id} data-queue-id={item.id} data-queue-state={item.state}>
            <div className="chat-queue-heading">
              <span className="meta">
                第 {index + 1} 条
                {Number.isFinite(item.created_at_ms) ? ` · ${times.format(item.created_at_ms)}（北京时间）` : ''}
              </span>
              {item.images.length > 0 && <span className="meta">附图 {item.images.length} 张</span>}
            </div>
            <p className="chat-queue-text">{item.text}</p>
            <p className="meta" role="status">
              {item.state === 'failed' ? item.error || states.failed : states[item.state]}
            </p>
            {(item.state === 'queued' || item.state === 'failed') && (
              <div className="chat-queue-actions" role="group" aria-label={`第${index + 1}条排队消息操作`}>
                {item.state === 'failed' && (
                  <Button
                    variant="ghost"
                    aria-label={item.failed_action === 'cancel' ? '重试取消' : '重试排队发送'}
                    onClick={() => onRetry(item.id)}>
                    重试
                  </Button>
                )}
                <Button variant="ghost" onClick={() => onCancel(item.id)}>
                  取消排队
                </Button>
              </div>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
