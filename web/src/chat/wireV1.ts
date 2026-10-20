import type { JsonObject, StatusPhase } from './types';

export type WireCommonV1 = { v: 1; run_id: string; seq: number; ts: string };
export type WireQuestionV1 = {
  ask_id: string;
  question: string;
  options: { id: string; label: string }[];
  allow_free_text: boolean;
  multi: boolean;
  why: string;
};
export type WireDecisionV1 = {
  id: string;
  title: string;
  benefit: string;
  cost: string;
  risk: string;
  reversibility: 'easy' | 'partial' | 'hard' | 'unknown';
  first_step: string;
  unknowns: string[];
};
export type WireOptionsV1 = { options_id: string; prompt?: string; options: WireDecisionV1[] };
export type WireReviewV1 = {
  state: 'pending' | 'passed' | 'revised' | 'skipped';
  reasons: { code: string; severity: 1 | 2 | 3 | 4 | 5 }[];
  revision_id?: string;
};
export type WireMemoryReceiptV1 = {
  fact_id?: string;
  proposal_id?: string;
  write_status: 'saved' | 'pending_confirm' | 'undone' | 'rejected';
  summary: string;
  undo_token?: string;
  sensitive: boolean;
};
export type WireEnvelopeV1 = {
  schema: 'core4.0';
  message_id: string;
  text: string;
  receipts: JsonObject[];
  used_fact_ids: string[];
  used_claim_ids: string[];
  asked: WireQuestionV1 | null;
  options: WireOptionsV1 | null;
  review: WireReviewV1;
  usage: JsonObject;
};
type Bodies = {
  started: { thread_id: string; message_id: string; area_id?: string; topic_id?: string; incognito: boolean };
  status: { text: string; phase: StatusPhase };
  tool_call: { call_id: string; name: string; summary: string };
  tool_result: { call_id: string; name: string; ok: boolean; summary: string; receipt?: JsonObject };
  text_delta: { text: string };
  text_reset: { text: string; reason: 'revised' | 'resumed'; revision_id?: string };
  memory_receipt: WireMemoryReceiptV1;
  ask_user: WireQuestionV1;
  present_options: WireOptionsV1;
  review: WireReviewV1;
  final: { message_id: string; envelope: WireEnvelopeV1 };
  error: { code: string; message: string; retryable: boolean };
};
export type WireEventV1 = { [K in keyof Bodies]: WireCommonV1 & { type: K } & Bodies[K] }[keyof Bodies];

const record = (value: unknown): value is JsonObject =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === 'string';
const identifier = (value: unknown): value is string => text(value) && Boolean(value.trim()) && !/[\r\n]/.test(value);
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(text);
const oneOf = (value: unknown, allowed: readonly string[]) => text(value) && allowed.includes(value);
const optionalId = (data: JsonObject, key: string) => !Object.hasOwn(data, key) || identifier(data[key]);
function keys(data: JsonObject, required: string[], optional: string[] = []) {
  return (
    required.every((key) => Object.hasOwn(data, key)) &&
    Object.keys(data).every((key) => required.includes(key) || optional.includes(key))
  );
}
function uniqueIds(value: { id: string }[]) {
  return new Set(value.map((item) => item.id)).size === value.length;
}

/** Validate the calendar explicitly so the host time zone cannot affect wire acceptance. */
export function isWireTimestampV1(value: unknown): value is string {
  if (!text(value)) return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})T([01]\d|2[0-3]):([0-5]\d):([0-5]\d)(?:\.\d{1,9})?\+08:00$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]),
    month = Number(match[2]),
    day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1) return false;
  const lastDay = new Date(0);
  lastDay.setUTCFullYear(year, month, 0);
  return day <= lastDay.getUTCDate();
}

export function isWireQuestionV1(value: unknown): value is WireQuestionV1 {
  if (!record(value) || !keys(value, ['ask_id', 'question', 'options', 'allow_free_text', 'multi', 'why']))
    return false;
  if (!identifier(value.ask_id) || !identifier(value.question) || !Array.isArray(value.options)) return false;
  const valid = value.options.every(
    (item: unknown) => record(item) && keys(item, ['id', 'label']) && identifier(item.id) && identifier(item.label),
  );
  return (
    valid &&
    uniqueIds(value.options as { id: string }[]) &&
    typeof value.allow_free_text === 'boolean' &&
    typeof value.multi === 'boolean' &&
    text(value.why)
  );
}

export function isWireOptionsV1(value: unknown): value is WireOptionsV1 {
  if (!record(value) || !keys(value, ['options_id', 'options'], ['prompt'])) return false;
  if (!identifier(value.options_id) || (Object.hasOwn(value, 'prompt') && !text(value.prompt))) return false;
  if (!Array.isArray(value.options) || value.options.length < 2 || value.options.length > 4) return false;
  const valid = value.options.every(
    (item: unknown) =>
      record(item) &&
      keys(item, ['id', 'title', 'benefit', 'cost', 'risk', 'reversibility', 'first_step', 'unknowns']) &&
      identifier(item.id) &&
      identifier(item.title) &&
      text(item.benefit) &&
      text(item.cost) &&
      text(item.risk) &&
      oneOf(item.reversibility, ['easy', 'partial', 'hard', 'unknown']) &&
      text(item.first_step) &&
      strings(item.unknowns),
  );
  return valid && uniqueIds(value.options as { id: string }[]);
}

