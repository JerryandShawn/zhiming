import { describe, expect, it } from 'vitest';
import { runStates, threadAcceptance, threadMessage } from '../src/threads/contracts';

const input = { request_id: 'synthetic-request:1', message: ' 保留原输入\n' };
const accepted = {
  run_id: 'synthetic-run',
  thread_id: 'life:self',
  status: 'queued',
  runtime: 'v4',
  run_url: '/api/runs/synthetic-run',
  events_url: '/api/runs/synthetic-run/events',
};

describe('published thread message DTO', () => {
  it('preserves stable request/message bytes, supplies only documented defaults and takes an immutable snapshot', () => {
    const cases = ['case-1'];
    const value = threadMessage({ ...input, case_ids: cases }, false);
    cases.push('case-2');
    expect(value).toEqual({
      ...input,
      subject_id: 'self',
      conversation_id: 'shared',
      case_ids: ['case-1'],
      depth: 'standard',
    });
    expect(Object.isFrozen(value)).toBe(true);
    expect(Object.isFrozen(value.case_ids)).toBe(true);
  });
  it.each(['images', 'selection', 'runtime', 'owner', 'thread_id', 'parent_run', 'draw_id'])(
    'refuses %s without silently discarding it',
    (field) => {
      expect(() => threadMessage({ ...input, [field]: [] }, false)).toThrow('尚未支持');
    },
  );
  it.each([
    null,
    undefined,
    1,
    [],
    {},
    { ...input, depth: 'fast' },
    { ...input, subject_id: null },
    { ...input, conversation_id: '' },
    { ...input, case_ids: undefined },
    { ...input, request_id: 'a/b' },
    { ...input, message: '' },
    { ...input, message: '\u001c\u0085\u3000' },
    { ...input, message: '🙂'.repeat(16001) },
    { ...input, subject_id: '🙂'.repeat(201) },
    { ...input, case_ids: [null] },
    { ...input, case_ids: Array(2) },
    { ...input, case_ids: Array(9).fill('case') },
  ])('rejects unsupported shapes and boundary violations %#', (value) => {
    expect(() => threadMessage(value, false)).toThrow();
  });
  it('uses Unicode code points rather than UTF-16 length; FEFF is not Python strip whitespace', () => {
    expect(
      threadMessage({ ...input, message: '🙂'.repeat(16000), subject_id: '🙂'.repeat(200) }, false).message,
    ).toHaveLength(32000);
    expect(threadMessage({ ...input, message: '\ufeff' }, false).message).toBe('\ufeff');
  });
  it('does not invent case-ID uniqueness, ASCII or nonempty restrictions', () => {
    expect(threadMessage({ ...input, case_ids: ['', '合成事项', '合成事项'] }, false).case_ids).toEqual([
      '',
      '合成事项',
      '合成事项',
    ]);
  });
  it('uses explicit private scope and refuses long-term cases before submission', () => {
    expect(() => threadMessage({ ...input, case_ids: ['case'] }, true)).toThrow();
    expect(threadMessage(input, true).case_ids).toEqual([]);
  });
});

describe('thread 202 acceptance is distinct from legacy chat acceptance', () => {
  it.each(runStates)('accepts %s including idempotently replayed terminal runs', (status) => {
    expect(threadAcceptance({ ...accepted, status }).status).toBe(status);
  });
  it('uses returned thread identity after natural private routing and allows 205-character life IDs', () => {
    expect(threadAcceptance({ ...accepted, thread_id: 'incognito:synthetic' }).thread_id).toBe('incognito:synthetic');
    expect(threadAcceptance({ ...accepted, thread_id: `life:${'字'.repeat(200)}` }).thread_id).toHaveLength(205);
  });
  it('v3 has no fabricated events URL', () => {
    const { events_url: omitted, ...v3 } = { ...accepted, runtime: 'v3' };
    expect(omitted).toBeTruthy();
    expect(threadAcceptance(v3)).toEqual(v3);
    expect(threadAcceptance(v3)).not.toHaveProperty('events_url');
    expect(() => threadAcceptance({ ...accepted, runtime: 'v3' })).toThrow();
  });
  it.each([
    { ...accepted, message_id: 'old-chat-message' },
    { ...accepted, status: 'finished' },
    { ...accepted, runtime: 'v5' },
    { ...accepted, events_url: undefined },
    { ...accepted, run_url: 'https://example.invalid/api/runs/synthetic-run' },
    { ...accepted, events_url: '//example.invalid/api/runs/synthetic-run/events' },
    { ...accepted, events_url: '/api/runs/another-run/events' },
    { ...accepted, events_url: '/api/runs/synthetic-run/events?after_seq=1' },
    { ...accepted, events_url: '/api/runs/synthetic-run/events#x' },
    { ...accepted, events_url: '/api/runs/./synthetic-run/events' },
    { ...accepted, run_id: '../run' },
    { ...accepted, thread_id: '\nprivate' },
    { ...accepted, thread_id: '' },
    { ...accepted, receipts: [] },
  ])('rejects drift, private fields and unsafe cross-run URLs %#', (value) => {
    expect(() => threadAcceptance(value)).toThrow('回执尚未核对');
  });
});
