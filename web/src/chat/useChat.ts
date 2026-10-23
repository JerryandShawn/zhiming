import { useCallback, useEffect, useRef, useState } from 'react';
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { api, operationNamespace, useAuth } from '../api/client';
import { clearPending, isCurrentChat, loadPending, newPending, readDraft, saveDraft, storePending } from './storage';
import { executeV3 } from './transport';
import { reduceChat } from './reducer';
import { envelope } from './events';
import {
  initialStream,
  object,
  string,
  type CompletedTurn,
  type Envelope,
  type HistoryRow,
  type PendingChat,
  type StreamState,
} from './types';

export function useChat() {
  const token = useAuth((current) => current.token),
    loginRequired = useAuth((current) => current.loginRequired);
  const cache = useQueryClient();
  const namespace = useRef(operationNamespace()).current;
  const [pending, setPending] = useState(loadPending);
  const [draft, setDraft] = useState(() => readDraft() || loadPending()?.payload.message || '');
  const [state, setState] = useState<StreamState>(initialStream);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const [stopStatus, setStopStatus] = useState('');
  const [currentMessage, setCurrentMessage] = useState(loadPending()?.payload.message || '');
  const [completedTurns, setCompletedTurns] = useState<CompletedTurn[]>([]);
  const controller = useRef<AbortController>();
  const active = useRef(false);
  const operationEpoch = useRef(0),
    draftRevision = useRef(0);
  const history = useInfiniteQuery({
    queryKey: ['chat', 'history', namespace],
    enabled: Boolean(token) && !loginRequired,
    retry: false,
    initialPageParam: '',
    queryFn: async ({ pageParam, signal }) => {
      if (namespace !== operationNamespace()) throw new DOMException('登录已切换', 'AbortError');
      const data = await api<HistoryRow[]>(`/api/history?limit=20&before=${encodeURIComponent(pageParam)}`, { signal });
      if (namespace !== operationNamespace()) throw new DOMException('登录已切换', 'AbortError');
      return data;
    },
    getNextPageParam: (last: HistoryRow[]) => (last.length === 20 ? last[0]?.cursor : undefined),
  });
  const historyRows = [...(history.data?.pages || [])].reverse().flat();
  const setText = (value: string) => {
    if (namespace !== operationNamespace()) return;
    draftRevision.current++;
    setDraft(value);
    saveDraft(value, namespace);
  };
  useEffect(() => () => controller.current?.abort(), []);
  const perform = useCallback(
    async (operation: PendingChat, retry: boolean) => {
      if (active.current || namespace !== operationNamespace() || !isCurrentChat(operation)) return;
      active.current = true;
      const epoch = ++operationEpoch.current,
        submittedDraftRevision = draftRevision.current;
      setBusy(true);
      setError('');
      setStopStatus('');
      setState(initialStream());
      setPending(operation);
      setCurrentMessage(operation.payload.message);
      const abort = new AbortController();
      controller.current = abort;
      let complete = false;
      let projection = { ...initialStream(), runId: operation.runId };
      try {
        await executeV3(
          operation,
          retry,
          (event) => {
            if (abort.signal.aborted || namespace !== operationNamespace() || !isCurrentChat(operation)) return;
            projection = reduceChat(projection, event);
            if (event.type === 'final') {
              complete = true;
              const turn = {
                requestId: operation.payload.request_id,
                runId: projection.runId,
                prompt: operation.payload.message,
                state: projection,
              };
              setCompletedTurns((current) => [...current.filter((item) => item.requestId !== turn.requestId), turn]);
            }
            setState(projection);
          },
          abort.signal,
        );
        if (complete && !abort.signal.aborted && clearPending(operation)) {
          setPending(undefined);
          if (draftRevision.current === submittedDraftRevision) {
            setDraft('');
            saveDraft('', namespace);
          }
          void cache.invalidateQueries({ queryKey: ['chat', 'history', namespace] });
        }
      } catch (reason) {
        if (!abort.signal.aborted && isCurrentChat(operation))
          setError(reason instanceof Error ? reason.message : '本轮未完成，请继续原来这一轮');
      } finally {
        if (operationEpoch.current === epoch) {
          active.current = false;
          if (namespace === operationNamespace()) setBusy(false);
        }
      }
    },
    [cache, namespace],
  );
  async function send(text: string, images: string[], forceNew = false) {
    if (!text.trim() || busy || active.current || namespace !== operationNamespace()) return;
    try {
      if (pending && !forceNew) {
        if (
          text.trim() !== pending.payload.message ||
          JSON.stringify(images) !== JSON.stringify(pending.payload.images)
        ) {
          setError('原来这一轮尚未确认完成。请继续原来这一轮，或明确开始新一轮。');
          return;
        }
        await perform(pending, true);
        return;
      }
      if (forceNew && pending) clearPending(pending);
      await perform(newPending(text.trim(), images, 'shared', namespace), false);
    } catch (reason) {
      if (namespace === operationNamespace())
        setError(reason instanceof Error ? reason.message : '无法保留本轮重试记录');
    }
  }
  async function cancel() {
    if (!pending || namespace !== operationNamespace() || !isCurrentChat(pending)) return;
    const operation = pending,
      targetRunId = state.runId || operation.runId;
    const targetController = controller.current,
      epoch = operationEpoch.current;
    const current = () =>
      namespace === operationNamespace() &&
      isCurrentChat(operation) &&
      operationEpoch.current === epoch &&
      controller.current === targetController &&
      !targetController?.signal.aborted;
    setStopStatus('正在请求停止');
    setError('');
    try {
      const receipt = await api<{ ok: boolean; run_id: string }>(
        `/api/runs/${encodeURIComponent(targetRunId)}/cancel`,
        {
          method: 'POST',
          body: JSON.stringify({ request_id: `cancel:${operation.payload.request_id}` }),
        },
      );
      if (!current()) return;
      if (receipt.ok !== true || receipt.run_id !== targetRunId || operation.runId !== targetRunId)
        throw new Error('未收到本轮停止回执，请核对运行状态');
      targetController?.abort();
      setStopStatus('已停止本轮');
      setState((current) => ({ ...current, status: '已停止本轮' }));
    } catch (reason) {
      if (current()) {
        setStopStatus('尚未确认停止，可以重试');
        setError(reason instanceof Error ? reason.message : '尚未确认停止，请重试');
      }
    }
  }
  async function resumeFrom(runId: string, interrupt: NonNullable<Envelope['interrupt']>, message: string) {
    if (busy || active.current || !runId || namespace !== operationNamespace()) return;
    if (pending) {
      setError('请先处理尚未完成的这一轮，再补充之前的对话。');
      return;
    }
    try {
      const operation = newPending(message, [], 'shared', namespace);
      operation.resume = {
        runId,
        interrupt_id: interrupt.id,
        state_version: interrupt.state_version,
        message_id: operation.payload.request_id,
      };
      operation.runId = `resume:${runId}:${operation.payload.request_id}`;
      storePending(operation);
      await perform(operation, false);
    } catch (reason) {
      if (namespace === operationNamespace()) setError(reason instanceof Error ? reason.message : '无法保留恢复记录');
    }
  }
  function resume(message: string) {
    if (state.envelope?.interrupt) return resumeFrom(state.runId, state.envelope.interrupt, message);
  }
  function resumeHistory(row: HistoryRow, message: string) {
    const interrupt = envelope(row.meta).interrupt;
    const runId = string(object(object(object(row.meta).meta).core_run).run_id);
    if (interrupt && runId) return resumeFrom(runId, interrupt, message);
    setError('这条历史缺少可恢复的运行标识，请先核对原来这一轮。');
  }
  function restore(row: HistoryRow) {
    if (busy || active.current || namespace !== operationNamespace()) return;
    try {
      const saved = loadPending(namespace);
      if (saved) {
        if (row.run_id !== saved.runId && row.turn_id !== saved.payload.request_id) {
          setError('请先处理尚未完成的这一轮，或明确开始新一轮，再继续之前的对话。');
          return;
        }
        void perform(saved, true);
        return;
      }
      const operation = newPending(row.content, [], 'shared', namespace);
      operation.runId = row.run_id || row.turn_id;
      operation.restoreOnly = true;
      storePending(operation);
      setPending(operation);
      void perform(operation, true);
    } catch (reason) {
      if (namespace === operationNamespace()) setError(reason instanceof Error ? reason.message : '无法保留恢复记录');
    }
  }
  return {
    pending,
    draft,
    setText,
    state,
    busy,
    error,
    stopStatus,
    history,
    historyRows,
    currentMessage,
    completedTurns,
    send,
    cancel,
    resume,
    resumeHistory,
    restore,
    retry: () => pending && perform(pending, true),
    setState,
  };
}
