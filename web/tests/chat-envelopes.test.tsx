import { describe, expect, it } from 'vitest';
import { chatEvent, envelope, normalizeEnvelope, receipt } from '../src/chat/events';
import { hiddenProfile, publicChatText } from '../src/chat/publicProjection';
import { reduceChat, withReviewPending } from '../src/chat/reducer';
import { initialStream, type ChatEvent } from '../src/chat/types';

function event(value: unknown, namedType = ''): ChatEvent {
  const parsed = chatEvent(value, namedType);
  expect(parsed).toBeDefined();
  return parsed!;
}

describe('central result envelope projection', () => {
  it('keeps the real core3 result and legacy clarification contract', () => {
    const result = normalizeEnvelope({
      schema_version: 'core3.0',
      answer: '公开回答',
      plain_summary: '旧摘要',
      professional_appendix: '专业依据',
      decision_options: [
        { title: '先核对', benefit: '可靠', cost: '等待', risk: '延迟', reversibility: '可改', first_step: '询问' },
      ],
      evidence: [{ ref: 'fact:synthetic', claim: '合成事实', source_refs: [{ private: 'PRIVATE' }] }],
      meta: {
        saved_receipts: [
          { id: 'synthetic-fact', write_status: 'saved', content: '偏好', revision: 2, undo_token: 'undo-synthetic' },
        ],
        interrupt: {
          id: 'clarify:synthetic',
          state_version: { facts: 2, profile: 1 },
          questions: ['还需要哪些信息？'],
        },
        private: 'PRIVATE',
      },
    });
    expect(result).toEqual({
      schema: 'core3.0',
      answer: '公开回答',
      professional_appendix: '专业依据',
      receipts: [
        {
          fact_id: 'synthetic-fact',
          proposal_id: undefined,
          write_status: 'saved',
          summary: '偏好',
          revision: 2,
          undo_token: 'undo-synthetic',
        },
      ],
      decisions: [
        { option: '先核对', benefit: '可靠', cost: '等待', risk: '延迟', reversibility: '可改', first_step: '询问' },
      ],
      evidence: [{ ref: 'fact:synthetic', claim: '合成事实' }],
      interrupt: { id: 'clarify:synthetic', state_version: { facts: 2, profile: 1 }, questions: ['还需要哪些信息？'] },
    });
    expect(JSON.stringify(result)).not.toContain('PRIVATE');
    expect(envelope({ plain_summary: '旧摘要' }).answer).toBe('旧摘要');
    expect(envelope({ answer: '无版本旧记录' }).schema).toBeUndefined();
  });

  it('maps core4 text, program receipts and asked without inventing resume or review phases', () => {
    const result = normalizeEnvelope({
      schema: 'core4.0',
      message_id: 'message-synthetic',
      text: '准备重点取决于面试轮次。',
      receipts: [
        { proposal_id: 'proposal-synthetic', write_status: 'pending', summary: '合成偏好', category: 'communication' },
      ],
      asked: {
        question: '技术面还是终面？',
        options: ['技术面', { label: '终面', internal: 'PRIVATE' }],
        allow_free_text: true,
        why: '准备重点不同',
        storage_permission: true,
      },
      review: { revised: true, pending: true, reviewPhase: 'reviewing', private: 'PRIVATE' },
      used_fact_ids: ['PRIVATE'],
      used_claim_ids: ['PRIVATE'],
      usage: { private: 'PRIVATE' },
      decision_options: [{ option: 'UNKNOWN_DECISION' }],
      meta: { interrupt: { id: 'PRIVATE', state_version: { private: 'PRIVATE' }, questions: ['PRIVATE'] } },
    });
    expect(result).toMatchObject({
      schema: 'core4.0',
      messageId: 'message-synthetic',
      answer: '准备重点取决于面试轮次。',
      receipts: [
        { proposal_id: 'proposal-synthetic', write_status: 'pending', summary: '合成偏好', category: 'communication' },
      ],
      question: {
        question: '技术面还是终面？',
        options: ['技术面', '终面'],
        allow_free_text: true,
        why: '准备重点不同',
      },
      professional_appendix: '',
      decisions: [],
      evidence: [],
    });
    expect(result?.interrupt).toBeUndefined();
    expect(JSON.stringify(result)).not.toMatch(/PRIVATE|reviewPhase|storage_permission|UNKNOWN_DECISION/);
    // A normalized client projection is not another wire envelope.
    expect(chatEvent({ type: 'result', result })).toBeUndefined();
  });

  it('preserves a core4 question at final as a new-turn question, with no legacy interrupt', () => {
    const state = reduceChat(
      initialStream(),
      event({
        type: 'final',
        message_id: 'outer-message',
        envelope: {
          schema: 'core4.0',
          message_id: 'inner-message',
          text: '',
          receipts: [],
          asked: { question: '需要哪种帮助？', options: ['列提纲'], allow_free_text: false, why: '确认范围' },
        },
      }),
    );
    expect(state.complete).toBe(true);
    expect(state.messageId).toBe('inner-message');
    expect(state.question?.options).toEqual(['列提纲']);
    expect(state.envelope?.interrupt).toBeUndefined();
    expect(state.answered).toBeUndefined();
  });

  it('uses authoritative empty core4 text while keeping its final question', () => {
    const streamed = reduceChat(initialStream(), event({ type: 'text_delta', text: '尚未确认的临时结论' }));
    const completed = reduceChat(
      streamed,
      event({
        type: 'final',
        envelope: {
          schema: 'core4.0',
          text: '',
          asked: { question: '先补充哪项信息？', options: ['补充信息'] },
        },
      }),
    );
    expect(completed.text).toBe('');
    expect(completed.question?.question).toBe('先补充哪项信息？');
    expect(completed.complete).toBe(true);
  });

  it.each([{ answer: '' }, { schema_version: 'core3.0', answer: '' }])(
    'retains the legacy empty-final text fallback: %j',
    (result) => {
      const streamed = reduceChat(initialStream(), event({ type: 'text_delta', text: '旧流的完整正文' }));
      expect(reduceChat(streamed, event({ type: 'result', result })).text).toBe('旧流的完整正文');
    },
  );

  it.each([
    { schema: 'core5.0', text: '未知' },
    { schema_version: 4, text: '未知' },
    { schema: 'core4.0', schema_version: 'core3.0', text: '冲突', answer: '冲突' },
    { schema: null, answer: '未知' },
    { schema: 'core4.0', answer: '不能猜 text' },
    { schema: 'core4.0', text: { answer: '类型错误' } },
    { schema: 'core3.0', text: '不能猜 answer' },
    {},
    null,
    ['不能当作信封'],
  ])('does not turn unsupported or malformed results into a final: %j', (result) => {
    expect(normalizeEnvelope(result)).toBeUndefined();
    expect(chatEvent({ type: 'result', result })).toBeUndefined();
    expect(chatEvent({ type: 'final', envelope: result })).toBeUndefined();
    expect(envelope(result)).toEqual({
      answer: '',
      professional_appendix: '',
      receipts: [],
      decisions: [],
      evidence: [],
    });
  });

  it.each([null, [], '何时？', { text: '未知字段' }, { question: 3 }, { question: '  ' }])(
    'ignores an unknown asked shape: %j',
    (asked) => {
      expect(normalizeEnvelope({ schema: 'core4.0', text: '公开回答', asked })?.question).toBeUndefined();
    },
  );

  it('accepts matching explicit schema markers and never assumes free text permission', () => {
    const result = normalizeEnvelope({
      schema: 'core4.0',
      schema_version: 'core4.0',
      text: '公开',
      asked: {
        question: '技术面？',
        options: ['技术面', null, { label: '终面' }, { unknown: true }],
        allow_free_text: 'true',
      },
    });
    expect(result?.question).toEqual({
      question: '技术面？',
      options: ['技术面', '终面'],
      allow_free_text: false,
      why: '',
    });
  });
});

