import { useState } from 'react';
import { Send } from 'lucide-react';
import { Markdown } from '../components/Markdown';
import { AssistantMessage, UserMessage } from '../components/Messages';
import { Button, Disclosure, Input } from '../components/ui/Controls';
import { write } from '../api/operations';
import { ApiError } from '../api/client';
import { envelope } from './events';
import { initialStream, type HistoryRow, type Receipt, type StreamState } from './types';
import { publicChatText, publicHistoryText } from './publicProjection';

function MemoryNotice({ receipt }: { receipt: Receipt }) {
  const [undone, setUndone] = useState(false),
    [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [conflicted, setConflicted] = useState(false);
  const canUndo = receipt.write_status === 'saved' && receipt.fact_id && Number.isInteger(receipt.revision);
  async function undo() {
    if (!canUndo) return;
    setBusy(true);
    setError('');
    try {
      const result = await write<{ write_status?: string; status?: string }>(
        `chat-undo:${receipt.fact_id}`,
        'PATCH',
        `/api/memories/${encodeURIComponent(receipt.fact_id!)}`,
        {
          expected_revision: receipt.revision,
          status: 'hidden',
        },
        { receipt: (value) => value.write_status === 'stopped' || value.status === 'hidden' },
      );
      if (result.write_status !== 'stopped' && result.status !== 'hidden') throw new Error('未收到停止使用回执');
      setUndone(true);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) setConflicted(true);
      setError(reason instanceof Error ? reason.message : '尚未确认撤销');
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="memory-receipt">
      <div>
        <p>
          {undone
            ? '已撤销，不会再使用'
            : receipt.write_status === 'saved'
              ? `程序回执：已记下${receipt.summary ? `：${receipt.summary}` : ''}`
              : receipt.write_status === 'pending_confirmation'
                ? '程序回执：待你确认，尚未保存为有效记忆'
                : receipt.write_status === 'stopped'
                  ? '程序回执：已停止使用'
                  : receipt.write_status === 'deleted'
                    ? '程序回执：已删除'
                    : '程序回执：尚未确认保存成功'}
        </p>
        {error && <p role="alert">{error}</p>}
        {!canUndo && receipt.write_status === 'saved' && (
          <a className="text-link quiet-link" href="#/me?section=memory">
            查看原话与撤销
          </a>
        )}
      </div>
      {canUndo && !undone && (
        <Button loading={busy} disabled={conflicted} onClick={() => void undo()}>
          撤销使用
        </Button>
      )}
    </div>
  );
}
export function Answer({
  state,
  onReply,
  time = '本轮',
  source,
}: {
  state: StreamState;
  onReply?: (text: string) => void;
  time?: string;
  source?: string;
}) {
  const [reply, setReply] = useState('');
  return (
    <AssistantMessage revised={state.revised} time={time}>
      {source === 'feishu' && (
        <p className="meta row">
          <Send className="icon small" aria-hidden="true" />
          飞书
        </p>
      )}
      {state.status && <p role="status">{state.status}</p>}
      {state.tools.length > 0 && (
        <Disclosure title={`本轮查看了 ${state.tools.length} 个步骤`} count="查看步骤">
          <ol>
            {state.tools.map((tool, index) => (
              <li key={index}>
                {tool.summary || '核对本轮资料'} · {tool.done ? '已完成' : '进行中'}
              </li>
            ))}
          </ol>
        </Disclosure>
      )}
      {state.text && <Markdown text={publicChatText(state.text)} />}
      {state.decisions.length > 0 && (
        <div className="decision-options">
          {state.decisions.map((option, index) => (
            <section className="decision-card" key={index}>
              <h3>{option.option}</h3>
              <dl>
                {(['benefit', 'cost', 'risk', 'reversibility', 'first_step'] as const).map((key, item) => (
                  <div key={key}>
                    <dt>{['收益', '代价', '风险', '可逆性', '第一步'][item]}</dt>
                    <dd>{option[key] || '仍需核对'}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      )}
      {state.question && (
        <section className="ask-card">
          <p className="question">{state.question.question}</p>
          <p className="meta">为什么问：{state.question.why}</p>
          <div className="ask-options">
            {state.question.options.map((option) => (
              <Button key={option} disabled={!onReply} onClick={() => onReply?.(option)}>
                {option}
              </Button>
            ))}
          </div>
          {state.question.allow_free_text && onReply && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (reply.trim()) onReply(reply.trim());
              }}>
              <Input aria-label="补充回答" value={reply} onChange={(event) => setReply(event.target.value)} />
              <Button type="submit" disabled={!reply.trim()}>
                补充并继续
              </Button>
            </form>
          )}
        </section>
      )}
      {state.envelope?.interrupt && onReply && (
        <form
          className="ask-card"
          onSubmit={(event) => {
            event.preventDefault();
            if (reply.trim()) onReply(reply.trim());
          }}>
          {state.envelope.interrupt.questions.map((question) => (
            <p key={question}>{question}</p>
          ))}
          <label>
            补充本轮澄清信息
            <Input value={reply} onChange={(event) => setReply(event.target.value)} />
          </label>
          <Button type="submit" disabled={!reply.trim()}>
            补充并继续
          </Button>
        </form>
      )}
      {state.receipts.map((item) => (
        <MemoryNotice key={item.fact_id || item.proposal_id} receipt={item} />
      ))}
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
}: {
  row: HistoryRow;
  restore: (row: HistoryRow) => void;
  resume?: (row: HistoryRow, text: string) => void;
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
  if (!data.answer) data.answer = publicHistoryText(row);
  return (
    <Answer
      time={time}
      source={row.source}
      onReply={resume && data.interrupt ? (text) => resume(row, text) : undefined}
      state={{
        ...initialStream(),
        text: data.answer,
        complete: true,
        envelope: data,
        receipts: data.receipts,
        decisions: data.decisions,
      }}
    />
  );
}
