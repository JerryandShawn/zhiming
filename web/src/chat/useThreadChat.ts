import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { authHeaders, operationNamespace } from '../api/client';
import { createThreadController } from '../threads/controller';
import type { ThreadAcceptance } from '../threads/contracts';
import { threadSubmitPort } from '../threads/submit';
import type { ThreadView } from '../threads/projection';
import { clearPending, isCurrentChat, loadPending, newPending, saveDraft, storePending } from './storage';
import { initialStream, type CompletedTurn, type HistoryRow, type PendingChat, type StreamState } from './types';
import { useChat } from './useChat';

const threadTarget = { threadId: 'life:self', incognito: false };
const threadPayload = (operation: PendingChat) => ({
  request_id: operation.payload.request_id,
  message: operation.payload.message,
  subject_id: 'self',
  conversation_id: operation.payload.session_id,
  case_ids: operation.payload.case_ids,
  depth: 'standard' as const,
});

export function useThreadChat() {
  const legacy = useChat();
  const cache = useQueryClient();
  const namespace = useRef(operationNamespace()).current;
  const [pending, setPending] = useState(() => {
    const current = loadPending();
    return current?.thread ? current : undefined;
  });
  const [state, setState] = useState<StreamState>(() => ({ ...initialStream(), complete: true }));
  const [phase, setPhase] = useState<ThreadView['phase']>('idle');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [stopStatus, setStopStatus] = useState('');
  const [currentMessage, setCurrentMessage] = useState(() => {
    const current = loadPending();
    return current?.thread ? current.payload.message : '';
  });
  const [completedTurns, setCompletedTurns] = useState<CompletedTurn[]>([]);
  const active = useRef(false);
  const operationEpoch = useRef(0);
  const draftRevision = useRef(0);
  const abort = useRef<AbortController>();
  const controller = useRef<ReturnType<typeof createThreadController>>();

  useEffect(
    () => () => {
      abort.current?.abort();
      controller.current?.dispose();
    },
    [],
  );

  const perform = useCallback(
    async (operation: PendingChat) => {
      if (active.current || !operation.thread || namespace !== operationNamespace() || !isCurrentChat(operation))
        return;
      active.current = true;
      const epoch = ++operationEpoch.current;
      const submittedDraftRevision = draftRevision.current;
      const lifetime = new AbortController();
      abort.current = lifetime;
      setBusy(true);
      setError('');
      setStopStatus('正在核对本轮状态…');
      setPhase('checking');
      setPending(operation);
      setCurrentMessage(operation.payload.message);
      setState({ ...initialStream(), runId: operation.runId, status: '正在核对本轮状态…' });
      const current = () =>
        !lifetime.signal.aborted &&
        namespace === operationNamespace() &&
        operationEpoch.current === epoch &&
        isCurrentChat(operation);
      const owner = { signal: lifetime.signal, isCurrent: current, headers: authHeaders };
      let completed = false;
      try {
        let acceptance: ThreadAcceptance | undefined = operation.thread.acceptance;
        if (!acceptance) {
          acceptance = await threadSubmitPort((input, init) => fetch(input, init))(
            operation.thread,
            threadPayload(operation),
            owner,
          );
          if (!current()) return;
          operation.thread = { ...operation.thread, acceptance };
          operation.runId = acceptance.run_id;
          storePending(operation);
        }
        const owned = createThreadController(acceptance, {
          ...owner,
          fetcher: (input, init) => fetch(input, init),
          maxReconnects: 3,
        });
        controller.current = owned;
        owned.subscribe(() => {
          if (!current()) return;
          const snapshot = owned.getSnapshot();
          setState(snapshot.stream);
          setPhase(snapshot.phase);
          setStopStatus(snapshot.notice);
          if (snapshot.phase !== 'complete' || completed) return;
          completed = true;
          const turn = {
            requestId: operation.payload.request_id,
            runId: snapshot.stream.runId,
            prompt: operation.payload.message,
            state: snapshot.stream,
          };
          setCompletedTurns((rows) => [...rows.filter((item) => item.requestId !== turn.requestId), turn]);
          if (clearPending(operation)) {
            setPending(undefined);
            if (draftRevision.current === submittedDraftRevision) {
              legacy.setText('');
              saveDraft('', namespace);
            }
            void cache.invalidateQueries({ queryKey: ['chat', 'history', namespace] });
          }
        });
        await owned.start();
      } catch (reason) {
        if (current()) setError(reason instanceof Error ? reason.message : '本轮尚未确认，请保留原请求再核对。');
      } finally {
        if (operationEpoch.current === epoch) {
          active.current = false;
          if (namespace === operationNamespace()) setBusy(false);
        }
      }
    },
    [cache, legacy, namespace],
  );

  async function send(text: string, images: string[], forceNew = false) {
    if (legacy.pending) return legacy.send(text, images, forceNew);
    if (pending) {
      if (forceNew) {
        clearPending(pending);
        setPending(undefined);
      } else {
        if (text.trim() !== pending.payload.message || images.length || pending.payload.images.length) {
          setError('原来这一轮尚未确认完成。请继续原来这一轮，或明确开始新一轮。');
          return;
        }
        await perform(pending);
        return;
      }
    }
    if (images.length) return legacy.send(text, images, forceNew);
    if (!text.trim() || busy || active.current || legacy.busy || namespace !== operationNamespace()) return;
    try {
      const operation = newPending(text.trim(), [], 'shared', namespace);
      operation.thread = { ...threadTarget };
      storePending(operation);
      await perform(operation);
    } catch (reason) {
      if (namespace === operationNamespace())
        setError(reason instanceof Error ? reason.message : '无法保留本轮重试记录');
    }
  }

  async function cancel() {
    if (!pending) return legacy.cancel();
    if (!controller.current) {
      setStopStatus('正在等待本轮回执，收到后才能请求停止。');
      return;
    }
    setStopStatus('正在请求停止，已出的内容保留。');
    await controller.current.stop();
  }

  function restore(row: HistoryRow) {
    if (!pending) return legacy.restore(row);
    if (row.run_id !== pending.runId && row.turn_id !== pending.payload.request_id) {
      setError('请先处理尚未完成的这一轮，或明确开始新一轮，再继续之前的对话。');
      return;
    }
    void perform(pending);
  }

  const legacyView = Boolean(legacy.pending || legacy.busy);
  return {
    ...legacy,
    pending: legacyView ? legacy.pending : pending,
    state: legacyView ? legacy.state : state,
    busy: legacyView ? legacy.busy : busy,
    error: legacyView ? legacy.error : error,
    stopStatus: legacyView ? legacy.stopStatus : stopStatus,
    currentMessage: legacyView ? legacy.currentMessage : currentMessage,
    completedTurns: [...legacy.completedTurns, ...completedTurns],
    send,
    cancel,
    restore,
    resume: async (message: string) => {
      if (pending) setError('请先处理尚未完成的这一轮。');
      else await legacy.resume(message);
    },
    resumeHistory: async (row: HistoryRow, message: string) => {
      if (pending) setError('请先处理尚未完成的这一轮。');
      else await legacy.resumeHistory(row, message);
    },
    retry: () => (pending ? perform(pending) : legacy.retry()),
    setState: legacyView ? legacy.setState : setState,
    setText: (value: string) => {
      draftRevision.current++;
      legacy.setText(value);
    },
    phase,
    refresh: async () => controller.current?.refresh(),
  };
}
