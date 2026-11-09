import { useEffect, useRef, useState } from 'react';
import { UserMessage } from '../components/Messages';
import { Button, Switch } from '../components/ui/Controls';
import { Answer, HistoryMessage } from '../chat/Answers';
import { LiveComposer } from '../chat/Composer';
import { useChat } from '../chat/useChat';
import { useThreadChat } from '../chat/useThreadChat';
import { object, string } from '../chat/types';
import { publicChatText } from '../chat/publicProjection';
import { createMemoryReceiptRegistry } from '../chat/interactions/memoryProjection';

type ViewModel = ReturnType<typeof useChat> & Partial<Pick<ReturnType<typeof useThreadChat>, 'phase' | 'refresh'>>;

function ChatView({ chat }: { chat: ViewModel }) {
  const receiptRegistry = useRef(createMemoryReceiptRegistry()).current;
  const historyReadPending = useRef(false);
  const mounted = useRef(true);
  const [historyRetrying, setHistoryRetrying] = useState(false);
  const [images, setImages] = useState(chat.pending?.payload.images || []);
  const inHistory = (requestId: string, runId: string, completed = false) =>
    chat.historyRows.some(
      (row) =>
        (!completed || row.role === 'assistant') &&
        ((Boolean(requestId) && row.turn_id === requestId) ||
          (Boolean(runId) &&
            (row.run_id === runId || string(object(object(object(row.meta).meta).core_run).run_id) === runId))),
    );
  useEffect(() => {
    if (chat.state.complete) setImages([]);
  }, [chat.state.complete]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  async function readHistory(mode: 'earlier' | 'retry') {
    if (historyReadPending.current || chat.history.isFetching) return;
    historyReadPending.current = true;
    if (mode === 'retry') setHistoryRetrying(true);
    try {
      // Refetch the same GET query; no session reset or conversation action.
      if (mode === 'earlier') await chat.history.fetchNextPage({ cancelRefetch: false });
      else await chat.history.refetch({ cancelRefetch: false });
    } catch {
      // React Query retains confirmed rows and owns the retry error display.
    } finally {
      historyReadPending.current = false;
      if (mounted.current && mode === 'retry') setHistoryRetrying(false);
    }
  }
  return (
    <div className="page chat-page" data-page="chat" data-runtime={chat.phase ? 'thread-v4' : 'v3'}>
      <h1 className="sr-only">和明镜对话</h1>
      <div className="chat-layout">
        <div className="chat-main">
          <div className="chat-messages" tabIndex={0} role="region" aria-label="对话内容">
            <div className="chat-inner">
              {chat.history.hasNextPage && (
                <Button
                  loading={chat.history.isFetchingNextPage}
                  disabled={historyRetrying || chat.history.isFetching}
                  onClick={() => void readHistory('earlier')}>
                  查看更早对话
                </Button>
              )}
              {chat.history.isLoading && !historyRetrying && <p role="status">正在读取历史对话…</p>}
              {(chat.history.error || historyRetrying) && (
                <div className="stack small" role={historyRetrying ? 'status' : 'alert'}>
                  <p>{historyRetrying ? '正在重新读取历史对话…' : '历史暂时没有读取完整，可以稍后重试。'}</p>
                  <Button
                    loading={historyRetrying}
                    disabled={chat.history.isFetching}
                    onClick={() => void readHistory('retry')}>
                    重新读取历史对话
                  </Button>
                </div>
              )}
              {chat.historyRows.map((row) => (
                <HistoryMessage
                  receiptRegistry={receiptRegistry}
                  key={`${row.cursor}:${row.role}`}
                  row={row}
                  restore={chat.restore}
                  onAskReply={
                    row === chat.historyRows.at(-1) && !chat.busy && !chat.pending
                      ? (text) => void chat.send(text, [])
                      : undefined
                  }
                  resume={chat.busy ? undefined : (row, text) => void chat.resumeHistory(row, text)}
                />
              ))}
              {chat.completedTurns
                .filter((turn) => !inHistory(turn.requestId, turn.runId, true))
                .map((turn) => (
                  <section key={turn.requestId}>
                    <UserMessage time="本轮">{publicChatText(turn.prompt)}</UserMessage>
                    <Answer
                      receiptRegistry={receiptRegistry}
                      state={turn.state}
                      onReply={
                        chat.busy || turn.runId !== chat.state.runId
                          ? undefined
                          : (text) => void (chat.state.envelope?.interrupt ? chat.resume(text) : chat.send(text, []))
                      }
                    />
                  </section>
                ))}
              {!chat.state.complete &&
                chat.currentMessage &&
                !inHistory(chat.pending?.payload.request_id || '', chat.state.runId) && (
                  <UserMessage time="本轮">{publicChatText(chat.currentMessage)}</UserMessage>
                )}
              {!chat.state.complete && (chat.state.runId || chat.state.text || chat.state.status) && (
                <Answer
                  receiptRegistry={receiptRegistry}
                  state={chat.state.status === chat.stopStatus ? { ...chat.state, status: '' } : chat.state}
                  onReply={
                    chat.busy
                      ? undefined
                      : (text) => void (chat.state.envelope?.interrupt ? chat.resume(text) : chat.send(text, []))
                  }
                />
              )}
              {chat.error && <p role="alert">{chat.error}</p>}
              {chat.stopStatus && (
                <p role="status" className="meta" aria-label="停止反馈">
                  {chat.stopStatus}
                </p>
              )}
              {chat.phase === 'needs_check' && chat.refresh && (
                <Button onClick={() => void chat.refresh?.()}>重新核对本轮状态</Button>
              )}
              {chat.pending && !chat.busy && (
                <section className="ask-card">
                  <p>本轮记录已保留，继续会沿用已保存的问题与资料。</p>
                  <div className="row wrap">
                    <Button onClick={() => void chat.retry()}>继续原来这一轮</Button>
                    <Button
                      variant="ghost"
                      onClick={() => void chat.send(chat.draft || chat.pending!.payload.message, images, true)}>
                      明确开始新一轮
                    </Button>
                  </div>
                </section>
              )}
            </div>
          </div>
          <LiveComposer
            draft={chat.draft}
            setText={chat.setText}
            busy={chat.busy}
            images={images}
            setImages={setImages}
            send={() => void chat.send(chat.draft, images)}
            stop={() => void chat.cancel()}
          />
        </div>
        <aside className="chat-aside">
          <section>
            <h2>这轮对话</h2>
            <p>资料与记忆以程序回执为准。</p>
            <a className="text-link quiet-link" href="#/me?section=memory">
              查看记忆与来源
            </a>
          </section>
          <div className="row between">
            <span>无痕模式</span>
            <Switch label="无痕模式" checked={false} disabled onChange={() => undefined} />
          </div>
          <p className="meta">无痕对话正在准备，暂不可用。</p>
        </aside>
      </div>
    </div>
  );
}

function LegacyChat() {
  return <ChatView chat={useChat()} />;
}
function ThreadChat() {
  return <ChatView chat={useThreadChat()} />;
}
export default function Chat({ transport = 'v3' }: { transport?: 'v3' | 'v4' }) {
  return transport === 'v4' ? <ThreadChat /> : <LegacyChat />;
}
