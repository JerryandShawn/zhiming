import { abortable, cancelUnusedResponse } from '../chat/followV1Async';
import { assertOwner, readJson, type RequestOwner } from '../threads/request';

// mod api_modules_common_draft 0.1.0 @ daccd26c (v4/mod-api-contracts). Draft, not frozen:
// every port built on this stays behind an explicit opt-in until main publishes the routes.
export const DRAFT_CONTRACT = 'daccd26c';
export const errorCodes = [
  'UNAUTHORIZED',
  'FORBIDDEN',
  'SCOPE_NOT_FOUND',
  'VALIDATION_ERROR',
  'REVISION_CONFLICT',
  'IDEMPOTENCY_CONFLICT',
  'CONSENT_REQUIRED',
  'SOURCE_REVOKED',
  'REVIEW_REQUIRED',
  'REVIEW_EXPIRED',
  'REVIEW_PLAN_CHANGED',
  'QUALITY_GATE_CLOSED',
  'UNKNOWN_RESULT',
  'RATE_LIMITED',
  'DRAFT_NOT_IMPLEMENTED',
] as const;
export type DraftErrorCode = (typeof errorCodes)[number] | 'NETWORK' | 'BAD_RESPONSE' | 'OBSOLETE';
export const writeStatuses = [
  'saved',
  'updated',
  'deleted',
  'undone',
  'skipped',
  'pending_confirmation',
  'queued',
] as const;

// Fixed copy only: server messages may quote private text and are never rendered.
const copy: Record<DraftErrorCode, string> = {
  UNAUTHORIZED: '请重新登录，你的修改还在。',
  FORBIDDEN: '这次操作没有权限，请核对登录。',
  SCOPE_NOT_FOUND: '没有找到这条内容，请刷新核对。',
  VALIDATION_ERROR: '内容没有通过核对，请检查填写的信息。',
  REVISION_CONFLICT: '内容已在别处更新，刷新后核对。你的修改还在。',
  IDEMPOTENCY_CONFLICT: '这次请求与之前的同号请求不一致，请刷新后重新核对。',
  CONSENT_REQUIRED: '这一区需要你先确认用途授权。',
  SOURCE_REVOKED: '采用的来源已撤销，这一项不能继续使用。',
  REVIEW_REQUIRED: '这一步需要先审阅确认。',
  REVIEW_EXPIRED: '审阅已过期，请重新审阅。',
  REVIEW_PLAN_CHANGED: '整理计划已变化，请重新审阅。',
  QUALITY_GATE_CLOSED: '这项整理尚未开放自动应用。',
  UNKNOWN_RESULT: '还没有确认是否已保存，请用原请求再核对一次，不要重复提交新的。',
  RATE_LIMITED: '请求太频繁，请稍后用原请求再试。',
  DRAFT_NOT_IMPLEMENTED: '服务端尚未开放这项功能，你的修改还在。',
  NETWORK: '网络没有连上。你的修改还在，请用原请求再试一次。',
  BAD_RESPONSE: '没有收到可核对的回执，你的修改还在，请用原请求再核对。',
  OBSOLETE: '登录或页面已经切换，本次结果不会显示。',
};
export class DraftApiError extends Error {
  constructor(
    public code: DraftErrorCode,
    public status?: number,
    public retryable = false,
    public currentRevision?: number,
  ) {
    super(copy[code]);
    this.name = 'DraftApiError';
  }
  /** Same request_id and payload may be resent; a new business operation is never implied. */
  get resendSame() {
    return ['UNKNOWN_RESULT', 'RATE_LIMITED', 'NETWORK', 'BAD_RESPONSE'].includes(this.code);
  }
}

export const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
const ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]*$/;
export const isId = (value: unknown): value is string =>
  typeof value === 'string' && value.length >= 1 && value.length <= 128 && ID.test(value);
export const isRevision = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 1;
export const isText = (value: unknown, min: number, max: number): value is string =>
  typeof value === 'string' && Array.from(value).length >= min && Array.from(value).length <= max;
const OFFSET = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
export const isInstant = (value: unknown): value is string =>
  typeof value === 'string' && OFFSET.test(value) && !Number.isNaN(Date.parse(value));
export function exactKeys(
  value: Record<string, unknown>,
  required: readonly string[],
  optional: readonly string[] = [],
) {
  const allowed = new Set([...required, ...optional]);
  return required.every((key) => Object.hasOwn(value, key)) && Object.keys(value).every((key) => allowed.has(key));
}

export type SourceRef = Readonly<{ message_id: string; revision: number; start: number; end: number }>;
export function sourceRef(value: unknown): SourceRef {
  const item = record(value);
  if (
    !exactKeys(item, ['message_id', 'revision', 'start', 'end']) ||
    !isId(item.message_id) ||
    !isRevision(item.revision) ||
    !Number.isSafeInteger(item.start) ||
    !Number.isSafeInteger(item.end) ||
    (item.start as number) < 0 ||
    (item.end as number) <= (item.start as number)
  )
    throw new DraftApiError('BAD_RESPONSE');
  return Object.freeze({
    message_id: item.message_id,
    revision: item.revision,
    start: item.start as number,
    end: item.end as number,
  });
}

