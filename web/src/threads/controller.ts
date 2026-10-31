import { chatEvent } from '../chat/events';
import { reduceChat } from '../chat/reducer';
import { initialStream } from '../chat/types';
import type { RunEventV1 } from '../contracts/runEvents';
import { threadAuthorityPort, type ThreadRunState } from './authority';
import { threadAcceptance, ThreadRequestError, type ThreadAcceptance } from './contracts';
import { followThreadEvents, type ThreadFollowOptions } from './follow';
import { activeRun, authoritativeProjection, detachedView, sameFinal, type ThreadView } from './projection';
import { assertOwner, type RequestOwner } from './request';

type Options = RequestOwner & Pick<ThreadFollowOptions, 'fetcher' | 'wait' | 'retryMs' | 'maxReconnects'>;

/** Owns one in-memory run projection. It never submits/retries a message or persists a bare cursor. */
export function createThreadController(receipt: ThreadAcceptance, options: Options) {
  const accepted = threadAcceptance(receipt);
  if (accepted.runtime !== 'v4') throw new ThreadRequestError('input');
  const authority = threadAuthorityPort(options.fetcher),
    lifetime = new AbortController();
  const empty = detachedView(),
    listeners = new Set<() => void>();
  let disposed = false,
    version = 0;
  let view: ThreadView = Object.freeze({
    phase: 'idle',
    stream: { ...initialStream(), runId: accepted.run_id, threadId: accepted.thread_id },
    stopping: false,
    notice: '',
  });
  let startTask: Promise<void> | undefined, stopTask: Promise<void> | undefined, refreshTask: Promise<void> | undefined;
  let followAbort: AbortController | undefined;
  const owned = () => !disposed && !options.signal.aborted && options.isCurrent();
  const owner: RequestOwner = { signal: lifetime.signal, isCurrent: owned, headers: options.headers };
  const current = () => assertOwner(owner);
  function publish(next: ThreadView) {
    current();
    view = Object.freeze(next);
    for (const listener of listeners) {
      if (!owned()) break;
      try {
        listener();
      } catch {
        /* Display observers cannot roll back authority. */
      }
    }
    // Transports/consumers check again before their next effect. A listener may
    // detach here, including while displaying a failure, without rejecting a UI task.
  }
  const pending = (notice: string) => publish({ ...view, phase: 'needs_check', notice });
  function adopt(state: ThreadRunState, ticket: number) {
    current();
    if (ticket !== version) return false;
    publish(authoritativeProjection(view, state));
    if (!activeRun(state) || state.attempts > 1) followAbort?.abort();
    return true;
  }
  async function read() {
    const ticket = ++version;
    const state = await authority.read(accepted, owner);
    current();
    return { state, ticket, fresh: ticket === version };
  }
  function failure(error?: unknown) {
    if (!owned() || ['complete', 'interrupted', 'ended'].includes(view.phase)) return;
    const notice =
      error instanceof ThreadRequestError && error.status === 401
        ? '请重新登录，已确认的内容保留。'
        : error instanceof ThreadRequestError && error.status === 403
          ? '本轮读取权限尚未确认，请核对登录；已显示的内容保留。'
          : '连接尚未核对，已显示的内容保留，请再查一次本轮状态。';
    pending(notice);
  }
  async function accept(event: RunEventV1, signal: AbortSignal) {
    current();
    signal.throwIfAborted();
    if (event.type === 'started' && event.thread_id !== accepted.thread_id) throw new ThreadRequestError('receipt');
    if (event.type === 'final' || event.type === 'error') {
      const checked = await read();
      current();
      signal.throwIfAborted();
      if (!checked.fresh || activeRun(checked.state)) {
        if (checked.fresh) {
          publish(authoritativeProjection(view, checked.state));
          pending('本轮执行仍在核对，暂不把旧终态当作当前结果。');
        }
        throw new ThreadRequestError('receipt');
      }
      if (
        event.type === 'final' &&
        (checked.state.status !== 'succeeded' ||
          !checked.state.final ||
          !sameFinal(event.envelope, checked.state.final))
      ) {
        publish({
          ...view,
          server: checked.state,
          stream: {
            ...view.stream,
            receipts: [],
            question: undefined,
            decisions: [],
            optionsId: undefined,
            optionsPrompt: undefined,
          },
        });
        pending('事件与已提交结果尚未对上，已显示的内容保留。');
        throw new ThreadRequestError('receipt');
      }
      // Adoption here is terminal; don't abort this consumer before its cursor commits.
      publish(authoritativeProjection(view, checked.state));
      return;
    }
    const projected = chatEvent(event, event.type);
    if (!projected) throw new ThreadRequestError('receipt');
    publish({ ...view, stream: reduceChat(view.stream, projected) });
  }
  async function run() {
    try {
      current();
      publish({ ...view, phase: 'checking', notice: '正在核对本轮状态…' });
      const initial = await read();
      if (!initial.fresh) return;
      adopt(initial.state, initial.ticket);
      if (!activeRun(initial.state)) return;
      if (initial.state.attempts > 1) {
        pending('本轮执行已切换，缺少恢复起点，请先核对状态。');
        return;
      }
      followAbort = new AbortController();
      const abort = () => followAbort?.abort();
      lifetime.signal.addEventListener('abort', abort, { once: true });
      publish({ ...view, phase: 'following', notice: '' });
      try {
        const result = await followThreadEvents(accepted, {
          ...owner,
          ...options,
          signal: followAbort.signal,
          isCurrent: owned,
          accept,
        });
        current();
        publish({ ...view, ...(result.lastEventId ? { lastEventId: result.lastEventId } : {}) });
        if (['complete', 'interrupted', 'ended'].includes(view.phase)) return;
        if (result.reason === 'needs_state') {
          const checked = await read();
          if (checked.fresh) {
            adopt(checked.state, checked.ticket);
            if (activeRun(checked.state)) pending('连接游标已不可用，已显示的内容保留；请核对本轮状态。');
          }
        } else if (result.reason !== 'aborted')
          failure(
            new ThreadRequestError(
              'http',
              result.code === 'unauthorized' ? 401 : result.code === 'forbidden' ? 403 : undefined,
            ),
          );
      } finally {
        lifetime.signal.removeEventListener('abort', abort);
      }
    } catch (error) {
      failure(error);
    }
  }
  function start() {
    return (startTask ??= Promise.resolve().then(run));
  }
  function refresh() {
    if (refreshTask) return refreshTask;
    refreshTask = Promise.resolve().then(async () => {
      try {
        current();
        const checked = await read();
        if (checked.fresh) {
          adopt(checked.state, checked.ticket);
          if (activeRun(checked.state) && view.phase !== 'following')
            pending('本轮仍在运行，请稍后再核对；不会重新发送问题。');
        }
      } catch (error) {
        failure(error);
      } finally {
        refreshTask = undefined;
      }
    });
    return refreshTask;
  }
  function stop() {
    if (stopTask) return stopTask;
    if (['complete', 'interrupted', 'ended'].includes(view.phase)) return Promise.resolve();
    stopTask = Promise.resolve().then(async () => {
      try {
        current();
        const ticket = ++version;
        publish({ ...view, stopping: true, notice: '正在请求停止，已出的内容保留。' });
        const result = await authority.stop(accepted, owner);
        current();
        if (adopt(result.state, ticket) && activeRun(result.state))
          publish({ ...view, stopping: true, notice: '停止请求已收到，仍在等待实际停止。' });
      } catch {
        if (owned() && !['complete', 'interrupted', 'ended'].includes(view.phase))
          publish({ ...view, stopping: false, notice: '停止尚未确认，已出的内容保留；可再核对本轮状态。' });
      } finally {
        stopTask = undefined;
      }
    });
    return stopTask;
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    lifetime.abort();
    followAbort?.abort();
    version++;
    view = empty;
    for (const listener of listeners) {
      try {
        listener();
      } catch {
        /* Clearing a detached view has no payload. */
      }
    }
    listeners.clear();
    options.signal.removeEventListener('abort', dispose);
  }
  options.signal.addEventListener('abort', dispose, { once: true });
  if (options.signal.aborted) dispose();
  return {
    start,
    refresh,
    stop,
    dispose,
    getSnapshot: () => (owned() ? view : empty),
    subscribe(listener: () => void) {
      if (owned()) listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
