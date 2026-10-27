import { describe, expect, it } from 'vitest';
import { createLegacyRunView } from '../src/legacy/runView';

describe('old-page minimal projection consumes the whole frozen event catalogue', () => {
  it.each(['saved', 'pending_confirm', 'undone', 'rejected'])(
    'memory %s does not block later text or invent an action',
    (write_status) => {
      const elements = {
        answer: document.createElement('div'),
        status: document.createElement('p'),
        review: document.createElement('span'),
        interrupted: document.createElement('span'),
      };
      const view = createLegacyRunView({ runId: 'synthetic-catalog', elements, isCurrent: () => true });
      const question = {
        ask_id: 'ask-1',
        question: '先看哪一项？',
        options: [{ id: 'a', label: '工作' }],
        allow_free_text: true,
        multi: false,
        why: '缩小范围',
      };
      const decision = (id: string) => ({
        id,
        title: '先核对',
        benefit: '清楚',
        cost: '时间',
        risk: '延迟',
        reversibility: 'easy',
        first_step: '询问',
        unknowns: [],
      });
      const receipt = { fact_id: 'fact-1', write_status, summary: '不得误当成正文或按钮', sensitive: false };
      const envelope = {
        schema: 'core4.0',
        message_id: 'message-1',
        text: '最终已提交正文',
        receipts: [{ fact_id: 'fact-1', write_status }],
        asked: question,
        options: { options_id: 'choices-1', options: [decision('a'), decision('b')] },
        review: { state: 'skipped', reasons: [] },
        usage: {},
        used_fact_ids: [],
        used_claim_ids: [],
      };
      const events: [string, Record<string, unknown>][] = [
        ['started', { thread_id: 'life:self', message_id: 'message-1', incognito: false }],
        ['status', { phase: 'thinking', text: '正在核对' }],
        ['tool_call', { call_id: 'call-1', name: 'date_calc', summary: '核对日期' }],
        [
          'tool_result',
          {
            call_id: 'call-1',
            name: 'date_calc',
            summary: '日期已核对',
            ok: true,
            receipt: { write_status: 'saved', fact_id: 'fact-1' },
          },
        ],
        ['memory_receipt', receipt],
        ['ask_user', question],
        ['present_options', envelope.options],
        ['text_delta', { text: '断线前草稿' }],
        ['text_reset', { text: '恢复正文', reason: 'resumed' }],
        ['review', { state: 'skipped', reasons: [] }],
        ['final', { message_id: 'message-1', envelope }],
      ];
      events.forEach(([type, body], index) => {
        const seq = index + 1;
        const event = { v: 1, run_id: 'synthetic-catalog', seq, ts: '2026-10-27T10:00:00+08:00', ...body };
        expect(view.accept(event, type), type).toBe('applied');
        expect(view.snapshot().lastEventId, type).toBe(String(seq));
        expect(view.accept(event, type), type + ' replay').toBe('duplicate');
      });
      expect(view.snapshot()).toMatchObject({ text: '最终已提交正文', terminal: true, lastEventId: '11' });
      expect(elements.answer.textContent).toBe('最终已提交正文');
      expect(elements.status.textContent).toBe('');
      expect(elements.review.hidden).toBe(true);
      for (const element of Object.values(elements)) {
        expect(element.querySelector('button,a,input')).toBeNull();
        expect(element.textContent).not.toContain(receipt.summary);
        expect(element.textContent).not.toContain('date_calc');
      }
    },
  );
});
