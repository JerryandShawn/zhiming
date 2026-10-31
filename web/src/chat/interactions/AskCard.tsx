import { useState } from 'react';
import { ApiError } from '../../api/client';
import { Button } from '../../components/ui/Controls';
import type { Question } from '../types';
import { validAskAnswerReceipt, type AskAnswerContext, type AskAnswerHandler } from './contracts';
import { useInteractionGuard } from './useInteractionGuard';

type AskCardProps = {
  question: Question;
  onAnswer?: AskAnswerHandler;
  onReply?: (answer: string) => void;
  answered?: string;
  answeredOptionIds?: string[];
  composerId?: string;
};

export function InteractiveAskCard(props: AskCardProps) {
  const { question } = props;
  const identity = question.askId || JSON.stringify([question.question, question.options]);
  return <AskCard key={identity} {...props} />;
}

function AskCard({
  question,
  onAnswer,
  onReply,
  answered,
  answeredOptionIds,
  composerId = 'composer-input',
}: AskCardProps) {
  const [confirmed, setConfirmed] = useState(''),
    [choice, setChoice] = useState('');
  const [draftIds, setDraftIds] = useState<string[]>([]),
    [confirmedIds, setConfirmedIds] = useState<string[]>([]),
    [attemptedIds, setAttemptedIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [legacyPending, setLegacyPending] = useState(false);
  const guard = useInteractionGuard();
  const selected = answered === undefined ? confirmed : answered;
  const optionIds = question.optionIds ?? [];
  const identified =
    (!question.askId && !question.multi) ||
    Boolean(
      question.askId &&
      optionIds.length === question.options.length &&
      optionIds.every(Boolean) &&
      new Set(optionIds).size === optionIds.length,
    );
  const unavailable = (!onAnswer && !onReply) || Boolean(question.askId && !onAnswer) || !identified;
  const selectedIds = answeredOptionIds ?? confirmedIds;
  function contextFor(ids: string[]): AskAnswerContext | undefined {
    return question.askId ? { askId: question.askId, optionIds: ids } : undefined;
  }
  async function submit(value: string, ids: string[] = []) {
    if (
      selected ||
      legacyPending ||
      unavailable ||
      (choice && (choice !== value || JSON.stringify(attemptedIds) !== JSON.stringify(ids))) ||
      !guard.begin()
    )
      return;
    setBusy(true);
    setChoice(value);
    setAttemptedIds(ids);
    setError('');
    try {
      if (onAnswer) {
        const context = contextFor(ids);
        const result = await (context ? onAnswer(value, context) : onAnswer(value));
        if (!guard.current()) return;
        if (!validAskAnswerReceipt(result, value, context)) throw new Error('尚未收到回答确认，请用原选择重试');
        setConfirmedIds(ids);
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
      ) {
        setChoice('');
        setAttemptedIds([]);
      }
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
      data-ask-id={question.askId}
      data-answer-state={selected ? 'answered' : busy || legacyPending ? 'pending' : 'unanswered'}>
      <p className="question">{question.question}</p>
      <p className="meta">为什么问：{question.why}</p>
      <div className="ask-options">
        {question.options.map((option, index) => (
          <Button
            key={optionIds[index] || `${index}-${option}`}
            data-option-id={optionIds[index]}
            aria-pressed={
              question.multi
                ? (selected ? selectedIds : draftIds).includes(optionIds[index])
                : question.askId
                  ? Boolean(selected) && selectedIds.includes(optionIds[index])
                  : selected === option
            }
            loading={
              busy && !question.multi && (question.askId ? attemptedIds[0] === optionIds[index] : choice === option)
            }
            disabled={
              Boolean(selected) ||
              busy ||
              legacyPending ||
              unavailable ||
              Boolean(choice && (question.multi || choice !== option))
            }
            onClick={() => {
              if (!question.multi) void submit(option, optionIds[index] ? [optionIds[index]] : []);
              else
                setDraftIds((ids) =>
                  ids.includes(optionIds[index])
                    ? ids.filter((id) => id !== optionIds[index])
                    : [...ids, optionIds[index]],
                );
            }}>
            {option}
          </Button>
        ))}
        {question.multi && (
          <Button
            loading={busy}
            disabled={!draftIds.length || Boolean(selected) || busy || legacyPending || unavailable}
            onClick={() => {
              const ids = optionIds.filter((id) => draftIds.includes(id));
              const labels = question.options.filter((_, index) => ids.includes(optionIds[index]));
              void submit(labels.join('；'), ids);
            }}>
            确认选择
          </Button>
        )}
        {question.allow_free_text && (
          <Button
            variant="ghost"
            disabled={Boolean(selected) || busy || legacyPending}
            onClick={() => document.getElementById(composerId)?.focus()}>
            我自己说
          </Button>
        )}
      </div>
      {!identified && <p className="meta">这张提问暂时不能确认，刷新后再试。</p>}
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
