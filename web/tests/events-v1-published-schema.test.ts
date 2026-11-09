import Ajv from 'ajv';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import published from './fixtures/events_v1.schema.json';
import provenance from './fixtures/provenance.json';
import { parseWireEventV1 } from '../src/chat/wireV1';
import { chatEvent, normalizeEnvelope } from '../src/chat/events';
import { reduceChat } from '../src/chat/reducer';
import { initialStream } from '../src/chat/types';
import { demoSteps } from '../src/night/events';

type Node = { [key: string]: unknown };
const allowed = new Set([
  '$schema',
  '$id',
  '$defs',
  '$ref',
  'title',
  'description',
  'default',
  'type',
  'const',
  'enum',
  'properties',
  'required',
  'additionalProperties',
  'oneOf',
  'anyOf',
  'items',
  'maxLength',
  'minLength',
  'pattern',
  'format',
  'minimum',
  'maximum',
  'maxItems',
  'minItems',
]);
const used = new Set<string>();
function inspect(node: unknown) {
  if (!node || typeof node !== 'object' || Array.isArray(node)) return;
  for (const [key, value] of Object.entries(node)) {
    used.add(key);
    if (key === 'properties' || key === '$defs') Object.values(value as Node).forEach(inspect);
    else if (key === 'oneOf' || key === 'anyOf') (value as unknown[]).forEach(inspect);
    else if (key === 'items' || (key === 'additionalProperties' && typeof value === 'object')) inspect(value);
  }
}
inspect(published);
// Ajv 6 cannot claim 2020-12 support. This mechanical dialect adaptation is valid only
// while the checked schema uses the shared keyword set above: no constraints are removed.
function draft07(node: unknown): unknown {
  if (Array.isArray(node)) return node.map(draft07);
  if (!node || typeof node !== 'object') return node;
  return Object.fromEntries(
    Object.entries(node).map(([key, value]) => [
      key === '$defs' ? 'definitions' : key,
      key === '$schema'
        ? 'http://json-schema.org/draft-07/schema#'
        : key === '$ref'
          ? String(value).replace('#/$defs/', '#/definitions/')
          : draft07(value),
    ]),
  );
}
const validator = new Ajv({
  allErrors: true,
  strictKeywords: true,
  format: 'full',
  coerceTypes: false,
  useDefaults: false,
  removeAdditional: false,
}).compile(draft07(published) as object);
const common = { v: 1, run_id: 'synthetic-run', seq: 1, ts: '2026-10-21T01:02:03+08:00' };
const question = {
  ask_id: 'ask-1',
  question: '先看什么？',
  options: [{ id: 'a', label: '安排' }],
  allow_free_text: true,
  multi: false,
  why: '先从你在意的开始。',
};
const choice = {
  id: 'a',
  title: '先了解',
  benefit: '',
  cost: '',
  risk: '',
  reversibility: 'unknown',
  first_step: '',
  unknowns: ['risk'],
};
const choices = { options_id: 'options-1', options: [choice, { ...choice, id: 'b' }] };
const publicReceipt = { write_status: 'saved', fact_id: 'fact-1' };
const envelope = {
  schema: 'core4.0',
  message_id: 'message-1',
  text: '合成完整答复',
  receipts: [publicReceipt],
  used_fact_ids: [],
  used_claim_ids: [],
  asked: null,
  options: null,
  review: { state: 'passed', reasons: [] },
  usage: {},
};
const bodies: Record<string, Node> = {
  started: { thread_id: 'thread-1', message_id: 'message-1', incognito: false },
  status: { text: '正在核对', phase: 'reviewing' },
  tool_call: { call_id: 'call-1', name: 'memory_search', summary: '查找记忆' },
  tool_result: { call_id: 'call-1', name: 'memory_search', summary: '已核对', ok: true, receipt: publicReceipt },
  text_delta: { text: '合成内容' },
  text_reset: { text: '', reason: 'resumed' },
  memory_receipt: { fact_id: 'fact-1', write_status: 'saved', summary: '合成偏好', sensitive: false },
  ask_user: question,
  present_options: choices,
  review: { state: 'passed', reasons: [] },
  final: { message_id: 'message-1', envelope },
  error: { code: 'OFFLINE', message: '网络暂时波动', retryable: true },
};
function assertSchema(type: string, data: Node, valid: boolean) {
  expect(validator({ type, data }), JSON.stringify(validator.errors)).toBe(valid);
}

