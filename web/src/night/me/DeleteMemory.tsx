import { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '../../components/ui/Controls';
import type { AboutMeCommand, AboutMePort, DeletePreview, DeleteScope, MemoryItem } from './types';
import { SourceQuote } from './Sources';
import { CancelButton, CommandFeedback, useMeCommand } from './useMeCommand';

export function DeleteMemory({
  item,
  port,
  close,
  confirmed,
}: {
  item: MemoryItem;
  port: AboutMePort;
  close: () => void;
  confirmed: (message: string) => void;
}) {
  const [scope, setScope] = useState<DeleteScope>('fact'),
    [sourceIndex, setSourceIndex] = useState(0);
  const [preview, setPreview] = useState<DeletePreview>(),
    [previewError, setPreviewError] = useState('');
  const [command, setCommand] = useState<AboutMeCommand>();
  const operation = useMeCommand(port);
  function prepare() {
    try {
      const value = port.previewDelete(item.id, scope, scope === 'source' ? item.sourceRefs[sourceIndex] : undefined);
      setPreview(value);
      setPreviewError('');
      setCommand({
        type: 'memory-delete',
        id: item.id,
        scope,
        expectedRevision: value.targetRevision,
        expectedSnapshotRevision: value.snapshotRevision,
        sourceRef: value.sourceRef,
        requestId: crypto.randomUUID(),
      });
    } catch {
      setPreviewError('暂时无法核对删除范围，没有提交删除。');
    }
  }
  return (
    <div className="stack">
      {!preview ? (
        <>
          <fieldset className="night-me-scope">
            <legend>选择删除范围</legend>
            <label>
              <input
                type="radio"
                name="delete-scope"
                value="fact"
                checked={scope === 'fact'}
                onChange={() => setScope('fact')}
              />
              <span>
                只删这条<span className="meta">保留来源，只移除这一条记忆及它的关联内容。</span>
              </span>
            </label>
            <label>
              <input
                type="radio"
                name="delete-scope"
                value="source"
                checked={scope === 'source'}
                disabled={!item.sourceRefs.length}
                onChange={() => setScope('source')}
              />
              <span>
                删除整段来源<span className="meta">会影响由这段来源整理出的其他内容。</span>
              </span>
            </label>
          </fieldset>
          {scope === 'source' && item.sourceRefs.length > 1 && (
            <label className="field">
              选择要删除的来源
              <select
                aria-label="选择要删除的来源"
                value={sourceIndex}
                onChange={(event) => setSourceIndex(Number(event.target.value))}>
                {item.sourceRefs.map((ref, index) => (
                  <option value={index} key={`${ref.messageId}-${index}`}>
                    {ref.at.slice(0, 10)} · {ref.channel}
                  </option>
                ))}
              </select>
            </label>
          )}
          {scope === 'source' && <SourceQuote port={port} source={item.sourceRefs[sourceIndex]} />}
          {previewError && <p role="alert">{previewError}</p>}
          <div className="row wrap">
            <Button onClick={prepare}>预览删除范围</Button>
            <CancelButton close={close} />
          </div>
        </>
      ) : (
        <>
          <div className="night-me-preview stack small" role="region" aria-label="删除影响预览">
            <h3>{preview.scope === 'fact' ? '将只删除这一条记忆' : '将删除整段来源'}</h3>
            <dl>
              <dt>记忆</dt>
              <dd>{preview.counts.memories} 条</dd>
              <dt>画像条目</dt>
              <dd>{preview.counts.profileItems} 条</dd>
              <dt>待确认内容</dt>
              <dd>{preview.counts.proposals} 条</dd>
              <dt>符号联想</dt>
              <dd>{preview.counts.symbols} 条</dd>
            </dl>
            <p className="meta">相关摘要与引用会一起更新；已经发到飞书的消息无法撤回。</p>
          </div>
          <p className="row small-text">
            <AlertTriangle className="icon" aria-hidden="true" />
            请再次确认范围，确认前不会提交删除。
          </p>
          <CommandFeedback operation={operation} success="删除已确认。" />
          {operation.conflict && <p>当前内容已变化。请返回重新核对影响范围，旧删除不会继续提交。</p>}
          <div className="row wrap">
            <Button
              disabled={operation.conflict || Boolean(operation.receipt)}
              loading={operation.busy}
              onClick={() => {
                if (command)
                  void operation.run(command).then((result) => {
                    if (result) {
                      confirmed('删除已确认。');
                      close();
                    }
                  });
              }}>
              {operation.hasPending && !operation.conflict
                ? '用原操作重试'
                : preview.scope === 'fact'
                  ? '确认删除这条'
                  : '确认删除整段来源'}
            </Button>
            <Button
              variant="ghost"
              disabled={operation.busy || (operation.hasPending && !operation.conflict)}
              onClick={() => {
                operation.reset();
                setPreview(undefined);
                setCommand(undefined);
              }}>
              返回核对范围
            </Button>
            <CancelButton close={close} disabled={operation.busy} />
          </div>
        </>
      )}
    </div>
  );
}
