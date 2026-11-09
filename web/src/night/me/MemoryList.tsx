import { useState } from 'react';
import { publicChatText } from '../../chat/publicProjection';
import { Button, Input, Tag } from '../../components/ui/Controls';
import { SourceQuote, Sources } from './Sources';
import type { AboutMePort, MemoryItem } from './types';
import type { OpenMeView } from './views';

const categories: Record<string, string> = {
  preference: '偏好',
  preferences: '偏好',
  health: '健康',
  career: '工作',
  work: '工作',
  event: '安排',
  schedule: '安排',
  relationship: '关系',
  basic: '基本情况',
  goals: '目标',
  communication: '沟通',
  study: '研习',
  plan: '计划',
};
const spaceLabels: Record<string, string> = {
  daily: '日常',
  career: '事业学业',
  relationships: '感情人际',
  family: '家庭',
  wellbeing: '身心',
  finance: '财务',
  study: '命理研习',
};
export function categoryLabel(value?: string) {
  return value ? categories[value] || '其他' : '未分类';
}
export function MemoryList({ items, port, open }: { items: MemoryItem[]; port: AboutMePort; open: OpenMeView }) {
  const [search, setSearch] = useState(''),
    [category, setCategory] = useState('all');
  const visible = items.filter((item) => item.status !== 'deleted');
  const choices = [...new Set(visible.map((item) => item.category || 'uncategorized'))];
  const filtered = visible.filter(
    (item) =>
      publicChatText(item.text).includes(search) &&
      (category === 'all' || (item.category || 'uncategorized') === category),
  );
  return (
    <section className="section stack" aria-label="记忆列表">
      <h2>记忆与来源</h2>
      <Input
        type="search"
        aria-label="搜索记忆"
        placeholder="找一件你说过的事…"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <div className="night-me-filter" role="group" aria-label="记忆类别">
        <Button variant="ghost" aria-pressed={category === 'all'} onClick={() => setCategory('all')}>
          全部
        </Button>
        {choices.map((value) => (
          <Button variant="ghost" key={value} aria-pressed={category === value} onClick={() => setCategory(value)}>
            {categoryLabel(value === 'uncategorized' ? undefined : value)}
          </Button>
        ))}
      </div>
      {!filtered.length && <p className="night-me-empty">没有符合当前条件的记忆。</p>}
      {filtered.map((item) => (
        <article
          className="night-me-item"
          data-memory-id={item.id}
          key={item.id}
          data-revision={item.revision}
          data-status={item.status}>
          <h3>{publicChatText(item.text)}</h3>
          <div className="row wrap">
            <Tag>{categoryLabel(item.category)}</Tag>
            {item.spaceId && <span className="meta">功能区归属：{spaceLabels[item.spaceId] || '已归档功能区'}</span>}
            {item.status === 'stopped' && <Tag>已停用，不会再提起</Tag>}
          </div>
          <SourceQuote port={port} source={item.sourceRefs[0]} />
          <Sources port={port} refs={item.sourceRefs} />
          <div className="row wrap night-me-item-actions">
            <Button
              variant="ghost"
              disabled={item.status !== 'active'}
              onClick={(event) => open({ kind: 'memory-edit', item }, event.currentTarget)}>
              修改记忆
            </Button>
            <Button
              variant="ghost"
              disabled={item.status !== 'active'}
              onClick={(event) => open({ kind: 'memory-stop', item }, event.currentTarget)}>
              停用记忆
            </Button>
            <Button variant="ghost" onClick={(event) => open({ kind: 'memory-delete', item }, event.currentTarget)}>
              删除记忆
            </Button>
          </div>
        </article>
      ))}
    </section>
  );
}