describe('published P3 events v1 Schema, independently validated with existing Ajv', () => {
  it('pins the byte-exact upstream artifact and verifies the shared-keyword adaptation boundary', () => {
    const raw = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), 'fixtures/events_v1.schema.json'));
    expect(createHash('sha256').update(raw).digest('hex')).toBe(provenance.fixture_sha256);
    expect(provenance.source_commit).toBe('064954eeb47f2ca3bf0dc7fa32bc93902f083e04');
    expect(published.$schema).toBe('https://json-schema.org/draft/2020-12/schema');
    expect([...used].filter((key) => !allowed.has(key))).toEqual([]);
    expect(used.has('$defs')).toBe(true);
    expect(used.has('pattern')).toBe(true);
  });
  it.each(Object.entries(bodies))(
    'validates actual published %s constraints and the frontend acceptance path',
    (type, body) => {
      const data = { ...common, ...body };
      assertSchema(type, data, true);
      expect(parseWireEventV1(data, type)).toBeDefined();
    },
  );
  it.each([
    ['started', { area_id: null, topic_id: null }],
    ['tool_result', { receipt: null }],
    ['text_reset', { revision_id: null }],
    ['memory_receipt', { fact_id: null, proposal_id: 'proposal-1', undo_token: null }],
    ['present_options', { prompt: null }],
    ['review', { revision_id: null }],
    ['final', { envelope: { ...envelope, schema_version: 'core4.0', answer: null, validation: null, meta: null } }],
  ] as const)('accepts Schema-valid nullable or optional %s server fields', (type, patch) => {
    const data = { ...common, ...bodies[type], ...patch };
    assertSchema(type, data, true);
    expect(parseWireEventV1(data, type)).toBeDefined();
    expect(chatEvent(data, type)).toBeDefined();
  });
  it('validates optional public metadata, token usage and compatibility fields without displaying them', () => {
    const complete = {
      ...envelope,
      schema_version: null,
      answer: 'legacy alias is not the displayed answer',
      validation: { status: 'validated', valid: true, schema: 'core4.0' },
      meta: {
        core_run: { run_id: common.run_id, operation_id: 'operation-1' },
        subject_id: 'subject-1',
        case_ids: ['case-1'],
        structural_warnings: [{ code: 'warning', count: 1 }],
      },
      usage: {
        model_steps: null,
        model_streams_this_execution: 0,
        replayed_model_steps: 1,
        reported_tokens: {
          input_tokens: 0,
          output_tokens: null,
          cache_creation_input_tokens: 1,
          cache_read_input_tokens: 2,
        },
        usage_known: false,
        offline: null,
      },
    };
    const data = { ...common, message_id: 'message-1', envelope: complete };
    assertSchema('final', data, true);
    expect(chatEvent(data, 'final')).toMatchObject({ envelope: { answer: envelope.text, receipts: [] } });
    expect(normalizeEnvelope(complete)).not.toHaveProperty('meta');
    expect(normalizeEnvelope(complete)).not.toHaveProperty('usage');
  });
  it.each(['cards', 'review', 'error', 'resumed', 'streaming', 'queued'] as const)(
    'validates every emitted %s synthetic frame against the published artifact',
    (scenario) => {
      demoSteps(scenario).forEach((step, index) => {
        const data = { ...common, seq: index + 1, ...step.payload };
        assertSchema(step.type, data, true);
        expect(chatEvent(data, step.type)).toBeDefined();
      });
    },
  );
  it.each(['saved', 'pending_confirm', 'undone', 'rejected'])(
    'retains prior %s memory display, consent and capabilities across a generic final receipt',
    (write_status) => {
      const memory = chatEvent(
        {
          ...common,
          proposal_id: 'proposal-1',
          write_status,
          summary: '合成私密偏好',
          sensitive: true,
          ...(write_status === 'saved' ? { undo_token: 'prior-undo' } : {}),
        },
        'memory_receipt',
      )!;
      const before = reduceChat(initialStream(), memory);
      const data = {
        ...common,
        seq: 2,
        message_id: 'message-1',
        envelope: { ...envelope, receipts: [{ proposal_id: 'proposal-1', write_status: 'saved', revision: 99 }] },
      };
      assertSchema('final', data, true);
      const final = chatEvent(data, 'final')!;
      const after = reduceChat(before, final);
      expect(after.receipts).toEqual(before.receipts);
      expect(after.receipts[0]).toMatchObject({ write_status, sensitive: true, summary: '合成私密偏好' });
      expect(after.receipts[0].revision).toBeUndefined();
      expect(reduceChat(initialStream(), final).receipts).toEqual([]);
    },
  );
  it('does not reinterpret an explicit v1 final containing full memory fields as legacy history', () => {
    const full = {
      ...envelope,
      receipts: [{ fact_id: 'fact-1', write_status: 'saved', summary: '旧格式摘要', sensitive: true }],
    };
    const data = { ...common, message_id: 'message-1', envelope: full };
    assertSchema('final', data, false);
    expect(chatEvent(data, 'final')).toBeUndefined();
    expect(normalizeEnvelope(full)?.receipts[0].summary).toBe('旧格式摘要');
    expect(normalizeEnvelope({ schema_version: null, answer: 'must not guess legacy' })).toBeUndefined();
  });
  it.each([
    ['status', { seq: 0 }],
    ['status', { run_id: '含空格 not-an-id' }],
    ['status', { run_id: 'x'.repeat(201) }],
    ['status', { text: '' }],
    ['status', { text: '字'.repeat(161) }],
    ['status', { ts: '2026-10-21T01:02:03.1234567+08:00' }],
    ['tool_call', { name: 'invalid-tool-name' }],
    ['tool_call', { summary: '字'.repeat(161) }],
    ['text_delta', { text: '' }],
    ['text_delta', { text: '字'.repeat(200001) }],
    ['ask_user', { options: Array.from({ length: 5 }, (_, index) => ({ id: `a-${index}`, label: '选项' })) }],
    ['ask_user', { why: '' }],
    ['review', { reasons: [{ code: 'unpublished_reason', severity: 1 }] }],
    ['memory_receipt', { proposal_id: 'proposal-1' }],
    ['memory_receipt', { summary: '' }],
    ['error', { code: 'lowercase' }],
    ['final', { envelope: { ...envelope, usage: { internal_trace: 'must-reject' } } }],
    ['final', { envelope: { ...envelope, receipts: [{ ...publicReceipt, summary: 'not-a-PublicReceipt-field' }] } }],
    ['memory_receipt', { undo_token: 'x'.repeat(1025) }],
    ['ask_user', { question: '字'.repeat(501) }],
    [
      'present_options',
      {
        options: [
          { ...choice, unknowns: Array(21).fill('risk') },
          { ...choice, id: 'b' },
        ],
      },
    ],
    ['tool_result', { receipt: { ...publicReceipt, revision: 0 } }],
    ['tool_result', { receipt: { ...publicReceipt, affected_ids: Array(1025).fill('fact-1') } }],
    ['final', { envelope: { ...envelope, text: '' } }],
    ['final', { envelope: { ...envelope, used_fact_ids: ['bad id'] } }],
    ['final', { envelope: { ...envelope, usage: { reported_tokens: null } } }],
    ['final', { envelope: { ...envelope, usage: { reported_tokens: { input_tokens: -1 } } } }],
    ['final', { envelope: { ...envelope, validation: { status: 'validated', valid: false, schema: 'core4.0' } } }],
    [
      'final',
      {
        envelope: {
          ...envelope,
          meta: {
            core_run: { run_id: 'run', operation_id: 'op' },
            subject_id: 'subject',
            case_ids: [],
            structural_warnings: [{ code: '', count: 0 }],
          },
        },
      },
    ],
  ] as const)('rejects Schema-invalid %s payloads at the explicit v1 client boundary', (type, patch) => {
    const data = { ...common, ...bodies[type], ...patch };
    assertSchema(type, data, false);
    expect(parseWireEventV1(data, type)).toBeUndefined();
  });
});