describe('event identity, terminal states and receipts', () => {
  const cases = [
    { type: 'started', run_id: 'synthetic-run', thread_id: 'synthetic-thread', message_id: 'synthetic-message' },
    { type: 'status', text: '正在核对' },
    { type: 'tool_call', name: 'calendar', summary: '核对日期' },
    { type: 'tool_result', name: 'calendar', summary: '日期已核对' },
    { type: 'text_delta', text: '正文' },
    { type: 'text_reset', text: '修订正文', reason: 'revised' },
    { type: 'memory_receipt', fact_id: 'synthetic-fact', write_status: 'saved', summary: '偏好' },
    { type: 'ask_user', question: '何时？', options: ['明天'], allow_free_text: true, why: '确认时间' },
    { type: 'present_options', options: [{ option: '先核对' }] },
    { type: 'final', envelope: { schema: 'core4.0', text: '最终回答' } },
    { type: 'error', code: 'OFFLINE', message: '稍后继续', retryable: true },
  ];
  it.each(cases)('accepts payload and named SSE event $type', (data) => {
    const { type, ...payload } = data;
    expect(event(payload, type)).toEqual(event(data));
    expect(event(data).type).toBe(type);
  });

  it('preserves started IDs and explicit error retryability without interpreting prose', () => {
    let state = reduceChat(initialStream(), event(cases[0]));
    expect(state).toMatchObject({
      runId: 'synthetic-run',
      threadId: 'synthetic-thread',
      messageId: 'synthetic-message',
    });
    state = reduceChat(state, event({ type: 'error', code: 'QUOTA', message: '稍后继续', retryable: false }));
    expect(state).toMatchObject({ errorCode: 'QUOTA', retryable: false, error: '稍后继续', reviewPending: false });
    state = reduceChat(state, event({ type: 'final', message_id: 'final-message', envelope: { answer: '已核对' } }));
    expect(state.messageId).toBe('final-message');
    expect(state.errorCode).toBeUndefined();
    expect(state.retryable).toBeUndefined();
  });

  it('uses only explicit local review state and clears it on final and error', () => {
    let state = reduceChat(initialStream(), event({ type: 'status', text: '正在复核，评审待完成' }));
    expect(state.reviewPending).toBeUndefined();
    state = withReviewPending(state, true);
    expect(state.reviewPending).toBe(true);
    const completed = reduceChat(
      state,
      event({ type: 'final', envelope: { schema: 'core4.0', text: '结论', review: { pending: true } } }),
    );
    expect(completed.reviewPending).toBe(false);
    expect(withReviewPending(completed, true).reviewPending).toBe(false);
    const failed = reduceChat(state, event({ type: 'error', code: 'ERROR', message: '未完成', retryable: true }));
    expect(withReviewPending(failed, true).reviewPending).toBe(false);
    expect(completed.revised).toBe(false);
  });

  it('distinguishes a revised replacement from a resumed replacement', () => {
    const restored = reduceChat(initialStream(), event({ type: 'text_reset', text: '恢复文本', reason: 'resumed' }));
    expect(restored.revised).toBe(false);
    const revised = reduceChat(restored, event({ type: 'text_reset', text: '评审核对后', reason: 'revised' }));
    expect(revised.revised).toBe(true);
    expect(reduceChat(revised, event({ type: 'text_reset', text: '再次恢复', reason: 'resumed' })).revised).toBe(true);
    expect(chatEvent({ type: 'text_reset', text: '未知原因', reason: 'reviewing' })).toBeUndefined();
    expect(chatEvent({ type: 'reviewPhase', phase: 'pending' })).toBeUndefined();
  });

  it('reconciles repeated program receipts and linked proposal confirmation without duplicating', () => {
    let state = reduceChat(
      initialStream(),
      event({ type: 'memory_receipt', proposal_id: 'proposal-synthetic', write_status: 'pending', summary: '偏好' }),
    );
    state = reduceChat(
      state,
      event({
        type: 'tool_result',
        name: 'memory_write',
        receipt: {
          proposal_id: 'proposal-synthetic',
          fact_id: 'fact-synthetic',
          write_status: 'saved',
          summary: '偏好',
          revision: 1,
        },
      }),
    );
    state = reduceChat(
      state,
      event({
        type: 'final',
        envelope: {
          schema: 'core4.0',
          text: '完成',
          receipts: [
            {
              proposal_id: 'proposal-synthetic',
              fact_id: 'fact-synthetic',
              write_status: 'saved',
              summary: '偏好',
              revision: 1,
            },
          ],
        },
      }),
    );
    expect(state.receipts).toHaveLength(1);
    expect(state.receipts[0]).toMatchObject({
      fact_id: 'fact-synthetic',
      proposal_id: 'proposal-synthetic',
      write_status: 'saved',
    });
    state = reduceChat(state, event({ type: 'memory_receipt', fact_id: 'fact-synthetic', write_status: 'stopped' }));
    expect(state.receipts).toHaveLength(1);
    expect(state.receipts[0].write_status).toBe('stopped');
  });

  it('does not conflate unrelated fact and proposal identifiers or model prose with receipts', () => {
    let state = reduceChat(initialStream(), event({ type: 'text_delta', text: '我已经保存了' }));
    expect(state.receipts).toEqual([]);
    for (const item of [{ fact_id: 'same-literal' }, { proposal_id: 'same-literal' }])
      state = reduceChat(state, event({ type: 'memory_receipt', ...item, write_status: 'saved' }));
    expect(state.receipts).toHaveLength(2);
    expect(receipt({ summary: '没有程序 ID', write_status: 'saved' })).toBeUndefined();
    expect(receipt({ fact_id: 'synthetic', summary: '没有状态' })).toBeUndefined();
  });

  it('joins fact and proposal aliases only when a program receipt explicitly links them', () => {
    let state = initialStream();
    for (const identifiers of [
      { proposal_id: 'proposal' },
      { fact_id: 'fact' },
      { proposal_id: 'proposal', fact_id: 'fact' },
    ])
      state = reduceChat(state, event({ type: 'memory_receipt', ...identifiers, write_status: 'saved' }));
    expect(state.receipts).toHaveLength(1);
    state = reduceChat(state, event({ type: 'memory_receipt', fact_id: 'fact', write_status: 'stopped' }));
    expect(state.receipts[0]).toMatchObject({ fact_id: 'fact', proposal_id: 'proposal', write_status: 'stopped' });
  });

  it('retains category only when supplied as a safe string', () => {
    const source = { fact_id: 'synthetic', write_status: 'pending' };
    expect(receipt({ ...source, category: ' communication ' })?.category).toBe('communication');
    for (const category of [
      undefined,
      null,
      4,
      {},
      ['communication'],
      '',
      'bad\ncategory',
      'a'.repeat(121),
      'birth.solar_datetime: PRIVATE',
    ])
      expect(receipt({ ...source, category })?.category).toBeUndefined();
    expect(receipt({ ...source, revision: -1 })?.revision).toBeUndefined();
    expect(receipt({ ...source, revision: 1.5 })?.revision).toBeUndefined();
  });
});

