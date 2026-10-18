import type { ReactNode } from 'react';
import { Answer } from '../chat/Answers';
import { LiveComposer } from '../chat/Composer';
import type { MemoryReceiptRegistry } from '../chat/interactions/memoryProjection';
import { UserMessage } from '../components/Messages';
import { Button } from '../components/ui/Controls';
import type { NightPort } from './port';
import type { NormalConversation } from './useNormalConversation';
import { PrivacyToggle } from './privacy';

export default function ChatPreview({
  port,
  receiptRegistry,
  chat,
  onPrivacyChange,
  guideControls,
}: {
  port: NightPort;
  receiptRegistry: MemoryReceiptRegistry;
  chat: NormalConversation;
  onPrivacyChange: (active: boolean) => void;
  guideControls?: ReactNode;
}) {
  const { state, scenario, round, review, draft, setDraft, images, setImages, answered, reply, busy, answer, replay } =
    chat;
  return (
    <div className="page chat-page night-chat" data-page="chat" data-scenario={scenario} data-complete={state.complete}>
      <h1 className="sr-only">和明镜对话 · 本地交互预览</h1>
      <div className="night-controls row wrap" role="group" aria-label="演示片段">
        {guideControls}
        <PrivacyToggle active={false} onChange={onPrivacyChange} />
        <Button onClick={() => replay('cards')}>重放对话</Button>
        <Button onClick={() => replay('review')}>查看修订过程</Button>
        <Button onClick={() => replay('error')}>查看中断与重试</Button>
        <Button onClick={() => replay('resumed')}>查看恢复片段</Button>
      </div>
      <div className="chat-layout">
        <div className="chat-main">
          <div className="chat-messages">
            <div className="chat-inner">
              <UserMessage time="本地示例">有两个方向拿不定主意，想先理清怎么迈出第一步。</UserMessage>
              <Answer
                key={`${scenario}-${round}`}
                state={state}
                memoryCommands={port.memory}
                onAskAnswer={answer}
                answered={answered || undefined}
                reviewPending={review}
                receiptRegistry={receiptRegistry}
              />
              {answered && <UserMessage time="本地新一轮">{answered}</UserMessage>}
              {reply && (
                <p className="meta" role="status">
                  {reply}
                </p>
              )}
              {state.error && <Button onClick={() => replay(scenario)}>重试这一轮演示</Button>}
            </div>
          </div>
          <LiveComposer
            draft={draft}
            setText={setDraft}
            busy={busy}
            images={images}
            setImages={setImages}
            send={chat.send}
            stop={chat.stop}
          />
        </div>
        <aside className="chat-aside stack">
          <section className="stack small">
            <h2>这一轮</h2>
            <p>先听你的选择，再往下聊。记忆回执可以撤销，私人内容会先征求同意。</p>
          </section>
          <section className="stack small">
            <h2>演示范围</h2>
            <p className="meta">提问、选择、工具状态、修订和记忆回执都由本机模拟事件驱动，未连接模型或保存到服务端。</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
