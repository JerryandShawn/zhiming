import { useMemo } from 'react';
import { Send } from 'lucide-react';
import { Markdown } from '../components/Markdown';
import { AssistantMessage, UserMessage } from '../components/Messages';
import { Button, Disclosure } from '../components/ui/Controls';
import { envelope } from './events';
import { initialStream, type HistoryRow, type StreamState } from './types';
import { publicChatText, publicHistoryText } from './publicProjection';
import { InteractiveAskCard } from './interactions/AskCard';
import { ClarificationCard } from './interactions/ClarificationCard';
import { DecisionCards } from './interactions/DecisionCards';
import { MemoryReceipts } from './interactions/MemoryReceipts';
import { ToolProgress } from './interactions/ToolProgress';
import type { AskAnswerHandler, MemoryActionHandler, MemoryCommands } from './interactions/contracts';
import type { MemoryReceiptRegistry } from './interactions/memoryProjection';

export type AnswerInteractions = {
  onAskAnswer?: AskAnswerHandler;
  answered?: string;
  answeredOptionIds?: string[];
  memoryCommands?: MemoryCommands;
  onMemoryAction?: MemoryActionHandler;
  reviewPending?: boolean;
  composerId?: string;
  receiptRegistry?: MemoryReceiptRegistry;
};
export function Answer({
  state,
  onReply,
  time = '本轮',
  source,
  onAskAnswer,
  answered,
  answeredOptionIds,
  memoryCommands,
  onMemoryAction,
  reviewPending,
  composerId,
  receiptRegistry,
}: AnswerInteractions & {
  state: StreamState;
  onReply?: (text: string) => void;
  time?: string;
  source?: string;
}) {
  const commands = useMemo(
    () =>
      memoryCommands ??
      (onMemoryAction
        ? {
            supports: () => true,
            execute: onMemoryAction,
          }
        : undefined),
    [memoryCommands, onMemoryAction],
  );
  return (
    <AssistantMessage revised={state.revised} pending={reviewPending ?? state.reviewPending ?? false} time={time}>
      {source === 'feishu' && (
        <p className="meta row">
          <Send className="icon small" aria-hidden="true" />
          飞书
        </p>
      )}
      {state.text && <Markdown text={publicChatText(state.text)} />}
      <ToolProgress tools={state.tools} status={state.status} complete={state.complete || Boolean(state.error)} />
      <DecisionCards options={state.decisions} />
      {state.question && (
        <InteractiveAskCard
          key={`${state.runId}:${state.question.askId || state.question.question}`}
          question={state.question}
          onAnswer={onAskAnswer}
          onReply={onReply}
          answered={answered ?? state.answered}
          answeredOptionIds={answeredOptionIds}
          composerId={composerId}
        />
      )}
      {state.envelope?.interrupt && onReply && (
        <ClarificationCard questions={state.envelope.interrupt.questions} onReply={onReply} />
      )}
      <MemoryReceipts receipts={state.receipts} commands={commands} registry={receiptRegistry} />
      {state.envelope?.professional_appendix || state.envelope?.evidence.length ? (
        <Disclosure title="专业依据与来源">
          {state.envelope?.evidence.map((item, index) => (
            <section key={index}>
              <h3>依据 {index + 1}</h3>
              <p>{item.claim}</p>
              <p className="meta">来源标识：{item.ref}</p>
            </section>
          ))}
          {state.envelope?.professional_appendix && <Markdown text={state.envelope.professional_appendix} />}
        </Disclosure>
      ) : null}
      {state.error && <p role="alert">{state.error}</p>}
    </AssistantMessage>
  );
}

export function HistoryMessage({
  row,
  restore,
  resume,
  onAskReply,
  receiptRegistry,
}: {
  row: HistoryRow;
  restore: (row: HistoryRow) => void;
  resume?: (row: HistoryRow, text: string) => void;
  onAskReply?: (text: string) => void;
  receiptRegistry?: MemoryReceiptRegistry;
}) {
  const date = new Date(row.at);
  const time = Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
  if (row.role === 'user')
    return (
      <>
        <UserMessage time={time} feishu={row.source === 'feishu'}>
          {publicHistoryText(row)}
        </UserMessage>
        {['failed', 'stale', 'interrupted', 'running', 'queued'].includes(row.status || '') && (
          <Button onClick={() => restore(row)}>继续原来这一轮</Button>
        )}
      </>
    );
  if (row.role !== 'assistant') return null;
  const data = envelope(row.meta);
  if (!data.answer && data.schema !== 'core4.0') data.answer = publicHistoryText(row);
  return (
    <Answer
      time={time}
      source={row.source}
      receiptRegistry={receiptRegistry}
      onReply={resume && data.interrupt ? (text) => resume(row, text) : data.question ? onAskReply : undefined}
      state={{
        ...initialStream(),
        text: data.answer,
        complete: true,
        envelope: data,
        receipts: data.receipts,
        decisions: data.decisions,
        question: data.question,
        review: data.review,
        revised: data.review?.state === 'revised',
        revisionId: data.review?.revisionId,
      }}
    />
  );
}
