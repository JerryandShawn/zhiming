import { ChevronDown, LockKeyhole } from 'lucide-react';
import { Button, Tag } from '../components/ui/Controls';
import { BEIJING_TIME_ZONE } from '../time/beijing';
import type { ReviewEditorTarget } from './ReviewEditor';
import ReviewTopicMenu from './ReviewTopicMenu';
import type { EditIntent, OrganizeSnapshot, ReviewSegment } from './types';
import './review-tree.css';

export type { ReviewEditorTarget } from './ReviewEditor';

type Props = {
  snapshot: OrganizeSnapshot;
  busy: boolean;
  onEdit: (intent: EditIntent) => void;
  onOpenEditor: (editor: ReviewEditorTarget) => void;
};
const decisions = { pending: '待审阅', accepted: '已接受', rejected: '本批不整理' } as const;
const timeFormat = new Intl.DateTimeFormat('zh-CN', {
  timeZone: BEIJING_TIME_ZONE,
  month: 'numeric',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});
const timeLabel = (value: number) => (Number.isFinite(value) ? timeFormat.format(value) : '时间待核对');
const uncertain = (segment: ReviewSegment) => segment.needs_review && segment.decision === 'pending';

function Segment({
  segment,
  snapshot,
  locked,
  onEdit,
  onOpenEditor,
  showTopic = false,
}: {
  segment: ReviewSegment;
  snapshot: OrganizeSnapshot;
  locked: boolean;
  onEdit: Props['onEdit'];
  onOpenEditor: Props['onOpenEditor'];
  showTopic?: boolean;
}) {
  const topic = snapshot.topics.find(({ id }) => id === segment.topic_id);
  const sourceUnavailable = segment.source_available === false;
  const messages = segment.message_ids.flatMap((id) =>
    snapshot.document.messages[id] ? [snapshot.document.messages[id]] : [],
  );
  return (
    <article
      className="review-segment"
      data-segment-id={segment.id}
      tabIndex={-1}
      aria-label={`片段：${topic?.title ?? '待归类'}`}>
      <div className="review-segment-heading">
        <span className="meta">
          {timeLabel(segment.start)} · {segment.message_ids.length} 条原消息
        </span>
        <Tag>{decisions[segment.decision]}</Tag>
      </div>
      {showTopic && <p className="meta">建议话题：{topic?.title ?? '待归类'}</p>}
      <p className="review-segment-sample">{segment.sample || '这段内容暂无摘要，可展开原消息核对。'}</p>
      {sourceUnavailable && <p className="meta">来源已停止使用。可以拒绝本次候选，继续审阅其他片段。</p>}
      {uncertain(segment) && <p className="meta">归属还不确定，请先核对原话，再决定是否接受。</p>}
      <div className="review-segment-actions" role="group" aria-label="片段操作">
        <Button
          variant="ghost"
          disabled={locked || sourceUnavailable || segment.decision === 'accepted'}
          onClick={() => onEdit({ kind: 'accept', segment_id: segment.id })}>
          接受
        </Button>
        <Button
          variant="ghost"
          disabled={locked || segment.decision === 'rejected'}
          onClick={() => onEdit({ kind: 'reject', segment_id: segment.id })}>
          拒绝
        </Button>
        <Button
          variant="ghost"
          disabled={locked || sourceUnavailable}
          onClick={() => onOpenEditor({ kind: 'move_segment', segment_id: segment.id })}>
          移动
        </Button>
      </div>
      {!sourceUnavailable && (
        <details className="review-originals">
          <summary>查看原消息（{messages.length} 条）</summary>
          <ol>
            {messages.map((message) => (
              <li key={message.id}>
                <p className="meta">
                  {message.role === 'user' ? '你' : '明镜'} · {timeLabel(message.at_ms)}（北京时间）
                </p>
                <p>{message.content}</p>
              </li>
            ))}
            {!messages.length && <li className="meta">原消息暂不可用，请稍后核对。</li>}
          </ol>
        </details>
      )}
    </article>
  );
}

export function ReviewTree({ snapshot, busy, onEdit, onOpenEditor }: Props) {
  const locked = busy || snapshot.status !== 'draft';
  const pending = snapshot.segments.filter(uncertain);
  return (
    <div className="review-tree" aria-label="区、话题与片段">
      <section aria-label="区与话题" className="review-tree-section">
        <div>
          <h2>区与话题</h2>
          <p className="meta">先核对归属。这里的调整会保留在本批草稿中。</p>
        </div>
        {snapshot.spaces.map((space) => {
          const topics = snapshot.topics.filter(({ space_id }) => space_id === space.id);
          return (
            <details className="review-space" key={space.id} data-space-id={space.id} open>
              <summary>
                <ChevronDown className="icon small" aria-hidden="true" />
                <span>{space.name}</span>
                {space.sensitive && (
                  <span className="review-sensitive meta">
                    <LockKeyhole className="icon small" aria-hidden="true" />
                    敏感区
                  </span>
                )}
                <span className="meta">{topics.length} 个话题</span>
              </summary>
              {!topics.length && <p className="meta review-empty">本批没有归入这个区的话题。</p>}
              <div className="review-topic-list">
                {topics.map((topic) => {
                  const segments = snapshot.segments.filter(({ topic_id }) => topic_id === topic.id);
                  const visible = segments.filter((segment) => !uncertain(segment));
                  return (
                    <article
                      key={topic.id}
                      className="review-topic"
                      data-topic-id={topic.id}
                      aria-label={`话题：${topic.title}`}>
                      <div className="review-topic-heading">
                        <div className="review-topic-title">
                          <h3>{topic.title}</h3>
                          <p className="meta">
                            {segments.length} 个片段 · {topic.message_ids.length} 条原消息
                          </p>
                        </div>
                        <div className="review-topic-actions" role="group" aria-label={`${topic.title}操作`}>
                          <Button
                            variant="ghost"
                            disabled={locked}
                            onClick={() => onOpenEditor({ kind: 'rename', topic_id: topic.id })}>
                            改名
                          </Button>
                          <Button
                            variant="ghost"
                            disabled={locked}
                            onClick={() => onOpenEditor({ kind: 'move_topic', topic_id: topic.id })}>
                            移动
                          </Button>
                          <ReviewTopicMenu
                            topic={topic}
                            disabled={locked}
                            onOpen={() => onOpenEditor({ kind: 'merge', topic_id: topic.id })}
                          />
                        </div>
                      </div>
                      {visible.map((segment) => (
                        <Segment key={segment.id} {...{ segment, snapshot, locked, onEdit, onOpenEditor }} />
                      ))}
                      {!visible.length && (
                        <p className="meta review-empty">这个话题的片段已列在“不确定，待你整理”区。</p>
                      )}
                    </article>
                  );
                })}
              </div>
            </details>
          );
        })}
        {!snapshot.spaces.length && <p className="meta">本批没有可审阅的功能区。</p>}
      </section>
      <section className="review-tree-section review-uncertain" aria-label="不确定，待你整理">
        <div>
          <h2 tabIndex={-1}>不确定，待你整理</h2>
          <p className="meta">这些片段需要你决定，不会自动归区。</p>
        </div>
        {pending.map((segment) => (
          <Segment key={segment.id} {...{ segment, snapshot, locked, onEdit, onOpenEditor }} showTopic />
        ))}
        {!pending.length && <p className="meta">本批没有归属不确定的待审片段。</p>}
      </section>
    </div>
  );
}

export default ReviewTree;
