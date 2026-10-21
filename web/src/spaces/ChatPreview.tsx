import { Fragment, useState } from 'react';
import { AssistantMessage, UserMessage } from '../components/Messages';
import { Button, Textarea } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import { RouteBadge } from './RouteBadge';
import { chatHref, formatSpaceTime, SpaceNavigation, useSpaceRoute } from './SpaceNavigation';
import { useSpacesDemo } from './store';
import StudyWorkspace from '../study/StudyWorkspace';
import './chat.css';

export default function ChatPreview() {
  const data = useSpacesDemo((state) => state.data);
  const { space, topics, topic, invalid } = useSpaceRoute();
  const [draft, setDraft] = useState('');
  const [inputRoute, setInputRoute] = useState<{ origin: string; spaceId: string; topicId: string }>();
  const origin = `${space?.id || 'all'}:${topic?.id || ''}`;
  const chosenInput = inputRoute?.origin === origin ? inputRoute : undefined;
  const composerSpace = chosenInput?.spaceId || space?.id || 'daily';
  const composerTopic =
    chosenInput?.topicId || topic?.id || data.topics.find((item) => item.spaceId === composerSpace)?.id || '';
  const messages = data.messages
    .filter((message) => !space || (message.spaceId === space.id && message.topicId === topic?.id))
    .sort((a, b) => a.at.localeCompare(b.at));
  const Workspace = space?.id === 'study' ? StudyWorkspace : Fragment;
  return (
    <div className="page spaces-chat" data-page="chat" data-runtime="spaces-demo">
      <h1 className="sr-only">功能区对话预览</h1>
      <div className="spaces-mobile-navigation">
        <SpaceNavigation mobile />
      </div>
      {invalid && (
        <p className="meta" role="status">
          这个区或话题暂时找不到，已显示可用的示例对话。
        </p>
      )}
      <div className={`spaces-chat-columns ${space ? '' : 'spaces-all'}`}>
        <aside className="spaces-topic-list" aria-label="话题列表">
          <h2>{space?.name || '全部对话'}</h2>
          <p className="small-text secondary-text">{space?.description || '沿着时间，看所有区的近况。'}</p>
          {space ? (
            <nav aria-label="区内话题">
              {topics.map((item) => (
                <a
                  key={item.id}
                  href={chatHref(space.id, item.id)}
                  className="spaces-topic-link"
                  aria-current={topic?.id === item.id ? 'page' : undefined}>
                  <span>{item.title}</span>
                  <span className="meta">
                    {item.status === 'case' ? '事项 · ' : item.status === 'archived' ? '已归档 · ' : ''}
                    {item.messageIds.length} 条消息
                  </span>
                  <time className="meta" dateTime={item.lastAt}>
                    {formatSpaceTime(item.lastAt)}
                  </time>
                </a>
              ))}
              {!topics.length && <p className="small-text">这个区还没有话题。</p>}
            </nav>
          ) : (
            <p className="meta">每条回答下面都保留归区标签。</p>
          )}
        </aside>
        <section className="spaces-conversation" aria-label="示例对话">
          <header className="spaces-conversation-heading">
            <h2 tabIndex={-1}>{space ? topic?.title || '还没有话题' : '全部 · 按时间'}</h2>
            <p className="meta">合成对话 · 本地模拟 · 刷新重置</p>
          </header>
          {space && (
            <div className="spaces-mobile-topics field">
              话题
              <Select
                label="当前话题"
                value={topic?.id || ''}
                options={
                  topics.length
                    ? topics.map((item) => ({ value: item.id, label: item.title }))
                    : [{ value: '', label: '还没有话题' }]
                }
                onChange={(value) => {
                  window.location.hash = chatHref(space.id, value);
                  setInputRoute(undefined);
                }}
              />
            </div>
          )}
          <Workspace>
            <div className="spaces-message-list" role="log" aria-label="合成消息时间线">
              {messages.map((message) => (
                <section key={message.id} data-message={message.id}>
                  {message.role === 'user' ? (
                    <UserMessage time={formatSpaceTime(message.at)}>{message.text}</UserMessage>
                  ) : (
                    <AssistantMessage time={formatSpaceTime(message.at)}>
                      <p>{message.text}</p>
                      <RouteBadge
                        messageId={message.id}
                        spaceId={message.spaceId}
                        topicId={message.topicId}
                        secondarySpaceId={message.secondarySpaceId}
                      />
                    </AssistantMessage>
                  )}
                </section>
              ))}
              {!messages.length && <p className="secondary-text">这里还没有示例消息，可以切换其他话题。</p>}
            </div>
            <div className="spaces-composer">
              <RouteBadge
                key={origin}
                prefix="将归入"
                spaceId={composerSpace}
                topicId={composerTopic}
                onChange={(spaceId, topicId) => setInputRoute({ origin, spaceId, topicId })}
              />
              <label className="sr-only" htmlFor="spaces-preview-draft">
                本地对话草稿
              </label>
              <Textarea
                id="spaces-preview-draft"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="可以试写草稿，预览不会发送"
                rows={2}
              />
              <div className="row between wrap">
                <p className="meta">发送暂未开放；不会请求模型或保存草稿。</p>
                <Button disabled>发送</Button>
              </div>
            </div>
          </Workspace>
        </section>
      </div>
    </div>
  );
}
