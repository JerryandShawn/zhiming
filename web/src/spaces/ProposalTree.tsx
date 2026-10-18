import { LockKeyhole } from 'lucide-react';
import { Button, Tag } from '../components/ui/Controls';
import type { OrganizeEdit } from './EditDialog';
import { useSpacesDemo } from './store';
import { getTopicStats } from './proposal';
import TopicActions from './TopicActions';

function dateLabel(value: string) {
  if (!value) return '时间待确认';
  const date = new Date(value);
  return date.toLocaleString('zh-CN', {
    timeZone: 'Asia/Taipei',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function ProposalTree({ onEdit }: { onEdit: (edit: OrganizeEdit) => void }) {
  const { draft, data, applied, ignoreTopic } = useSpacesDemo();
  return (
    <div className="organize-tree" aria-label="整理草稿区与话题">
      {[...draft.spaces]
        .sort((a, b) => a.order - b.order)
        .map((space) => {
          const topics = draft.topics.filter(
            (topic) => topic.spaceId === space.id && !draft.ignoredTopicIds.includes(topic.id),
          );
          const count = new Set(topics.flatMap((topic) => topic.messageIds)).size;
          return (
            <details key={space.id} className="organize-space" open>
              <summary>
                <Tag>
                  {space.sensitive && <LockKeyhole className="icon small" aria-label="敏感区" />}
                  {space.name}
                </Tag>
                <span className="meta">
                  {topics.length} 个话题 · {count} 条消息
                </span>
              </summary>
              <div className="organize-space-body">
                <div className="row between wrap">
                  <p className="meta">{space.description}</p>
                  <Button
                    variant="ghost"
                    aria-label={`改区名：${space.name}`}
                    disabled={Boolean(applied)}
                    onClick={() => onEdit({ kind: 'space', id: space.id })}>
                    改区名
                  </Button>
                </div>
                {!topics.length && <p className="meta">这个区在本批没有话题。</p>}
                {topics.map((topic) => {
                  const stats = getTopicStats(topic, data.messages);
                  return (
                    <article className="organize-topic stack small" aria-label={`话题：${topic.title}`} key={topic.id}>
                      <div className="row wrap">
                        <h3>{topic.title}</h3>
                        {topic.needsReview && <Tag>待你确认 · 把握度低</Tag>}
                      </div>
                      <p className="meta">
                        {stats.count} 条消息 · {dateLabel(stats.start)} 至 {dateLabel(stats.end)}
                      </p>
                      <p className="organize-sample">{stats.sample || '这条话题没有可展示的消息摘要。'}</p>
                      <TopicActions
                        id={topic.id}
                        title={topic.title}
                        disabled={Boolean(applied)}
                        onEdit={onEdit}
                        onIgnore={() => ignoreTopic(topic.id)}
                      />
                    </article>
                  );
                })}
              </div>
            </details>
          );
        })}
    </div>
  );
}
