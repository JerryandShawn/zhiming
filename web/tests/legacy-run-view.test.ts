import { describe, expect, it } from 'vitest';
import { createLegacyRunView, type LegacyRunElements } from '../src/legacy/runView';

function fixture() {
  const elements: LegacyRunElements = {
    answer: document.createElement('div'),
    status: document.createElement('p'),
    review: document.createElement('span'),
    interrupted: document.createElement('span'),
  };
  elements.answer.textContent = '原网页占位';
  elements.review.hidden = elements.interrupted.hidden = true;
  let current = true;
  const view = createLegacyRunView({ runId: 'run-synthetic', elements, isCurrent: () => current });
  const event = (seq: number, type: string, body: Record<string, unknown> = {}) => ({
    v: 1,
    run_id: 'run-synthetic',
    seq,
    ts: '2026-10-27T09:00:00+08:00',
    ...body,
    type,
  });
  return { elements, view, event, retire: () => (current = false) };
}

describe('old-page native DOM view over frozen v1', () => {
  it('does not touch an old page until valid events arrive; renders exact deltas as text', () => {
    const f = fixture();
    expect(f.elements.answer.textContent).toBe('原网页占位');
    expect(f.view.accept(f.event(1, 'text_delta', { text: '你好\n' }), 'text_delta')).toBe('applied');
    f.view.accept(f.event(2, 'text_delta', { text: '<img src=x onerror=alert(1)>🙂' }), 'text_delta');
    expect(f.elements.answer.textContent).toBe('你好\n<img src=x onerror=alert(1)>🙂');
    expect(f.elements.answer.children.length).toBe(0);
  });

  it('replaces the whole draft on revision and never appends its old text', () => {
    const f = fixture();
    f.view.accept(f.event(1, 'text_delta', { text: '旧稿' }), 'text_delta');
    f.view.accept(f.event(2, 'text_reset', { text: '修订稿', reason: 'revised', revision_id: 'rev-1' }), 'text_reset');
    f.view.accept(f.event(3, 'text_delta', { text: '。' }), 'text_delta');
    expect(f.elements.answer.textContent).toBe('修订稿。');
    expect(f.elements.review.textContent).toBe('已修订');
    expect(f.elements.review.hidden).toBe(false);
  });

  it.each(['passed', 'skipped'] as const)('pending → %s clears quiet review without error UI', (state) => {
    const f = fixture();
    f.view.accept(f.event(1, 'review', { state: 'pending', reasons: [] }), 'review');
    expect(f.elements.review.textContent).toBe('复核中');
    f.view.accept(f.event(2, 'review', { state, reasons: [] }), 'review');
    expect(f.elements.review.textContent).toBe('');
    expect(f.elements.review.hidden).toBe(true);
    expect(f.elements.status.textContent).toBe('');
  });

  it('shows only safe tool summary, without appending the internal tool name', () => {
    const f = fixture();
    f.view.accept(f.event(1, 'status', { text: '在想…', phase: 'thinking' }), 'status');
    expect(f.elements.status.textContent).toBe('在想…');
    f.view.accept(
      f.event(2, 'tool_call', { call_id: 'call-1', name: 'date_calc', summary: '算了一下日期' }),
      'tool_call',
    );
    expect(f.elements.status.textContent).toBe('算了一下日期');
  });

  it('uses the committed final text as authority and closes the view', () => {
    const f = fixture();
    f.view.accept(f.event(1, 'text_delta', { text: '流中的草稿' }), 'text_delta');
    const envelope = {
      schema: 'core4.0',
      message_id: 'message-1',
      text: '最终已提交正文',
      receipts: [],
      used_fact_ids: [],
      used_claim_ids: [],
      asked: null,
      options: null,
      review: { state: 'skipped', reasons: [] },
      usage: {},
    };
    expect(f.view.accept(f.event(2, 'final', { message_id: 'message-1', envelope }), 'final')).toBe('applied');
    expect(f.elements.answer.textContent).toBe('最终已提交正文');
    expect(f.elements.review.hidden).toBe(true);
    expect(f.view.snapshot()).toMatchObject({ terminal: true, lastEventId: '2' });
    expect(f.view.accept(f.event(3, 'text_delta', { text: '迟到' }), 'text_delta')).toBe('terminal');
  });

  it('resumed text replaces the partial answer without claiming it was revised', () => {
    const f = fixture();
    f.view.accept(f.event(1, 'text_delta', { text: '断线前' }), 'text_delta');
    f.view.accept(f.event(2, 'text_reset', { text: '恢复后的完整正文', reason: 'resumed' }), 'text_reset');
    expect(f.elements.answer.textContent).toBe('恢复后的完整正文');
    expect(f.elements.review.hidden).toBe(true);
  });

  it('keeps partial text on authoritative cancellation and refuses later final/delta', () => {
    const f = fixture();
    f.view.accept(f.event(1, 'text_delta', { text: '已出的部分' }), 'text_delta');
    f.view.accept(f.event(2, 'error', { code: 'RUN_CANCELLED', message: '已停止', retryable: false }), 'error');
    expect(f.elements.answer.textContent).toBe('已出的部分');
    expect(f.elements.interrupted.textContent).toBe('已中断');
    expect(f.elements.interrupted.hidden).toBe(false);
    expect(f.view.accept(f.event(3, 'text_delta', { text: '迟到' }), 'text_delta')).toBe('terminal');
    expect(f.elements.answer.textContent).toBe('已出的部分');
  });

  it('does not mistake duplicate/gapped/foreign events for new text or advance the cursor', () => {
    const f = fixture();
    const first = f.event(1, 'text_delta', { text: '甲' });
    f.view.accept(first, 'text_delta');
    expect(f.view.accept(first, 'text_delta')).toBe('duplicate');
    expect(f.view.accept(f.event(3, 'text_delta', { text: '丙' }), 'text_delta')).toBe('gap');
    expect(f.view.accept({ ...f.event(2, 'text_delta', { text: '乙' }), run_id: 'other-run' }, 'text_delta')).toBe(
      'foreign',
    );
    expect(f.view.snapshot()).toMatchObject({ text: '甲', lastEventId: '1' });
    f.view.accept(f.event(2, 'text_delta', { text: '乙' }), 'text_delta');
    expect(f.elements.answer.textContent).toBe('甲乙');
  });

  it('drops malformed/extra fields and rejects mismatched named events', () => {
    const f = fixture();
    expect(f.view.accept(f.event(1, 'text_delta', { text: '私有', reasoning: 'PRIVATE' }), 'text_delta')).toBe(
      'invalid',
    );
    expect(f.view.accept(f.event(1, 'text_delta', { text: '甲' }), 'status')).toBe('invalid');
    expect(f.elements.answer.textContent).toBe('原网页占位');
    expect(f.view.snapshot().lastEventId).toBeUndefined();
  });

  it.each(['owner', 'dispose'] as const)('ignores late callbacks after %s retirement', (kind) => {
    const f = fixture();
    if (kind === 'owner') f.retire();
    else f.view.dispose();
    expect(f.view.accept(f.event(1, 'text_delta', { text: '迟到' }), 'text_delta')).toBe('stale');
    expect(f.elements.answer.textContent).toBe('原网页占位');
  });
});
