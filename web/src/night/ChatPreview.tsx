import { useEffect, useRef, useState } from 'react';
import { Answer } from '../chat/Answers';
import { LiveComposer } from '../chat/Composer';
import { reduceChat } from '../chat/reducer';
import { initialStream } from '../chat/types';
import type { MemoryReceiptRegistry } from '../chat/interactions/memoryProjection';
import { UserMessage } from '../components/Messages';
import { Button } from '../components/ui/Controls';
import { playDemo, type DemoScenario } from './events';
import type { NightPort } from './port';

export default function ChatPreview({
  port,
  receiptRegistry,
}: {
  port: NightPort;
  receiptRegistry: MemoryReceiptRegistry;
}) {
  const [state, setState] = useState(initialStream);
  const [scenario, setScenario] = useState<DemoScenario>('cards');
  const [round, setRound] = useState(0);
  const [review, setReview] = useState(false);
  const [draft, setDraft] = useState('');
  const [images, setImages] = useState<string[]>([]);
  const [answered, setAnswered] = useState('');
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(true);
  const controller = useRef<AbortController>();
  const mountId = useRef(crypto.randomUUID()).current;
  useEffect(() => {
    const abort = new AbortController();
    controller.current = abort;
    setState(initialStream());
    setReview(false);
    setAnswered('');
    setReply('');
    setBusy(true);
    void playDemo(
      scenario,
      (event, pending) => {
        setState((current) => reduceChat(current, event));
        if (pending !== undefined) setReview(pending);
        if (event.type === 'final' || event.type === 'error') {
          setBusy(false);
          setReview(false);
        }
      },
      abort.signal,
    ).catch((reason: unknown) => {
      if (!abort.signal.aborted) setReply(reason instanceof Error ? reason.message : '演示暂时停下了。');
    });
    return () => abort.abort();
  }, [round, scenario]);
  async function answer(text: string) {
    const receipt = await port.answer(text, `local-answer-${mountId}-${scenario}-${round}`);
    setAnswered(receipt.answer);
    setDraft('');
    setReply('已收到你的选择。接下来会开启新一轮对话（本地演示）。');
    return receipt;
  }
  function replay(next: DemoScenario) {
    setScenario(next);
    setRound((value) => value + 1);
  }
  return (
    <div className="page chat-page night-chat" data-page="chat" data-scenario={scenario} data-complete={state.complete}>
      <h1 className="sr-only">和明镜对话 · 本地交互预览</h1>
      <div className="night-controls row wrap" role="group" aria-label="演示片段">
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
            send={() => {
              if (state.question && !answered) void answer(draft);
              else {
                setReply('这是本地演示，开放式回答将在接入后提供。');
                setDraft('');
              }
            }}
            stop={() => {
              controller.current?.abort();
              setBusy(false);
              setReview(false);
              setState((current) => ({ ...current, complete: true, status: '' }));
              setReply('已停止本地演示，尚未完成的步骤没有确认。');
            }}
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
