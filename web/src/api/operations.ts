import { ApiError, json, operationNamespace } from './client';

type Pending = { id: string; fingerprint: string; payload: Record<string, unknown> };
const fallback = new Map<string, Pending>();
const key = (scope: string) => `mingjing-write:${operationNamespace()}:${scope}`;
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object')
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([name, item]) => `${JSON.stringify(name)}:${canonical(item)}`)
      .join(',')}}`;
  return JSON.stringify(value) ?? 'null';
}
function readAt(storageKey: string): Pending | undefined {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (raw) {
      const value = JSON.parse(raw) as Partial<Pending> | null;
      if (
        value &&
        typeof value.id === 'string' &&
        typeof value.fingerprint === 'string' &&
        value.payload &&
        typeof value.payload === 'object'
      )
        return value as Pending;
    }
  } catch {
    /* Fall back to this tab's memory. */
  }
  return fallback.get(storageKey);
}
export function pendingPayload<T>(scope: string): T | undefined {
  return readAt(key(scope))?.payload as T | undefined;
}
function forgetAt(storageKey: string, expectedId?: string) {
  if (expectedId && readAt(storageKey)?.id !== expectedId) return;
  fallback.delete(storageKey);
  try {
    sessionStorage.removeItem(storageKey);
  } catch {
    /* Storage can be unavailable. */
  }
}
export function discardOperation(scope: string) {
  forgetAt(key(scope));
}
export async function write<T>(
  scope: string,
  method: string,
  path: string,
  payload: Record<string, unknown>,
  options: { idKey?: 'request_id' | 'idempotency_key'; receipt?: (value: T) => boolean } = {},
): Promise<T> {
  const fingerprint = canonical({ method, path, payload });
  const storageKey = key(scope);
  const existing = readAt(storageKey);
  if (existing && existing.fingerprint !== fingerprint)
    throw new ApiError(0, '上次提交还没有收到确认，请先用原内容重试。');
  const pending = existing ?? { id: crypto.randomUUID(), fingerprint, payload };
  try {
    sessionStorage.setItem(storageKey, JSON.stringify(pending));
  } catch {
    throw new ApiError(0, '当前浏览会话无法保存重试标识，本次没有发送。请释放浏览器存储空间后再试。');
  }
  fallback.set(storageKey, pending);
  try {
    const value = await json<T>(method, path, {
      ...payload,
      request_id: pending.id,
      ...(options.idKey === 'idempotency_key' ? { idempotency_key: pending.id } : {}),
    });
    if (options.receipt && !options.receipt(value)) throw new ApiError(502, '没有收到有效保存回执，请用原内容重试。');
    forgetAt(storageKey, pending.id);
    return value;
  } catch (error) {
    if (
      error instanceof ApiError &&
      error.status >= 400 &&
      error.status < 500 &&
      ![401, 408, 429].includes(error.status)
    )
      forgetAt(storageKey, pending.id);
    throw error;
  }
}