export function isWireReviewV1(value: unknown): value is WireReviewV1 {
  return (
    record(value) &&
    keys(value, ['state', 'reasons'], ['revision_id']) &&
    oneOf(value.state, ['pending', 'passed', 'revised', 'skipped']) &&
    optionalId(value, 'revision_id') &&
    Array.isArray(value.reasons) &&
    value.reasons.every(
      (reason: unknown) =>
        record(reason) &&
        keys(reason, ['code', 'severity']) &&
        identifier(reason.code) &&
        Number.isInteger(reason.severity) &&
        Number(reason.severity) >= 1 &&
        Number(reason.severity) <= 5,
    )
  );
}

export function isWireMemoryReceiptV1(value: unknown): value is WireMemoryReceiptV1 {
  return (
    record(value) &&
    keys(value, ['write_status', 'summary', 'sensitive'], ['fact_id', 'proposal_id', 'undo_token']) &&
    (identifier(value.fact_id) || identifier(value.proposal_id)) &&
    optionalId(value, 'fact_id') &&
    optionalId(value, 'proposal_id') &&
    optionalId(value, 'undo_token') &&
    text(value.summary) &&
    typeof value.sensitive === 'boolean' &&
    oneOf(value.write_status, ['saved', 'pending_confirm', 'undone', 'rejected'])
  );
}

export function isWireEnvelopeV1(value: unknown): value is WireEnvelopeV1 {
  return (
    record(value) &&
    keys(value, [
      'schema',
      'message_id',
      'text',
      'receipts',
      'used_fact_ids',
      'used_claim_ids',
      'asked',
      'options',
      'review',
      'usage',
    ]) &&
    value.schema === 'core4.0' &&
    identifier(value.message_id) &&
    text(value.text) &&
    Array.isArray(value.receipts) &&
    value.receipts.every(record) &&
    strings(value.used_fact_ids) &&
    strings(value.used_claim_ids) &&
    (value.asked === null || isWireQuestionV1(value.asked)) &&
    (value.options === null || isWireOptionsV1(value.options)) &&
    isWireReviewV1(value.review) &&
    record(value.usage)
  );
}

const bodyValidators: Record<keyof Bodies, (data: JsonObject) => boolean> = {
  started: (d) =>
    keys(d, ['thread_id', 'message_id', 'incognito'], ['area_id', 'topic_id']) &&
    identifier(d.thread_id) &&
    identifier(d.message_id) &&
    typeof d.incognito === 'boolean' &&
    optionalId(d, 'area_id') &&
    optionalId(d, 'topic_id'),
  status: (d) =>
    keys(d, ['text', 'phase']) && text(d.text) && oneOf(d.phase, ['thinking', 'tool', 'writing', 'reviewing']),
  tool_call: (d) =>
    keys(d, ['call_id', 'name', 'summary']) && identifier(d.call_id) && identifier(d.name) && text(d.summary),
  tool_result: (d) =>
    keys(d, ['call_id', 'name', 'ok', 'summary'], ['receipt']) &&
    identifier(d.call_id) &&
    identifier(d.name) &&
    typeof d.ok === 'boolean' &&
    text(d.summary) &&
    (!Object.hasOwn(d, 'receipt') || record(d.receipt)),
  text_delta: (d) => keys(d, ['text']) && text(d.text),
  text_reset: (d) =>
    keys(d, ['text', 'reason'], ['revision_id']) &&
    text(d.text) &&
    oneOf(d.reason, ['revised', 'resumed']) &&
    optionalId(d, 'revision_id'),
  memory_receipt: isWireMemoryReceiptV1,
  ask_user: isWireQuestionV1,
  present_options: isWireOptionsV1,
  review: isWireReviewV1,
  final: (d) =>
    keys(d, ['message_id', 'envelope']) &&
    identifier(d.message_id) &&
    isWireEnvelopeV1(d.envelope) &&
    d.envelope.message_id === d.message_id,
  error: (d) =>
    keys(d, ['code', 'message', 'retryable']) &&
    identifier(d.code) &&
    text(d.message) &&
    typeof d.retryable === 'boolean',
};

/** Explicit v1 input never falls back to legacy projection when malformed. */
export function parseWireEventV1(value: unknown, namedType = ''): WireEventV1 | undefined {
  if (
    !record(value) ||
    !['v', 'run_id', 'seq', 'ts'].every((key) => Object.hasOwn(value, key)) ||
    value.v !== 1 ||
    !identifier(value.run_id) ||
    !Number.isSafeInteger(value.seq) ||
    Number(value.seq) < 0 ||
    !isWireTimestampV1(value.ts)
  )
    return;
  const type = text(value.type) ? value.type : namedType;
  if ((namedType && type !== namedType) || !Object.hasOwn(bodyValidators, type)) return;
  const body = Object.fromEntries(
    Object.entries(value).filter(([key]) => !['v', 'run_id', 'seq', 'ts', 'type'].includes(key)),
  );
  if (!bodyValidators[type as keyof Bodies](body)) return;
  return { ...body, type, v: 1, run_id: value.run_id, seq: value.seq, ts: value.ts } as WireEventV1;
}
