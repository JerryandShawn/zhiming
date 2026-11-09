import { useState } from 'react';
import { publicChatText } from '../../chat/publicProjection';
import { Button, Textarea } from '../../components/ui/Controls';
import type { AboutMePort, MemoryItem, ProfileItem } from './types';
import { CancelButton, CommandFeedback, useMeCommand } from './useMeCommand';

export function ItemEditor({
  item,
  kind,
  port,
  close,
  confirmed,
}: {
  item: ProfileItem | MemoryItem;
  kind: 'profile' | 'memory';
  port: AboutMePort;
  close: () => void;
  confirmed: (text: string) => void;
}) {
  const [draft, setDraft] = useState(publicChatText(item.text));
  const [revision, setRevision] = useState(item.revision),
    [review, setReview] = useState(false);
  const operation = useMeCommand(port);
  return (
    <form
      className="stack"
      onSubmit={(event) => {
        event.preventDefault();
        if (!draft.trim()) return;
        void operation
          .run({
            type: kind === 'profile' ? 'profile-edit' : 'memory-edit',
            id: item.id,
            text: draft.trim(),
            expectedRevision: revision,
            requestId: crypto.randomUUID(),
          })
          .then((receipt) => {
            if (receipt) {
              confirmed('修改已确认。');
              close();
            }
          });
      }}>
      {'section' in item && item.section === 'chart_summary' && (
        <p className="small-text">这里只修改画像文字，不会改变盘面或出生资料。</p>
      )}
      <label className="field">
        你的说法
        <Textarea
          aria-label="你的说法"
          value={draft}
          disabled={operation.busy || (operation.hasPending && !operation.conflict)}
          onChange={(event) => setDraft(event.target.value)}
        />
      </label>
      <CommandFeedback operation={operation} success="修改已确认。" />
      {operation.conflict && (
        <div className="stack small">
          <Button onClick={() => setReview(true)}>核对当前版本</Button>
          {review && (
            <div className="night-me-preview stack small">
              <h3>当前保存的内容</h3>
              <p>{publicChatText(item.text)}</p>
              <p className="meta">{item.status === 'deleted' ? '这条已经删除。' : '你的草稿仍保留在上方。'}</p>
              <Button
                disabled={item.status !== 'active'}
                onClick={() => {
                  setRevision(item.revision);
                  operation.reset();
                  setReview(false);
                }}>
                已核对，继续编辑
              </Button>
            </div>
          )}
        </div>
      )}
      <div className="row wrap">
        <Button type="submit" loading={operation.busy} disabled={!draft.trim() || operation.conflict}>
          {operation.hasPending && !operation.conflict ? '用原操作重试' : '保存修改'}
        </Button>
        <CancelButton close={close} disabled={operation.busy} />
      </div>
    </form>
  );
}
