import { useRef, useState, useSyncExternalStore } from 'react';
import { Button, Tag } from '../components/ui/Controls';
import AppliedChanges from './AppliedChanges';
import ReviewConfirmation, { type ReviewConfirmationState } from './ReviewConfirmation';
import ReviewEditor, { type ReviewEditorTarget } from './ReviewEditor';
import ReviewTree from './ReviewTree';
import { createOrganizeDemoPort } from './port';
import type { ConfirmationScope, EditIntent, OrganizePort } from './types';
import './review.css';

export default function OrganizeReviewPage({ suppliedPort }: { suppliedPort?: OrganizePort }) {
  const [port] = useState(() => suppliedPort ?? createOrganizeDemoPort());
  const snapshot = useSyncExternalStore(port.subscribe, port.getSnapshot);
  const [editor, setEditor] = useState<ReviewEditorTarget | null>(null);
  const [confirmation, setConfirmation] = useState<ReviewConfirmationState | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const pending = useRef(false);
  const summary = snapshot.summary;
  async function edit(intent: EditIntent) {
    if (pending.current) return false;
    pending.current = true;
    setBusy(true);
    try {
      const request_id = crypto.randomUUID();
      const result = await port.edit({ request_id, expected_revision: snapshot.revision, intent });
      if (result.request_id !== request_id || result.revision !== port.getSnapshot().revision) {
        setMessage('这次草稿回执尚未核对成功，请重新查看。');
        return false;
      }
      setMessage(result.message);
      return result.status === 'accepted';
    } catch {
      setMessage('草稿尚未确认保存，请重试；原消息没有改变。');
      return false;
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  function confirm(scope: ConfirmationScope) {
    try {
      const ticket = port.prepareConfirmation(scope);
      setConfirmation({ scope, ticket, requestId: crypto.randomUUID() });
      setMessage('');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '暂时不能确认，请核对当前整理。');
    }
  }
  return (
    <section
      className="page stack review-page"
      data-runtime="organize-v2"
      data-revision={snapshot.revision}
      data-state={snapshot.status}
      aria-labelledby="review-title">
      <header className="stack small">
        <h1 id="review-title" tabIndex={-1}>
          旧对话审阅
        </h1>
        <p>先看区、话题和片段，再决定哪些整理值得留下。</p>
      </header>
      <aside className="review-note stack small" aria-label="整理审阅模拟说明">
        <div>
          <Tag>合成资料 · 本地模拟</Tag>
        </div>
        <p className="small-text">本页没有连接真实聊天。整理只改变演示标签，刷新即重置；不改写原话，不发送模型请求。</p>
        <p className="meta">低把握的建议请你判断，不会自动应用。按字段撤销目前由模拟端口提供。</p>
        <div>
          <Button
            variant="ghost"
            onClick={() => {
              document.querySelector<HTMLElement>('.review-uncertain')?.scrollIntoView({ block: 'start' });
              document.querySelector<HTMLElement>('.review-uncertain h2')?.focus({ preventScroll: true });
            }}>
            先看归属不确定的片段
          </Button>
        </div>
      </aside>
      <section className="review-summary stack small" aria-labelledby="review-summary-title">
        <h2 id="review-summary-title">应用前的变更摘要</h2>
        <dl className="review-counts">
          <div>
            <dt>已接受</dt>
            <dd>{summary.accepted_segments} 段</dd>
          </div>
          <div>
            <dt>已拒绝</dt>
            <dd>{summary.rejected_segments} 段</dd>
          </div>
          <div>
            <dt>待处理</dt>
            <dd>{summary.pending_segments} 段</dd>
          </div>
          <div>
            <dt>涉及原消息</dt>
            <dd>{summary.message_count} 条</dd>
          </div>
          <div>
            <dt>标签字段</dt>
            <dd>{summary.field_changes} 项</dd>
          </div>
          <div>
            <dt>新话题</dt>
            <dd>{summary.topic_creations} 个</dd>
          </div>
        </dl>
        <p className="small-text secondary-text">
          接受与拒绝先保存在草稿。只有再次确认应用后，已接受的片段才改变归属。
        </p>
        <div>
          <Button
            variant="primary"
            disabled={busy || snapshot.status !== 'draft' || !summary.accepted_segments}
            onClick={() => confirm({ action: 'apply' })}>
            应用已接受的整理
          </Button>
        </div>
      </section>
      {message && <p role="status">{message}</p>}
      <AppliedChanges
        snapshot={snapshot}
        busy={busy}
        onRevert={(fields) => confirm({ action: 'revert', ...(fields ? { fields } : {}) })}
      />
      <ReviewTree
        snapshot={snapshot}
        busy={busy || snapshot.status !== 'draft'}
        onEdit={(intent) => void edit(intent)}
        onOpenEditor={setEditor}
      />
      {editor && (
        <ReviewEditor
          key={JSON.stringify(editor)}
          target={editor}
          snapshot={snapshot}
          busy={busy}
          onClose={() => setEditor(null)}
          onSubmit={edit}
        />
      )}
      {confirmation && (
        <ReviewConfirmation
          key={confirmation.ticket.id}
          confirmation={confirmation}
          port={port}
          onClose={() => setConfirmation(null)}
          onRenew={confirm}
          onSuccess={(text) => {
            setMessage(text);
            setConfirmation(null);
          }}
        />
      )}
    </section>
  );
}
