import { useRef, useState } from 'react';
import { publicChatText } from '../../chat/publicProjection';
import { Button, Tag } from '../../components/ui/Controls';
import { categoryLabel } from './MemoryList';
import { Sources } from './Sources';
import type { AboutMePort, ProposalItem } from './types';
import { CommandFeedback, useMeCommand } from './useMeCommand';

function ProposalCard({ item, port }: { item: ProposalItem; port: AboutMePort }) {
  const operation = useMeCommand(port, item.category);
  const [revision, setRevision] = useState(item.revision),
    [review, setReview] = useState(false);
  const retryAction = useRef<'remember' | 'dismiss' | 'remember-category'>();
  const saved = item.status === 'saved',
    dismissed = item.status === 'dismissed';
  return (
    <article
      className="night-me-item stack small"
      data-proposal-id={item.status === 'pending' ? item.id : undefined}
      data-revision={item.revision}
      data-status={item.status}>
      <h3>{publicChatText(item.text)}</h3>
      <div className="row wrap">
        <Tag>{item.kind === 'legacy-note' ? '旧版资料' : categoryLabel(item.category)}</Tag>
        <p className="meta">
          {saved ? '已记下' : dismissed ? '这次不记，尚未保存为有效记忆' : '待你确认，尚未保存为有效记忆'}
        </p>
      </div>
      {item.categorySaved && (
        <p role="status" className="meta">
          本地同类记忆偏好已更新。
        </p>
      )}
      <Sources port={port} refs={item.sourceRefs} />
      <CommandFeedback
        operation={operation}
        success={item.categorySaved ? '已记下，并更新了本地同类记忆偏好。' : dismissed ? '这次不记。' : '已记下。'}
      />
      {operation.conflict && (
        <div className="stack small">
          <Button onClick={() => setReview(true)}>核对当前版本</Button>
          {review && (
            <div className="night-me-preview">
              <p>{publicChatText(item.text)}</p>
              <Button
                disabled={item.status !== 'pending'}
                onClick={() => {
                  setRevision(item.revision);
                  operation.reset();
                  setReview(false);
                }}>
                已核对，继续操作
              </Button>
            </div>
          )}
        </div>
      )}
      {!saved && !dismissed && (
        <div className="row wrap">
          {(
            [
              { action: 'remember', label: '记住' },
              { action: 'dismiss', label: '不用' },
              { action: 'remember-category', label: '以后这类都记' },
            ] as const
          ).map(({ action, label }) => (
            <Button
              key={action}
              disabled={
                operation.busy ||
                operation.conflict ||
                Boolean(operation.receipt) ||
                (operation.hasPending &&
                  !operation.conflict &&
                  operation.error !== '' &&
                  action !== retryAction.current) ||
                (action === 'remember-category' && !item.category)
              }
              onClick={() => {
                retryAction.current = action;
                void operation.run({
                  type: 'proposal-act',
                  action,
                  id: item.id,
                  expectedRevision: revision,
                  requestId: crypto.randomUUID(),
                });
              }}>
              {operation.error && retryAction.current === action && !operation.conflict ? '用原操作重试' : label}
            </Button>
          ))}
        </div>
      )}
    </article>
  );
}

export function ProposalList({ items, port }: { items: ProposalItem[]; port: AboutMePort }) {
  const current = items.filter((item) => item.status !== 'deleted');
  return (
    <section className="section stack" aria-label="待确认列表">
      <h2>要不要记住这些？</h2>
      <p className="secondary-text">私人的事先听你的意思，确认前不会成为有效记忆。</p>
      {current
        .filter((item) => item.kind !== 'legacy-note')
        .map((item) => (
          <ProposalCard key={item.id} item={item} port={port} />
        ))}
      <section className="stack small" aria-label="旧版资料">
        <h3>旧版资料</h3>
        {current.some((item) => item.kind === 'legacy-note') ? (
          current
            .filter((item) => item.kind === 'legacy-note')
            .map((item) => <ProposalCard key={item.id} item={item} port={port} />)
        ) : (
          <p className="meta">暂无需要你重新确认的旧版条目。</p>
        )}
      </section>
      {!current.length && <p className="night-me-empty">目前没有待确认内容。</p>}
    </section>
  );
}
