import type { PointerEvent } from 'react';
import { EyeOff } from 'lucide-react';
import { LiveComposer } from '../../chat/Composer';
import { AssistantMessage, UserMessage } from '../../components/Messages';
import { Markdown } from '../../components/Markdown';
import { Button, Switch } from '../../components/ui/Controls';
import type { PrivacySessionController } from './usePrivacySession';

function keepInputFocus(event: PointerEvent<HTMLElement>) {
  const active = document.activeElement;
  // Blurring here would move the visual viewport before the pointer can complete its click.
  if (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement) event.preventDefault();
}

export function PrivacyToggle({ active, onChange }: { active: boolean; onChange: (active: boolean) => void }) {
  return (
    <section
      className="row between wrap"
      aria-label="对话隐私模式"
      onPointerDown={(event) => {
        if (event.target instanceof Element && event.target.closest('[role="switch"]')) keepInputFocus(event);
      }}>
      <div>
        <p className="row small-text">
          <EyeOff className="icon" aria-hidden="true" />
          无痕模式
        </p>
        <p className="meta">{active ? '这段不会被记住' : '开启一段仅在本页保留的对话'}</p>
      </div>
      <Switch label="无痕模式" checked={active} onChange={onChange} />
    </section>
  );
}

export function PrivateChat({ privacy }: { privacy: PrivacySessionController }) {
  const { session } = privacy;
  if (!session) return null;
  return (
    <div
      className="page chat-page night-chat night-private-chat"
      data-page="chat"
      data-privacy="incognito"
      data-thread-id={session.id}>
      <h1 className="sr-only">无痕对话</h1>
      <div className="chat-layout">
        <div className="chat-main">
          <section className="memory-receipt row between wrap" aria-label="无痕对话提示">
            <div>
              <p className="row">
                <EyeOff className="icon" aria-hidden="true" />
                无痕对话
              </p>
              <p className="small-text">这段不会被记住</p>
            </div>
            <Button variant="ghost" onPointerDown={keepInputFocus} onClick={privacy.exit}>
              退出无痕
            </Button>
          </section>
          <div className="chat-messages" tabIndex={0} role="region" aria-label="对话内容">
            <div className="chat-inner">
              <p className="meta">这段只在当前页面保留，退出无痕或刷新后会清空，不会写入长期记忆。</p>
              {session.messages.map((message) =>
                message.role === 'user' ? (
                  <UserMessage key={message.id} time="本轮">
                    {message.text}
                    {message.images.map((image, index) => (
                      <img key={index} src={image} alt={`本轮附图${index + 1}`} />
                    ))}
                  </UserMessage>
                ) : message.text ? (
                  <AssistantMessage key={message.id} time="本地演示">
                    <Markdown text={message.text} />
                  </AssistantMessage>
                ) : null,
              )}
              {session.status && (
                <p role="status" className="meta">
                  {session.status}
                </p>
              )}
              <p className="meta">本地演示，未连接模型。连续 24 小时未使用也会清空。</p>
            </div>
          </div>
          <LiveComposer
            key={session.id}
            draft={session.draft}
            setText={privacy.setDraft}
            busy={session.busy}
            images={session.images}
            setImages={privacy.setImages}
            send={() => void privacy.send()}
            stop={privacy.stop}
          />
        </div>
        <aside className="chat-aside stack">
          <section className="stack small">
            <h2>只聊这一段</h2>
            <p>无痕内容不会进入长期记忆、普通对话或后续整理。退出后不能恢复。</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
