import { describe, expect, it } from 'vitest';
import { initialStream, type ChatEvent, type Review } from '../src/chat/types';
import { reduceChat } from '../src/chat/reducer';

const review = (state: Review['state']): ChatEvent => ({
  type: 'review',
  review: { state, reasons: [{ code: 'generic_barnum', severity: 3 }], revisionId: 'r-1' },
});

describe('frozen-v1 stream projection', () => {
  it('uses explicit phase and review events rather than matching human text', () => {
    let state = reduceChat(initialStream(), { type: 'status', text: '复核中只是正文', phase: 'writing' });
    expect(state.reviewPending).toBe(false);
    state = reduceChat(state, { type: 'status', text: '核对一下', phase: 'reviewing' });
    expect(state.reviewPending).toBe(true);
    state = reduceChat(state, review('pending'));
    state = reduceChat(state, { type: 'status', text: '补充正文', phase: 'writing' });
    expect(state.reviewPending).toBe(true);
    state = reduceChat(state, review('passed'));
    expect(state.reviewPending).toBe(false);
    expect(state.revised).toBe(false);
  });

  it.each(['passed', 'skipped'] as const)(
    'clears an active review badge for %s without an error or revision',
    (verdict) => {
      let state = reduceChat(initialStream(), { type: 'status', text: '核对中', phase: 'reviewing' });
      state = reduceChat(state, review(verdict));
      expect(state).toMatchObject({ reviewPending: false, revised: false, status: '' });
      expect(state.error).toBeUndefined();
      expect(state.phase).toBeUndefined();
    },
  );

  it('keeps revised identity and replaces resumed text without inventing another reviewer decision', () => {
    let state = reduceChat(initialStream(), { type: 'text_delta', text: '不完整片段' });
    state = reduceChat(state, {
      type: 'text_reset',
      text: '恢复后的全文',
      reason: 'resumed',
      revision_id: 'recovery-1',
    });
    expect(state).toMatchObject({ text: '恢复后的全文', revised: false, revisionId: 'recovery-1' });
    state = reduceChat(state, review('revised'));
    expect(state).toMatchObject({ revised: true, revisionId: 'r-1', reviewPending: false });
    state = reduceChat(state, { type: 'text_reset', text: '随后恢复的全文', reason: 'resumed' });
    expect(state).toMatchObject({ text: '随后恢复的全文', revised: true, revisionId: 'r-1' });
  });

  it('matches concurrent calls of the same tool by call_id and never reopens duplicate calls', () => {
    let state = initialStream();
    for (const call_id of ['first', 'second'])
      state = reduceChat(state, { type: 'tool_call', name: 'memory_search', summary: '核对中', call_id });
    state = reduceChat(state, {
      type: 'tool_result',
      name: 'memory_search',
      summary: '第一条完成',
      call_id: 'first',
      ok: true,
    });
    expect(state.tools).toMatchObject([
      { callId: 'first', done: true, ok: true, summary: '第一条完成' },
      { callId: 'second', done: false },
    ]);
    const duplicate = reduceChat(state, {
      type: 'tool_call',
      name: 'memory_search',
      summary: '重复',
      call_id: 'first',
    });
    expect(duplicate).toBe(state);
    state = reduceChat(state, {
      type: 'tool_result',
      name: 'memory_search',
      summary: '第二条未完成',
      call_id: 'second',
      ok: false,
    });
    expect(state.tools[1]).toMatchObject({ callId: 'second', done: true, ok: false });
  });

  it('keeps all four program memory statuses and cannot make a rejected proposal look saved', () => {
    let state = initialStream();
    for (const write_status of ['pending_confirm', 'saved', 'undone', 'rejected']) {
      state = reduceChat(state, {
        type: 'memory_receipt',
        receipt: { proposal_id: 'proposal-1', write_status, summary: '合成提案', sensitive: true },
      });
      expect(state.receipts).toHaveLength(1);
      expect(state.receipts[0].write_status).toBe(write_status);
    }
  });

  it('takes the final review verdict and clears transient review indication', () => {
    const state = reduceChat(reduceChat(initialStream(), review('pending')), {
      type: 'final',
      envelope: {
        schema: 'core4.0',
        answer: '',
        professional_appendix: '',
        receipts: [],
        decisions: [],
        evidence: [],
        review: { state: 'revised', reasons: [], revisionId: 'final-r' },
      },
    });
    expect(state).toMatchObject({
      complete: true,
      reviewPending: false,
      revised: true,
      revisionId: 'final-r',
      text: '',
    });
  });

  it('keeps explicit destination and incognito fields without deriving them from prose', () => {
    const state = reduceChat(initialStream(), {
      type: 'started',
      run_id: 'run-1',
      thread_id: 'thread-1',
      message_id: 'message-1',
      area_id: 'study',
      topic_id: 'terms',
      incognito: false,
    });
    expect(state).toMatchObject({ runId: 'run-1', areaId: 'study', topicId: 'terms', incognito: false });
  });
});
