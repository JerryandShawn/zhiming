import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { AskAnswerContext } from '../chat/interactions/contracts';
import { reduceChat } from '../chat/reducer';
import { initialStream } from '../chat/types';
import { INITIAL_DEMO_PROMPT, type DemoJob, type DemoTurn } from './conversationTypes';
import { playDemo, type DemoScenario } from './events';
import type { NightPort } from './port';
import { acceptQuestionAnswer } from './questionAnswer';
import { createInputQueue, createMockQueuePort, type InputQueue } from './queue';
import { restoreComposerFocus } from './queue/focus';
import { useConversationDraft } from './useConversationDraft';

// The ordinary conversation outlives its view. PrivateChat never receives this store.
export function useNormalConversation(port: NightPort, enabled: boolean, suppliedQueue?: InputQueue) {
  const mountId = useRef(crypto.randomUUID()).current;
  const sequence = useRef(0);
  const [queue] = useState(() => suppliedQueue ?? createInputQueue(createMockQueuePort(), `normal:${mountId}:0`));
  const queued = useSyncExternalStore(queue.subscribe, queue.getSnapshot);
  const input = useConversationDraft();
  const submitted = useRef(new Map<string, { scope: string; input: ReturnType<typeof input.capture> }>());
  const [state, setState] = useState(initialStream);
  const latest = useRef(state);
  const [job, setJob] = useState<DemoJob>({
    id: 'cards-0',
    scenario: 'cards',
    prompt: INITIAL_DEMO_PROMPT,
    images: [],
  });
  const jobRef = useRef(job);
  const [turns, setTurns] = useState<DemoTurn[]>([]);
  const [answered, setAnswered] = useState('');
  const [answeredOptionIds, setAnsweredOptionIds] = useState<string[]>();
  const answerRef = useRef({ text: '', optionIds: undefined as string[] | undefined });
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);
  const [halted, setHalted] = useState(false);
  const busyRef = useRef(false),
    haltedRef = useRef(false),
    enabledRef = useRef(enabled);
  const controller = useRef<AbortController>();
  const generation = useRef(0),
    played = useRef('');
  enabledRef.current = enabled;
  jobRef.current = job;

  const start = useCallback((next: DemoJob) => {
    const previous = latest.current;
    if (previous.runId || previous.text) {
      const old = {
        ...jobRef.current,
        state: previous,
        answered: answerRef.current.text,
        answeredOptionIds: answerRef.current.optionIds,
      };
      setTurns((items) => [...items.filter((item) => item.id !== old.id), old]);
    }
    busyRef.current = true;
    jobRef.current = next;
    setJob(next);
  }, []);
  useEffect(() => {
    if (!enabled || (played.current === job.id && (latest.current.complete || latest.current.error))) return;
    const abort = new AbortController(),
      epoch = ++generation.current;
    const valid = () => !abort.signal.aborted && generation.current === epoch && enabledRef.current;
    played.current = job.id;
    controller.current = abort;
    latest.current = initialStream();
    answerRef.current = { text: '', optionIds: undefined };
    setState(latest.current);
    setAnswered('');
    setAnsweredOptionIds(undefined);
    setReply('');
    busyRef.current = true;
    setBusy(true);
    let terminal = false;
    void playDemo(
      job.scenario,
      (event) => {
        if (!valid()) return;
        latest.current = reduceChat(latest.current, event);
        setState(latest.current);
        if (event.type === 'final' || event.type === 'error') {
          terminal = true;
          haltedRef.current = event.type === 'error';
          setHalted(haltedRef.current);
          busyRef.current = false;
          setBusy(false);
        }
      },
      abort.signal,
      100,
      { runId: `local-${mountId}-${job.id}` },
    )
      .then(() => {
        if (valid() && !terminal) {
          busyRef.current = false;
          setBusy(false);
          haltedRef.current = true;
          setHalted(true);
          setReply('这轮尚未收到完成确认，排队消息仍保留。');
        }
      })
      .catch((reason: unknown) => {
        if (!valid()) return;
        busyRef.current = false;
        setBusy(false);
        haltedRef.current = true;
        setHalted(true);
        setReply(reason instanceof Error ? reason.message : '演示暂时停下了，排队消息仍保留。');
      });
    return () => {
      abort.abort();
      busyRef.current = false;
    };
  }, [enabled, job.id, job.scenario, mountId]);

  useEffect(() => {
    if (!enabled || busyRef.current || haltedRef.current || !latest.current.complete) return;
    busyRef.current = true;
    const item = queue.claimNext();
    if (!item) {
      busyRef.current = false;
      return;
    }
    start({ id: `queued-${++sequence.current}`, scenario: 'queued', prompt: item.text, images: [...item.images] });
  }, [enabled, busy, state.complete, queued.revision, queue, start]);

  async function answer(text: string, context?: AskAnswerContext) {
    const captured = input.capture(),
      currentJob = jobRef.current.id,
      scope = queue.getSnapshot().scope_id;
    const question = latest.current.question;
    const receipt = await acceptQuestionAnswer(
      port,
      question,
      text,
      context,
      `local-answer-${mountId}-${currentJob}`,
      () =>
        jobRef.current.id === currentJob &&
        queue.getSnapshot().scope_id === scope &&
        (!question?.askId || latest.current.question?.askId === question.askId),
    );
    answerRef.current = { text: receipt.answer, optionIds: receipt.optionIds };
    setAnswered(receipt.answer);
    setAnsweredOptionIds(receipt.optionIds);
    input.clearSubmitted(captured, false);
    setReply('已收到你的选择。接下来会开启新一轮对话（本地演示）。');
    return receipt;
  }
  async function enqueue() {
    if (queue.getSnapshot().items.some((item) => item.state === 'pending')) return;
    const captured = input.capture(),
      scope = queue.getSnapshot().scope_id;
    const previous = new Set(queue.getSnapshot().items.map((item) => item.id));
    const task = queue.enqueue({
      text: captured.text,
      images: captured.images,
      after_run_id: latest.current.runId || `local-${mountId}-${jobRef.current.id}`,
    });
    const pending = queue.getSnapshot().items.find((item) => !previous.has(item.id));
    if (pending) submitted.current.set(pending.id, { scope, input: captured });
    const result = await task;
    if (result.status === 'accepted' && queue.getSnapshot().scope_id === scope) {
      input.clearSubmitted(captured);
      submitted.current.delete(result.item_id);
    } else if (result.status === 'rejected' && queue.getSnapshot().scope_id === scope) setReply(result.message);
    return result;
  }
  async function retryQueued(id: string) {
    const oldError = queue.getSnapshot().items.find((item) => item.id === id)?.error;
    const captured = submitted.current.get(id),
      result = await queue.retry(id);
    if (
      captured &&
      result.status === 'accepted' &&
      result.action === 'enqueue' &&
      queue.getSnapshot().scope_id === captured.scope
    ) {
      input.clearSubmitted(captured.input);
      submitted.current.delete(id);
      setReply((current) => (oldError && current === oldError ? '' : current));
    }
  }
  async function cancelQueued(id: string) {
    const previous = document.activeElement,
      scope = queue.getSnapshot().scope_id;
    const result = await queue.cancel(id);
    if (result.status === 'accepted' && result.scope_id === scope && queue.getSnapshot().scope_id === scope) {
      submitted.current.delete(id);
      restoreComposerFocus(previous);
    }
  }
  function pause() {
    ++generation.current;
    controller.current?.abort();
    busyRef.current = false;
    setBusy(false);
  }
  function stop() {
    const previous = document.activeElement;
    setReply('正在请求停止…');
    pause();
    haltedRef.current = true;
    setHalted(true);
    latest.current = { ...latest.current, complete: true, status: '' };
    setState(latest.current);
    setReply('已停止本地演示，排队消息仍保留，可继续处理下一条。');
    restoreComposerFocus(previous);
  }
  function clearQueueForPrivacy() {
    submitted.current.clear();
    queue.reset(`normal:${mountId}:privacy-${++sequence.current}`);
  }
  function replay(scenario: DemoScenario) {
    submitted.current.clear();
    pause();
    queue.reset(`normal:${mountId}:replay-${++sequence.current}`);
    haltedRef.current = false;
    setHalted(false);
    setTurns([]);
    latest.current = initialStream();
    start({ id: `${scenario}-${sequence.current}`, scenario, prompt: INITIAL_DEMO_PROMPT, images: [] });
  }
  function continueQueue() {
    if (!enabledRef.current || busyRef.current) return;
    const previous = document.activeElement;
    busyRef.current = true;
    const item = queue.claimNext();
    if (!item) {
      busyRef.current = false;
      setReply('请先等接收完成，或在排队列表中重试、取消尚未确认的消息。');
      return;
    }
    haltedRef.current = false;
    setHalted(false);
    start({ id: `queued-${++sequence.current}`, scenario: 'queued', prompt: item.text, images: [...item.images] });
    restoreComposerFocus(previous);
  }
  function send() {
    if (!busyRef.current && latest.current.question && !answerRef.current.text)
      void answer(input.capture().text).catch((reason: unknown) =>
        setReply(reason instanceof Error ? reason.message : '尚未收到确认。'),
      );
    else void enqueue();
  }
  return {
    state,
    scenario: job.scenario,
    round: sequence.current,
    review: state.reviewPending ?? false,
    ...input,
    answered,
    answeredOptionIds,
    reply,
    busy,
    answer,
    replay,
    pause,
    stop,
    send,
    queue,
    queued,
    turns,
    prompt: job.prompt,
    promptImages: job.images,
    halted,
    continueQueue,
    clearQueueForPrivacy,
    retryQueued,
    cancelQueued,
    submitting: queued.items.some((item) => item.state === 'pending'),
  };
}
export type NormalConversation = ReturnType<typeof useNormalConversation>;
