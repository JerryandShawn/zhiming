import { useSyncExternalStore } from 'react';
import { Lock } from 'lucide-react';
import { Tag } from '../components/ui/Controls';
import { useSpacesDemo } from './store';
import './chat.css';

const subscribe = (listener: () => void) => {
  window.addEventListener('hashchange', listener);
  return () => window.removeEventListener('hashchange', listener);
};

export function chatHref(spaceId = 'all', topicId?: string) {
  const query = new URLSearchParams({ space: spaceId });
  if (topicId) query.set('topic', topicId);
  return `#/chat?${query}`;
}

export function useSpaceRoute() {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  const data = useSpacesDemo((state) => state.data);
  const query = new URLSearchParams(hash.split('?')[1]);
  const requestedSpace = query.get('space') || 'all';
  const space = data.spaces.find((item) => item.id === requestedSpace && !item.hidden);
  const topics = data.topics
    .filter((item) => item.spaceId === space?.id)
    .sort((a, b) => b.lastAt.localeCompare(a.lastAt));
  const requestedTopic = query.get('topic');
  const topic = topics.find((item) => item.id === requestedTopic) || topics[0];
  const invalid =
    (requestedSpace !== 'all' && !space) ||
    Boolean(requestedTopic && !topics.some((item) => item.id === requestedTopic));
  return { space, topics, topic, invalid };
}

export function formatSpaceTime(at: string) {
  const date = new Date(at);
  return Number.isNaN(date.valueOf())
    ? '暂无对话'
    : new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'Asia/Shanghai',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      }).format(date);
}

export function SpaceNavigation({ mobile = false }: { mobile?: boolean }) {
  const spaces = useSpacesDemo((state) => state.data.spaces);
  const { space: current } = useSpaceRoute();
  const rows = [...spaces].filter((space) => !space.hidden).sort((a, b) => a.order - b.order);
  return (
    <nav className={mobile ? 'spaces-tabs' : 'spaces-navigation'} aria-label={mobile ? '手机功能区' : '功能区'}>
      <a href={chatHref()} className="spaces-link" aria-current={!current ? 'page' : undefined}>
        <Tag tone={!current ? 'accent' : 'neutral'}>全部</Tag>
        {!mobile && <span className="meta">按时间看所有区</span>}
      </a>
      {rows.map((space) => (
        <a
          key={space.id}
          href={chatHref(space.id)}
          className="spaces-link"
          aria-current={current?.id === space.id ? 'page' : undefined}>
          <span className="row">
            <Tag tone={current?.id === space.id ? 'accent' : 'neutral'}>
              {space.sensitive && <Lock className="icon small" role="img" aria-label="敏感区" />}
              {space.name}
            </Tag>
            {!mobile && (
              <span className="meta" aria-label={`${space.unread} 条未读`}>
                {space.unread} 条未读
              </span>
            )}
          </span>
          {!mobile && (
            <time className="meta" dateTime={space.lastAt}>
              最近 {formatSpaceTime(space.lastAt)}
            </time>
          )}
        </a>
      ))}
    </nav>
  );
}
