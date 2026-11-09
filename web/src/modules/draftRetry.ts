import { operationNamespace } from '../api/client';
import { DraftApiError, isId, writeIntent, type WriteIdentity } from './draftApi';

type Pending = { id: string; fingerprint: string };
const volatile = new Map<string, Pending>();
const storageKey = (scope: string) => `mingjing-draft-write:${operationNamespace()}:${scope}`;

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object')
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(',')}}`;
  return JSON.stringify(value) ?? 'null';
}

function read(key: string, durable: boolean): Pending | undefined {
  if (!durable) return volatile.get(key);
  let raw: string | null;
  try {
    raw = sessionStorage.getItem(key);
  } catch {
    throw new DraftApiError('UNKNOWN_RESULT');
  }
  if (!raw) return undefined;
  try {
    const value = JSON.parse(raw) as Partial<Pending> | null;
    if (value && isId(value.id) && typeof value.fingerprint === 'string') return value as Pending;
  } catch {
    return undefined;
  }
  return undefined;
}

export function draftRetryIntent<T extends object>(
  scope: string,
  expectedRevision: number,
  payload: T,
  durable = true,
): Readonly<T & WriteIdentity> {
  const key = storageKey(scope);
  const fingerprint = canonical({ expectedRevision, payload });
  const prior = read(key, durable);
  if (prior && prior.fingerprint !== fingerprint) throw new DraftApiError('UNKNOWN_RESULT');
  const pending = prior ?? { id: `web:${crypto.randomUUID()}`, fingerprint };
  if (durable) {
    try {
      sessionStorage.setItem(key, JSON.stringify(pending));
    } catch {
      throw new DraftApiError('UNKNOWN_RESULT');
    }
  } else volatile.set(key, pending);
  return writeIntent(expectedRevision, payload, pending.id);
}

export function clearDraftRetry(scope: string, requestId: string, durable = true) {
  const key = storageKey(scope);
  if (read(key, durable)?.id !== requestId) return;
  volatile.delete(key);
  if (!durable) return;
  try {
    sessionStorage.removeItem(key);
  } catch {
    /* A later identical request remains safe if storage cannot be cleared. */
  }
}
