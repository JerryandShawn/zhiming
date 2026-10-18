import { useState } from 'react';
import { ApiError } from '../../api/client';
import { Button } from '../../components/ui/Controls';
import type { Question } from '../types';
import type { AskAnswerHandler } from './contracts';
import { useInteractionGuard } from './useInteractionGuard';

export function InteractiveAskCard({
  question,
  onAnswer,
  onReply,
  answered,
  composerId = 'composer-input',
}: {
  question: Question;
  onAnswer?: AskAnswerHandler;
  onReply?: (answer: string) => void;
  answered?: string;
  composerId?: string;
}) {
  const [confirmed, setConfirmed] = useState(''),
    [choice, setChoice] = useState('');
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [legacyPending, setLegacyPending] = useState(false);
  const guard = useInteractionGuard();
  const selected = answered === undefined ? confirmed : answered;
  const unavailable = !onAnswer && !onReply;
  async function submit(value: string) {
    if (selected || legacyPending || unavailable || (choice && choice !== value) || !guard.begin()) return;
    setBusy(true);
    setChoice(value);
    setError('');
    try {
      if (onAnswer) {
        const result = await onAnswer(value);
        if (!guard.current()) return;
        if (!result || result.status !== 'accepted' || result.answer !== value || !result.request_id)
          throw new Error('尚未收到回答确认，请用原选择重试');
        setConfirmed(value);
      } else {
        onReply?.(value);
        if (guard.current()) setLegacyPending(true);
      }
    } catch (reason) {
      if (!guard.current()) return;
      if (
        reason instanceof ApiError &&
        reason.status >= 400 &&
        reason.status < 500 &&
        ![401, 408, 429].includes(reason.status)
      )
        setChoice('');
      setError(reason instanceof Error ? reason.message : '尚未收到确认，请用原选择重试');
    } finally {
      guard.end();
      if (guard.current()) setBusy(false);
    }
  }
  return (
    <section
      className="ask-card"
      aria-label="明镜的提问"
      data-answer-state={selected ? 'answered' : busy || legacyPending ? 'pending' : 'unanswered'}>
      <p className="question">{question.question}</p>
      <p className="meta">为什么问：{question.why}</p>
      <div className="ask-options">
        {question.options.map((option, index) => (
          <Button
            key={`${index}-${option}`}
            aria-pressed={selected === option}
            loading={busy && choice === option}
            disabled={Boolean(selected) || busy || legacyPending || unavailable || Boolean(choice && choice !== option)}
            onClick={() => void submit(option)}>
            {option}
          </Button>
        ))}
        {question.allow_free_text && (
          <Button
            variant="ghost"
            disabled={Boolean(selected) || busy || legacyPending}
            onClick={() => document.getElementById(composerId)?.focus()}>
            我自己说
          </Button>
        )}
      </div>
      {selected && (
        <p className="meta" role="status">
          你选了：{selected}
        </p>
      )}
      {legacyPending && !selected && (
        <p className="meta" role="status">
          选择已发出，尚未收到确认。
        </p>
      )}
      {error && (
        <p className="interaction-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