describe('public data whitelist and birth privacy', () => {
  const privateBirth = 'birth.solar_datetime: SYNTHETIC_PRIVATE_BIRTH';
  it.each([
    { field: 'birth.solar_datetime', value: '1998-03-12', content: '1998-03-12' },
    { field: 'birth.location.lng', value: 116.4, content: '116.4' },
    { field: 'birth', value: { solar_datetime: '1998-03-12' }, content: '1998-03-12' },
    { kind: 'profile', content: '1998-03-12', summary: '1998-03-12' },
  ])('filters real v3 profile receipts from every generic chat entry point: %j', (profile) => {
    const raw = { fact_id: 'profile-fact', write_status: 'saved', revision: 1, ...profile };
    const projected = receipt(raw);
    expect(projected).toBeUndefined();
    expect(chatEvent({ type: 'memory_receipt', ...raw })).toBeUndefined();
    const tool = event({ type: 'tool_result', name: 'profile_get', receipt: raw });
    expect(tool.type === 'tool_result' && tool.receipt).toBeUndefined();
    for (const result of [
      { schema_version: 'core3.0', answer: '公开', memory_receipts: [raw] },
      { schema: 'core4.0', text: '公开', receipts: [raw] },
    ]) {
      const final = event({ type: 'result', result });
      expect(final.type === 'final' && final.envelope.receipts).toEqual([]);
      expect(JSON.stringify(final)).not.toMatch(/1998-03-12|116\.4|solar_datetime/);
    }
  });

  it('keeps ordinary numeric facts visible instead of treating all dates and numbers as profile data', () => {
    for (const content of ['3', '每周锻炼3次', '面试在2026-10-21']) {
      const raw = {
        fact_id: 'ordinary-fact',
        write_status: 'saved',
        kind: 'preference',
        field: null,
        value: 3,
        content,
      };
      expect(receipt(raw)?.summary).toBe(content);
      expect(
        normalizeEnvelope({ schema_version: 'core3.0', answer: '公开', memory_receipts: [raw] })?.receipts[0].summary,
      ).toBe(content);
    }
  });

  it('projects only public core4 fields and removes private values from every visible card', () => {
    const projected = normalizeEnvelope({
      schema: 'core4.0',
      text: privateBirth,
      message_id: 'synthetic-message',
      receipts: [
        {
          fact_id: 'synthetic-fact',
          write_status: 'pending',
          summary: privateBirth,
          birth: { raw: 'PRIVATE_RAW' },
          undo_token: privateBirth,
        },
      ],
      asked: {
        question: privateBirth,
        options: ['公开选项', privateBirth, { label: privateBirth }],
        why: privateBirth,
        allow_free_text: true,
      },
      birth: { raw: 'PRIVATE_RAW' },
      raw_birth: 'PRIVATE_RAW',
      review: { text: 'PRIVATE_RAW' },
      professional_appendix: 'PRIVATE_RAW',
    });
    expect(projected?.answer).toBe(hiddenProfile);
    expect(projected?.question).toEqual({
      question: hiddenProfile,
      options: ['公开选项'],
      why: hiddenProfile,
      allow_free_text: true,
    });
    expect(projected?.receipts[0].summary).toBe(hiddenProfile);
    expect(JSON.stringify(projected)).not.toMatch(/PRIVATE|birth\.|undo_token/);
  });

  it('does not copy raw birth fields through core3 evidence, decision fields or clarification dependencies', () => {
    const projected = normalizeEnvelope({
      schema_version: 'core3.0',
      answer: '公开',
      professional_appendix: privateBirth,
      evidence: [
        { ref: 'fact:private', claim: privateBirth },
        { ref: privateBirth, claim: '公开' },
        { ref: 'fact:ordinary', claim: '面试在2026-10-21' },
      ],
      decision_options: [{ option: '核对', benefit: privateBirth, first_step: privateBirth }],
      meta: {
        interrupt: {
          id: 'clarify:synthetic',
          state_version: { facts: 3, 'birth.raw': 'PRIVATE_RAW', profile: { raw: 'PRIVATE_RAW' } },
          questions: [privateBirth, '其他安排？'],
        },
      },
    });
    expect(projected?.evidence).toEqual([{ ref: 'fact:ordinary', claim: '面试在2026-10-21' }]);
    expect(projected?.interrupt?.state_version).toEqual({ facts: 3 });
    expect(projected?.interrupt?.questions).toEqual([hiddenProfile, '其他安排？']);
    expect(projected?.decisions[0].benefit).toBe(hiddenProfile);
    expect(JSON.stringify(projected)).not.toMatch(/PRIVATE|birth\./);
  });

  it.each([
    '公开开头\nbirth.solar_datetime:\nSYNTHETIC_PRIVATE_BIRTH\n公开结尾',
    '{"birth": {\n"year": "SYNTHETIC_PRIVATE_BIRTH"\n}}',
    'birth_location: SYNTHETIC_PRIVATE_BIRTH',
    'raw_birth: SYNTHETIC_PRIVATE_BIRTH',
    '出生时刻：SYNTHETIC_PRIVATE_BIRTH',
    '出生地点=SYNTHETIC_PRIVATE_BIRTH',
  ])('hides multiline and alias birth values in public text: %s', (text) => {
    expect(publicChatText(text)).toBe(hiddenProfile);
    expect(publicChatText('面试在2026-10-21，先准备简历。')).toBe('面试在2026-10-21，先准备简历。');
    expect(publicChatText('出生时间是否确定？')).toBe('出生时间是否确定？');
  });

  it('redacts the full accumulated projection when a private key/value is split across chunks', () => {
    let state = initialStream();
    for (const text of ['公开\nbi', 'rth.solar_', 'datetime:\n', 'SYNTHETIC_PRIVATE_BIRTH', '\n后续内容']) {
      state = reduceChat(state, event({ type: 'text_delta', text }));
      expect(publicChatText(state.text)).not.toContain('SYNTHETIC_PRIVATE_BIRTH');
    }
    expect(publicChatText(state.text)).toBe(hiddenProfile);
    expect(state.text).toContain('SYNTHETIC_PRIVATE_BIRTH');
  });

  it('does not display private fields through statuses, tool summaries or error messages', () => {
    expect(event({ type: 'status', text: privateBirth })).toMatchObject({ text: hiddenProfile });
    expect(event({ type: 'tool_result', name: 'profile_get', summary: privateBirth })).toMatchObject({
      summary: hiddenProfile,
    });
    expect(event({ type: 'error', code: 'ERROR', message: privateBirth })).toMatchObject({ message: hiddenProfile });
    expect(chatEvent({ type: 'tool_call', name: privateBirth })).toBeUndefined();
    expect(chatEvent({ type: 'started', run_id: privateBirth })).toBeUndefined();
    expect(receipt({ fact_id: privateBirth, write_status: 'saved' })).toBeUndefined();
  });
});
