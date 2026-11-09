import { useEffect, useRef, useSyncExternalStore } from 'react';
import { UserMessage, AssistantMessage } from '../../components/Messages';
import { Button } from '../../components/ui/Controls';
import { publicChatText } from '../../chat/publicProjection';
import { BirthConfirmSheet } from './BirthConfirmSheet';
import { GuidedQuestion } from './GuidedQuestion';
import type { BirthPort, OnboardingController } from './types';
import './onboarding.css';

export default function OnboardingChat({
  controller,
  birth,
  onLeave,
}: {
  controller: OnboardingController;
  birth: BirthPort;
  onLeave?: () => void;
}) {
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const frame = requestAnimationFrame(() => bottom.current?.scrollIntoView({ block: 'end', behavior: 'auto' }));
    return () => cancelAnimationFrame(frame);
  }, [state.step, state.status]);
  const waiting = ['welcome', 'summary'].includes(state.step);
  return (
    <div
      className="page chat-page night-chat night-onboarding"
      data-runtime="night-onboarding"
      data-page="chat"
      data-stage={state.stage}
      data-step={state.step}
      data-status={state.status}
      data-session-id={state.sessionId}
      data-birth-status={birth.readSummary().status}
      data-birth-revision={birth.readSummary().revision}>
      <h1 className="sr-only">初次相识</h1>
      <div className="onboarding-controls row between wrap" role="group" aria-label="相识进度">
        <p className="meta">慢慢认识 · 第 {Math.min(7, state.stage)} / 7 段</p>
        <div className="row wrap">
          {state.status === 'active' && (
            <Button variant="ghost" onClick={controller.pause}>
              先到这里
            </Button>
          )}
          {onLeave && (
            <Button
              variant="ghost"
              onClick={() => {
                controller.pause();
                onLeave();
              }}>
              先聊别的
            </Button>
          )}
        </div>
      </div>
      <div className="chat-layout">
        <div className="chat-main">
          <div className="chat-messages">
            <div className="chat-inner stack">
              {state.messages
                .filter(
                  (message, index) =>
                    !(
                      state.status === 'active' &&
                      index === state.messages.length - 1 &&
                      message.role === 'assistant' &&
                      message.text === state.prompt.text
                    ),
                )
                .map((message) =>
                  message.role === 'user' ? (
                    <UserMessage key={message.id} time="这次相识">
                      {publicChatText(message.text)}
                    </UserMessage>
                  ) : (
                    <AssistantMessage key={message.id} time="这次相识">
                      <p>{publicChatText(message.text)}</p>
                    </AssistantMessage>
                  ),
                )}
              <section
                className="stack small"
                aria-label="出生资料这一步"
                hidden={state.step !== 'birth' || state.status !== 'active'}>
                <h2>{state.step === 'birth' ? publicChatText(state.prompt.text) : '出生资料'}</h2>
                <p className="meta">需要排盘时才会用到；可以只给日期，也可以暂时跳过。</p>
                <div className="row wrap">
                  <BirthConfirmSheet
                    port={birth}
                    accepted={controller.birthConfirmed}
                    disabled={state.busy || state.conflicted || state.step !== 'birth'}
                  />
                  <Button variant="ghost" disabled={state.busy} onClick={controller.skip}>
                    暂时跳过
                  </Button>
                </div>
              </section>
              {state.status === 'idle' && <Button onClick={() => controller.start()}>开始相识</Button>}
              {state.status === 'paused' ? (
                <section className="onboarding-paused stack small" aria-label="相识已暂停">
                  <h2>先到这里也很好</h2>
                  <p>已经确认的内容与这一轮草稿仍在，回来从这里继续。</p>
                  <Button onClick={controller.resume}>继续相识</Button>
                </section>
              ) : (
                state.status === 'active' &&
                (waiting ? (
                  <section className="stack small" aria-label={state.step === 'summary' ? '相识小结' : '初次见面'}>
                    <h2>{state.step === 'summary' ? '我目前了解到的你' : '你好，我是明镜'}</h2>
                    <p>{publicChatText(state.prompt.text)}</p>
                    {state.step === 'summary' && <p className="meta">见面礼还在等可核对的排盘结果。</p>}
                    <Button onClick={controller.continue}>{state.prompt.options[0] || '继续'}</Button>
                  </section>
                ) : state.step === 'birth' ? null : (
                  <GuidedQuestion key={state.step} state={state} controller={controller} />
                ))
              )}
              {state.status === 'complete' && <p role="status">初次相识先到这里。以后想起什么，我们再慢慢补充。</p>}
              {state.error && <p role="alert">这次还没有确认成功，草稿仍保留，请用原回答重试。</p>}
              {state.conflicted && <Button onClick={controller.reconcile}>核对当前进度后继续</Button>}
              <div ref={bottom} aria-hidden="true" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
