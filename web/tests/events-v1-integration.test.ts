import { describe, expect, it } from 'vitest';
import { chatEvent, normalizeEnvelope } from '../src/chat/events';
import { parseWireEventV1 } from '../src/chat/wireV1';
import { initialStream } from '../src/chat/types';
import { reduceChat } from '../src/chat/reducer';
import { demoSteps, playDemo } from '../src/night/events';
import { createNightPort } from '../src/night/port';
import { beijingDateKey, beijingTimestamp } from '../src/time/beijing';

describe('frozen v1 public projection and isolated demo', () => {
  it.each(['cards', 'review', 'error', 'resumed'] as const)('validates every %s demo wire payload', (scenario) => {
    for (const [index, step] of demoSteps(scenario).entries()) {
      const data = { ...step.payload, v: 1, run_id: 'isolated-run', seq: index + 1, ts: '2026-10-20T23:00:00+08:00' };
      expect(parseWireEventV1(data, step.type), step.type).toBeDefined();
      expect(chatEvent(data, step.type), step.type).toBeDefined();
      expect(Object.hasOwn(step, 'reviewPending')).toBe(false);
    }
  });

  it('commits structured decisions and review from core4 while retaining stable question IDs', async () => {
    let state = initialStream();
    await playDemo(
      'review',
      (event) => {
        state = reduceChat(state, event);
      },
      new AbortController().signal,
      0,
      { runId: 'isolated-run', now: () => new Date('2026-10-20T15:00:00Z') },
    );
    expect(state.complete).toBe(true);
    expect(state.review?.state).toBe('revised');
    expect(state.revised).toBe(true);
    expect(state.revisionId).toBe('local-revision-1');
    expect(state.reviewPending).toBe(false);
    expect(state.question).toMatchObject({ askId: 'local-ask', optionIds: ['trial', 'clarify'], multi: false });
    expect(state.decisions[1]).toMatchObject({ id: 'clarify', unknowns: ['risk'], reversibility: 'partial' });
    expect(state.receipts[1]).toMatchObject({ write_status: 'pending_confirm', sensitive: true });
    expect(state.text).not.toContain('所有安排定下来');
  });

  it('retains old core3 and unfrozen historical core4 reads without guessing a version', () => {
    expect(normalizeEnvelope({ schema: 'core3.0', answer: '旧回答' })?.answer).toBe('旧回答');
    expect(
      normalizeEnvelope({ schema: 'core4.0', text: '', asked: { question: '旧问题', options: [] } }),
    ).toMatchObject({ answer: '', question: { question: '旧问题' }, decisions: [] });
    expect(normalizeEnvelope({ schema: 'core5.0', answer: '不能降级' })).toBeUndefined();
    expect(chatEvent({ v: 1, text: '不能降级' }, 'text_delta')).toBeUndefined();
  });

  it('projects only frozen review/options from persisted core4 and hides profile receipts', () => {
    const raw = demoSteps('review').find((step) => step.type === 'final')!.payload.envelope as Record<string, unknown>;
    const result = normalizeEnvelope({
      ...raw,
      receipts: [{ fact_id: 'profile-event', write_status: 'saved', field: 'birth.date', summary: '2000-01-01' }],
    });
    expect(result?.review).toMatchObject({ state: 'revised', revisionId: 'local-revision-1' });
    expect(result?.decisions).toHaveLength(2);
    expect(result?.receipts).toEqual([]);
    expect(normalizeEnvelope({ ...raw, review: { state: 'invented' }, options: { options: [] } })).toMatchObject({
      decisions: [],
    });
  });

  it('bridges public pending_confirm to the mock aggregate without inventing a wire revision', async () => {
    const port = createNightPort();
    const item = {
      proposal_id: 'local-proposal',
      write_status: 'pending_confirm',
      sensitive: true,
      summary: '希望跟进一项健康安排（合成示例）',
    };
    expect(port.memory.supports('remember', item)).toBe(true);
    expect(port.memory.supports('remember-category', item)).toBe(true);
    expect(port.memory.supports('remember', { ...item, summary: '另一个内容' })).toBe(false);
    const saved = await port.memory.execute('remember', item);
    expect(saved.write_status).toBe('saved');
    expect(await port.memory.execute('remember', item)).toBe(saved);
  });

  it('binds idempotent answer receipts to IDs as well as visible text', async () => {
    const port = createNightPort();
    const context = { askId: 'ask-1', optionIds: ['choice-1', 'choice-2'] };
    const result = await port.answer('第一；第二', 'request-1', context);
    context.optionIds.reverse();
    expect(result.optionIds).toEqual(['choice-1', 'choice-2']);
    expect(await port.answer('第一；第二', 'request-1', { askId: 'ask-1', optionIds: ['choice-1', 'choice-2'] })).toBe(
      result,
    );
    await expect(
      port.answer('第一；第二', 'request-1', { askId: 'ask-2', optionIds: ['choice-1', 'choice-2'] }),
    ).rejects.toThrow('已经回答');
  });
});

describe('explicit Beijing time independent of the host timezone', () => {
  it.each([
    ['2026-10-20T15:59:59Z', '2026-10-20', '2026-10-20T23:59:59.000+08:00'],
    ['2026-10-20T16:00:00Z', '2026-10-21', '2026-10-21T00:00:00.000+08:00'],
  ])('%s uses UTC+8 day boundaries', (iso, day, timestamp) => {
    expect(beijingDateKey(new Date(iso))).toBe(day);
    expect(beijingTimestamp(new Date(iso))).toBe(timestamp);
  });
  it('rejects invalid instants instead of recording the machine date', () => {
    expect(() => beijingTimestamp(new Date('invalid'))).toThrow('时间无效');
  });
});
