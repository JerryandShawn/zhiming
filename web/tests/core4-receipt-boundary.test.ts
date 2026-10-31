import { describe, expect, it } from 'vitest';
import { normalizeEnvelope, chatEvent } from '../src/chat/events';
import { reduceChat } from '../src/chat/reducer';
import { initialStream } from '../src/chat/types';

const fakeSaved = { fact_id: 'synthetic-fact', write_status: 'saved', summary: '合成偏好' };
const core4 = { schema: 'core4.0', text: '只读当前信封', receipts: [] };

describe('R7: core4 never borrows old-web receipt aliases', () => {
  it.each([undefined, null, [], {}, 'invalid', 0])('receipts=%j does not revive old acknowledgements', (receipts) => {
    const value = normalizeEnvelope({
      ...core4,
      receipts,
      memory_receipts: [fakeSaved],
      meta: { saved_receipts: [fakeSaved] },
    });
    expect(value?.receipts).toEqual([]);
    expect(JSON.stringify(value)).not.toContain('合成偏好');
  });

  it('does not even read old aliases on the core4 branch', () => {
    const value = { ...core4 };
    for (const key of ['memory_receipts', 'meta'])
      Object.defineProperty(value, key, {
        get: () => {
          throw new Error('Old alias must stay unread');
        },
      });
    expect(normalizeEnvelope(value)?.receipts).toEqual([]);
  });

  it('keeps a permitted display receipt from receipts instead of its conflicting alias', () => {
    const value = normalizeEnvelope({
      ...core4,
      receipts: [{ ...fakeSaved, summary: '当前字段' }],
      memory_receipts: [{ ...fakeSaved, summary: '旧字段' }],
    });
    expect(value?.receipts).toHaveLength(1);
    expect(value?.receipts[0].summary).toBe('当前字段');
    expect(JSON.stringify(value)).not.toContain('旧字段');
  });

  it('public command ack cannot create a memory card or overwrite an authoritative stream receipt', () => {
    const memory = chatEvent(
      {
        v: 1,
        run_id: 'run-1',
        seq: 1,
        ts: '2026-10-27T10:00:00+08:00',
        fact_id: 'synthetic-fact',
        write_status: 'undone',
        summary: '已撤销的合成偏好',
        sensitive: false,
      },
      'memory_receipt',
    );
    expect(memory).toBeDefined();
    let state = reduceChat(initialStream(), memory!);
    const envelope = normalizeEnvelope({
      ...core4,
      receipts: [{ fact_id: 'synthetic-fact', write_status: 'saved' }],
      memory_receipts: [fakeSaved],
      meta: { saved_receipts: [fakeSaved] },
    });
    expect(envelope?.receipts).toEqual([]);
    state = reduceChat(state, { type: 'final', envelope: envelope! });
    expect(state.receipts).toHaveLength(1);
    expect(state.receipts[0]).toMatchObject({ write_status: 'undone', summary: '已撤销的合成偏好' });
  });

  it.each(['core4.0', 'core5.0'])('conflicting/unknown %s never downgrades to legacy receipt parsing', (schema) => {
    const data = { schema, schema_version: 'core3.0', answer: '旧正文', memory_receipts: [fakeSaved] };
    expect(normalizeEnvelope(data)).toBeUndefined();
  });

  it('preserves the separate old core3 compatibility path', () => {
    expect(
      normalizeEnvelope({ schema: 'core3.0', answer: '旧正文', memory_receipts: [fakeSaved] })?.receipts[0].summary,
    ).toBe('合成偏好');
  });
});