export type Receipt = Readonly<{
  operation_id: string;
  write_status: (typeof writeStatuses)[number];
  entity_id: string;
  revision: number;
}>;
export type WriteIdentity = Readonly<{ request_id: string; expected_revision: number }>;
/** One business operation: the id and serialized payload are fixed for every resend. */
export function writeIntent<T extends object>(expectedRevision: number, payload: T, id = newRequestId()) {
  if (!isId(id) || !Number.isSafeInteger(expectedRevision) || expectedRevision < 0)
    throw new DraftApiError('VALIDATION_ERROR');
  return Object.freeze({ ...payload, request_id: id, expected_revision: expectedRevision }) as Readonly<
    T & WriteIdentity
  >;
}
export const newRequestId = () => `web:${crypto.randomUUID()}`;

export function writeResult(value: unknown, requestId: string): Receipt {
  const result = record(value),
    receipt = record(result.receipt);
  if (
    !exactKeys(result, ['ok', 'request_id', 'receipt']) ||
    result.ok !== true ||
    result.request_id !== requestId ||
    !exactKeys(receipt, ['operation_id', 'write_status', 'entity_id', 'revision']) ||
    !isId(receipt.operation_id) ||
    !isId(receipt.entity_id) ||
    !isRevision(receipt.revision) ||
    !writeStatuses.includes(receipt.write_status as Receipt['write_status'])
  )
    throw new DraftApiError('BAD_RESPONSE');
  return Object.freeze({
    operation_id: receipt.operation_id,
    write_status: receipt.write_status as Receipt['write_status'],
    entity_id: receipt.entity_id,
    revision: receipt.revision,
  });
}
/** Only program receipts count as saved; queued/pending stay visibly unconfirmed. */
export const receiptSaved = (receipt: Receipt) =>
  ['saved', 'updated', 'deleted', 'undone', 'skipped'].includes(receipt.write_status);

function draftError(value: unknown, status: number, requestId?: string): DraftApiError {
  const body = record(value),
    error = record(body.error);
  const code = errorCodes.find((item) => item === error.code);
  if (
    !code ||
    body.ok !== false ||
    !exactKeys(body, ['ok', 'error'], ['request_id']) ||
    !exactKeys(error, ['code', 'message', 'retryable'], ['current_revision']) ||
    typeof error.retryable !== 'boolean' ||
    !isText(error.message, 1, 300) ||
    (error.current_revision !== undefined && !isRevision(error.current_revision)) ||
    (requestId !== undefined && body.request_id !== undefined && body.request_id !== requestId)
  )
    return new DraftApiError(status === 401 ? 'UNAUTHORIZED' : status === 403 ? 'FORBIDDEN' : 'BAD_RESPONSE', status);
  return new DraftApiError(code, status, error.retryable, error.current_revision as number | undefined);
}

type Request = {
  method: 'GET' | 'POST' | 'PATCH';
  path: string;
  query?: Record<string, string | number | boolean | undefined>;
  body?: WriteIdentity;
  maxBytes?: number;
};
/** Same-origin /api/ only, no redirects, no automatic retries, owner rechecked around every await. */
export async function draftRequest(fetcher: typeof fetch, request: Request, owner: RequestOwner): Promise<unknown> {
  assertOwner(owner);
  const endpoint = new URL(request.path, 'https://request.invalid');
  if (
    !request.path.startsWith('/api/') ||
    endpoint.origin !== 'https://request.invalid' ||
    endpoint.pathname !== request.path ||
    endpoint.search ||
    endpoint.hash
  )
    throw new DraftApiError('VALIDATION_ERROR');
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(request.query ?? {}))
    if (value !== undefined) query.set(key, String(value));
  const path = query.size ? `${request.path}?${query}` : request.path;
  const headers = new Headers(owner.headers());
  headers.set('Accept', 'application/json');
  if (request.body) headers.set('Content-Type', 'application/json');
  const controller = new AbortController();
  const abort = () => controller.abort();
  owner.signal.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(abort, 45000);
  let response: Response | undefined;
  try {
    response = await abortable(
      fetcher(path, {
        method: request.method,
        headers,
        ...(request.body ? { body: JSON.stringify(request.body) } : {}),
        signal: controller.signal,
        credentials: 'same-origin',
        cache: 'no-store',
        redirect: 'error',
      }),
      controller.signal,
      cancelUnusedResponse,
    );
    assertOwner(owner);
    if (!/^application\/json(?:\s*;|$)/i.test(response.headers.get('Content-Type') ?? '')) {
      if (response.ok) throw new DraftApiError('BAD_RESPONSE', response.status);
      throw draftError(undefined, response.status);
    }
    const value = await readJson(response, { ...owner, signal: controller.signal }, request.maxBytes ?? 256 * 1024);
    assertOwner(owner);
    const ok = request.method === 'GET' ? response.status === 200 : [200, 201, 202].includes(response.status);
    if (!ok) throw draftError(value, response.status, request.body?.request_id);
    return value;
  } catch (error) {
    if (owner.signal.aborted || !owner.isCurrent()) throw new DraftApiError('OBSOLETE');
    if (error instanceof DraftApiError) throw error;
    // Timeout or a broken body after the request left: the outcome of a write is unknown.
    throw new DraftApiError(response ? 'BAD_RESPONSE' : 'NETWORK', response?.status);
  } finally {
    clearTimeout(timer);
    owner.signal.removeEventListener('abort', abort);
    if (response) cancelUnusedResponse(response);
  }
}
