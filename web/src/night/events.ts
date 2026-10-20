import { chatEvent } from '../chat/events';
import { readSse } from '../chat/sse';
import type { ChatEvent } from '../chat/types';
import { beijingTimestamp } from '../time/beijing';

export type DemoScenario = 'cards' | 'review' | 'error' | 'resumed' | 'streaming' | 'queued';
export type DemoStep = { type: string; payload: Record<string, unknown>; hold?: number };
const options = {
  options_id: 'local-options',
  prompt: '两种走法，可以先比较再决定。',
  options: [
    {
      id: 'trial',
      title: '先做一周小试验',
      benefit: '留出实际体验的空间',
      cost: '每天花二十分钟',
      risk: '进展可能比预想慢',
      reversibility: 'easy',
      first_step: '写下最想验证的一件事',
      unknowns: [],
    },
    {
      id: 'clarify',
      title: '先把信息问清楚',
      benefit: '减少信息缺口',
      cost: '需要等一次沟通',
      risk: '',
      reversibility: 'partial',
      first_step: '列三个具体问题',
      unknowns: ['risk'],
    },
  ],
};
const question = {
  ask_id: 'local-ask',
  question: '你更想先理清哪一部分？',
  options: [
    { id: 'trial', label: '先做个小试验' },
    { id: 'clarify', label: '先把信息问清楚' },
  ],
  allow_free_text: true,
  multi: false,
  why: '先从你最在意的地方开始，不替你做决定。',
};
const saved = {
  fact_id: 'local-preference',
  write_status: 'saved',
  sensitive: false,
  summary: '偏好先看简短结论（合成示例）',
  undo_token: 'local-undo-token',
};
const pending = {
  proposal_id: 'local-proposal',
  write_status: 'pending_confirm',
  sensitive: true,
  summary: '希望跟进一项健康安排（合成示例）',
};
const text = '先把选择缩小到一个可验证的小步骤。下面两种走法各有代价，你可以按自己的节奏来。';

function finalStep(answer: string, revised = false, cards = true): DemoStep {
  return {
    type: 'final',
    payload: {
      message_id: 'local-message',
      envelope: {
        schema: 'core4.0',
        message_id: 'local-message',
        text: answer,
        receipts: cards
          ? [
              { fact_id: saved.fact_id, write_status: saved.write_status },
              { proposal_id: pending.proposal_id, write_status: pending.write_status },
            ]
          : [],
        used_fact_ids: [],
        used_claim_ids: [],
        asked: cards ? question : null,
        options: cards ? options : null,
        review: {
          state: revised ? 'revised' : 'passed',
          reasons: [],
          ...(revised ? { revision_id: 'local-revision-1' } : {}),
        },
        usage: {},
      },
    },
  };
}

