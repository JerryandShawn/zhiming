import {
  OrganizeError,
  type Collection,
  type FieldKey,
  type FieldValue,
  type Json,
  type OrganizeDocument,
} from './types';

export const LABEL_FIELDS = new Set(['space_id', 'topic_id', 'space_secondary', 'route_source', 'route_confidence']);
export const TOPIC_FIELDS = new Set(['title', 'space_id', 'status', 'message_ids']);
const forbidden = new Set(['__proto__', 'prototype', 'constructor']);
export function identity(value: unknown): asserts value is string {
  if (typeof value !== 'string' || !value.trim() || value.length > 160 || forbidden.has(value))
    throw new OrganizeError('INVALID', '整理标识无效，请刷新合成示例。');
}
export function canonical(value: unknown): string {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype)
    return `{${Object.entries(value)
      .filter(([, child]) => child !== undefined)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([key, child]) => `${JSON.stringify(key)}:${canonical(child)}`)
      .join(',')}}`;
  throw new OrganizeError('INVALID', '整理数据不是有效的有限JSON值。');
}
export function same(left: unknown, right: unknown) {
  return canonical(left) === canonical(right);
}
export function freeze<T>(value: T): T {
  if (value && typeof value === 'object') {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
  return value;
}
export function active(record: object) {
  const row = record as Record<string, unknown>;
  if (
    [row.status, row.source_status].some((value) => value !== undefined && value !== null && typeof value !== 'string')
  )
    throw new OrganizeError('INVALID', '整理来源状态无效。');
  if (
    row.incognito === true ||
    String(row.thread_id ?? '').startsWith('incognito:') ||
    (row.retention_scope !== undefined && row.retention_scope !== 'persistent')
  )
    throw new OrganizeError('SOURCE_CHANGED', '无痕或临时来源不能应用到长期整理。');
  if (
    [row.status, row.source_status].some((value) => ['deleted', 'revoked', 'withdrawn'].includes(String(value))) ||
    row.deleted_at != null ||
    row.revoked_at != null
  )
    throw new OrganizeError('SOURCE_CHANGED', '整理来源已停止使用，请重新核对。');
}
function ownRecord(value: unknown): asserts value is Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.getPrototypeOf(value) !== Object.prototype)
    throw new OrganizeError('INVALID', '整理快照格式无效。');
}
export function validateDocument(document: OrganizeDocument, owner: string, subject: string) {
  ownRecord(document);
  if (document.owner_id !== owner || document.subject_id !== subject)
    throw new OrganizeError('SCOPE', '整理归属不匹配，未修改任何数据。');
  for (const collection of ['messages', 'topics'] as const) {
    ownRecord(document[collection]);
    for (const [id, row] of Object.entries(document[collection])) {
      identity(id);
      ownRecord(row);
      if (row.id !== id || row.owner_id !== owner || row.subject_id !== subject)
        throw new OrganizeError('SCOPE', '整理记录归属或标识不匹配。');
      if (typeof row.status !== 'string') throw new OrganizeError('INVALID', '整理来源状态无效。');
    }
  }
  for (const row of Object.values(document.messages)) {
    if (
      typeof row.content !== 'string' ||
      !['user', 'assistant'].includes(row.role) ||
      !Number.isSafeInteger(row.at_ms) ||
      !Number.isSafeInteger(row.revision) ||
      row.revision < 1
    )
      throw new OrganizeError('INVALID', '原始消息格式无效。');
    if (row.topic_id != null && row.topic_id !== '') {
      identity(row.topic_id);
      const topic = Object.hasOwn(document.topics, row.topic_id) ? document.topics[row.topic_id] : undefined;
      if (!topic || (Object.hasOwn(row, 'space_id') && row.space_id !== topic.space_id))
        throw new OrganizeError('INVALID_SELECTION', '归区与话题必须一起核对，不能留下不一致标签。');
    }
  }
  for (const row of Object.values(document.topics)) {
    if (
      typeof row.title !== 'string' ||
      typeof row.space_id !== 'string' ||
      !Array.isArray(row.message_ids) ||
      row.message_ids.some((id) => typeof id !== 'string' || !Object.hasOwn(document.messages, id)) ||
      new Set(row.message_ids).size !== row.message_ids.length
    )
      throw new OrganizeError('INVALID', '话题目录不完整或引用重复。');
  }
  canonical(document);
}
export function fieldId(key: FieldKey): string {
  return canonical([key.collection, key.entity_id, key.field]);
}
export function readField(document: OrganizeDocument, key: FieldKey): FieldValue {
  const collection = document[key.collection];
  if (key.field === null)
    return Object.hasOwn(collection, key.entity_id)
      ? { present: true, value: structuredClone(collection[key.entity_id]) as unknown as Json }
      : { present: false };
  if (!Object.hasOwn(collection, key.entity_id)) throw new OrganizeError('SOURCE_CHANGED', '整理目标已不存在。');
  const row = collection[key.entity_id] as unknown as Record<string, Json>;
  return Object.hasOwn(row, key.field) ? { present: true, value: structuredClone(row[key.field]) } : { present: false };
}
export function writeField(document: OrganizeDocument, key: FieldKey, value: FieldValue) {
  const collection = document[key.collection] as unknown as Record<string, Record<string, Json>>;
  const target = key.field === null ? collection : collection[key.entity_id];
  const property = key.field ?? key.entity_id;
  if (value.present)
    Object.defineProperty(target, property, {
      value: structuredClone(value.value),
      writable: true,
      configurable: true,
      enumerable: true,
    });
  else delete target[property];
}
export function immutableRecord(document: OrganizeDocument, collection: Collection, id: string) {
  const row = document[collection][id];
  if (!row) throw new OrganizeError('SOURCE_CHANGED', '整理来源已不存在。');
  const labels = collection === 'messages' ? LABEL_FIELDS : TOPIC_FIELDS;
  return Object.fromEntries(Object.entries(row).filter(([key]) => !labels.has(key)));
}
export async function sha256(text: string): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new OrganizeError('UNAVAILABLE', '当前环境不支持本地来源核对。');
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, '0')).join('');
}
