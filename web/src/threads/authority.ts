import { identifier, integer, keys, record } from '../chat/wireChecksV1';
import { isWireEnvelopeV1, type WireEnvelopeV1 } from '../chat/wireV1';
import { runStates, threadAcceptance, ThreadRequestError, type ThreadAcceptance } from './contracts';
import { assertOwner, ownedJson, type RequestOwner } from './request';

export type ThreadRunState = Readonly<{
  runId: string;
  status: ThreadAcceptance['status'];
  attempts: number;
  final?: WireEnvelopeV1;
}>;

/** Drop checkpoint/dependencies/error and every non-succeeded result, including old partials. */
export function runState(value: unknown, runId: string): ThreadRunState {
  const invalid = () => {
    throw new ThreadRequestError('receipt');
  };
  if (
    !identifier(runId) ||
    !record(value) ||
    !keys(value, [
      'id',
      'operation_id',
      'status',
      'calls',
      'call_limit',
      'attempts',
      'checkpoint',
      'dependencies',
      'error',
      'result',
    ]) ||
    value.id !== runId ||
    !identifier(value.operation_id) ||
    !runStates.some((status) => status === value.status) ||
    !integer(value.attempts, 0) ||
    !integer(value.calls, 0) ||
    !integer(value.call_limit, 0) ||
    value.calls > value.call_limit
  )
    return invalid();
  const state = { runId, status: value.status as ThreadAcceptance['status'], attempts: value.attempts };
  if (value.status !== 'succeeded') return Object.freeze(state);
  if (!isWireEnvelopeV1(value.result)) return invalid();
  const binding = value.result.meta?.core_run;
  if (binding && (binding.run_id !== runId || binding.operation_id !== value.operation_id)) return invalid();
  return Object.freeze({ ...state, final: value.result });
}

/** Read and cancel only the same verified v4 run; cancellation ack is never a stopped state. */
export function threadAuthorityPort(fetcher: typeof fetch) {
  const checked = (receipt: ThreadAcceptance, owner: RequestOwner) => {
    assertOwner(owner);
    const accepted = threadAcceptance(receipt);
    if (accepted.runtime !== 'v4') throw new ThreadRequestError('input');
    return accepted;
  };
  async function read(receipt: ThreadAcceptance, owner: RequestOwner): Promise<ThreadRunState> {
    const accepted = checked(receipt, owner);
    const value = await ownedJson(fetcher, accepted.run_url, { method: 'GET', status: 200, maxBytes: 2097152 }, owner);
    const state = runState(value, accepted.run_id);
    assertOwner(owner);
    return state;
  }
  async function stop(receipt: ThreadAcceptance, owner: RequestOwner) {
    const accepted = checked(receipt, owner);
    const ack = await ownedJson(
      fetcher,
      `${accepted.run_url}/cancel`,
      { method: 'POST', status: 200, maxBytes: 8192 },
      owner,
    );
    if (!record(ack) || !keys(ack, ['ok', 'run_id']) || ack.ok !== true || ack.run_id !== accepted.run_id)
      throw new ThreadRequestError('receipt');
    assertOwner(owner);
    const state = await read(accepted, owner);
    assertOwner(owner);
    return { acknowledged: true as const, stopped: state.status === 'cancelled', state };
  }
  return { read, stop };
}