/** Emit frozen server wire shapes; view state is never smuggled in as an event extension. */
export function demoSteps(scenario: DemoScenario): DemoStep[] {
  const start: DemoStep[] = [
    {
      type: 'started',
      payload: {
        thread_id: 'local-thread',
        message_id: 'local-message',
        area_id: 'daily',
        topic_id: 'local-topic',
        incognito: false,
      },
    },
    { type: 'status', payload: { text: '我先看看你刚才提到的情况。', phase: 'thinking' } },
    {
      type: 'tool_call',
      payload: { call_id: 'local-memory-1', name: 'memory_search', summary: '正在查看相关记忆' },
      hold: 450,
    },
    {
      type: 'tool_result',
      payload: { call_id: 'local-memory-1', name: 'memory_search', ok: true, summary: '找到 2 条相关记忆' },
    },
    { type: 'status', payload: { text: '我把要点理一理。', phase: 'writing' } },
  ];
  if (scenario === 'streaming' || scenario === 'queued') {
    const parts =
      scenario === 'streaming'
        ? [
            '我先把这段话慢慢说完。',
            '你想到新的情况，',
            '可以随时写在下面。',
            '新的补充会先排队，',
            '等这一段完成后，',
            '再按收到的顺序继续。',
            '排队时仍能修改下一条草稿，',
            '也能取消其中一条。',
            '停止后不会擅自继续，',
            '其余补充会保留在列表里。',
            '这是本机合成演示，',
            '没有连接模型。',
          ]
        : ['这条补充已接到当前对话后面。', '这里只演示接收与顺序处理，未连接模型。'];
    return [
      start[0],
      { type: 'status', payload: { text: '本地演示正在逐段展开。', phase: 'writing' } },
      ...parts.map((part) => ({
        type: 'text_delta',
        payload: { text: part },
        hold: scenario === 'streaming' ? 500 : 350,
      })),
      { type: 'review', payload: { state: 'passed', reasons: [] } },
      finalStep(parts.join(''), false, false),
    ];
  }
  if (scenario === 'error')
    return [
      ...start.slice(0, 3),
      { type: 'text_delta', payload: { text: '已经理清的内容会保留。' } },
      {
        type: 'error',
        payload: { code: 'LOCAL_INTERRUPTED', message: '这次演示中途停下了，可以重试这一轮。', retryable: true },
      },
    ];
  if (scenario === 'resumed') {
    const restored = '从已确认的片段继续，原来的重复文字已替换。';
    return [
      ...start,
      { type: 'text_delta', payload: { text: '旧片段' } },
      { type: 'text_reset', payload: { text: restored, reason: 'resumed', revision_id: 'local-restored-1' } },
      finalStep(restored, false, false),
    ];
  }
  const content: DemoStep[] =
    scenario === 'review'
      ? [
          { type: 'text_delta', payload: { text: '第一版：现在就把所有安排定下来。' } },
          { type: 'review', payload: { state: 'pending', reasons: [] }, hold: 1600 },
          { type: 'text_reset', payload: { text, reason: 'revised', revision_id: 'local-revision-1' } },
          {
            type: 'review',
            payload: {
              state: 'revised',
              reasons: [{ code: 'generic_barnum', severity: 2 }],
              revision_id: 'local-revision-1',
            },
          },
        ]
      : [
          { type: 'text_delta', payload: { text: text.slice(0, 20) } },
          { type: 'text_delta', payload: { text: text.slice(20) } },
          { type: 'review', payload: { state: 'passed', reasons: [] } },
        ];
  return [
    ...start,
    ...content,
    { type: 'memory_receipt', payload: saved },
    { type: 'memory_receipt', payload: pending },
    { type: 'present_options', payload: options },
    { type: 'ask_user', payload: question },
    finalStep(text, scenario === 'review'),
  ];
}

export async function playDemo(
  scenario: DemoScenario,
  accept: (event: ChatEvent) => void,
  signal: AbortSignal,
  delay = 100,
  context: { runId?: string; now?: () => Date } = {},
) {
  for (const [index, step] of demoSteps(scenario).entries()) {
    signal.throwIfAborted();
    const payload = {
      ...step.payload,
      v: 1,
      run_id: context.runId || 'local-' + scenario,
      seq: index + 1,
      ts: beijingTimestamp(context.now?.() ?? new Date()),
    };
    const frame =
      ': ping\n\nid: ' + (index + 1) + '\nevent: ' + step.type + '\ndata: ' + JSON.stringify(payload) + '\n\n';
    const bytes = new TextEncoder().encode(frame);
    const response = new Response(
      new ReadableStream<Uint8Array>({
        start(controller) {
          const split = Math.floor(bytes.length / 2);
          controller.enqueue(bytes.slice(0, split));
          controller.enqueue(bytes.slice(split));
          controller.close();
        },
      }),
    );
    await readSse(
      response,
      (raw) => {
        const event = chatEvent(JSON.parse(raw.data) as unknown, raw.event);
        if (event && !signal.aborted) accept(event);
      },
      signal,
    );
    if (delay)
      await new Promise<void>((resolve, reject) => {
        const abort = () => {
          clearTimeout(timer);
          reject(new DOMException('已停止本地演示', 'AbortError'));
        };
        const timer = setTimeout(() => {
          signal.removeEventListener('abort', abort);
          resolve();
        }, step.hold ?? delay);
        signal.addEventListener('abort', abort, { once: true });
      });
  }
}
