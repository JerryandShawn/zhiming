import { chatEvent } from '../chat/events';
import { readSse } from '../chat/sse';
import type { ChatEvent } from '../chat/types';

export type DemoScenario = 'cards' | 'review' | 'error' | 'resumed';
export type DemoStep = { type: string; payload: Record<string, unknown>; reviewPending?: boolean; hold?: number };
const options = [
  {
    option: '先做一周小试验',
    benefit: '留出实际体验的空间',
    cost: '每天花二十分钟',
    risk: '进展可能比预想慢',
    reversibility: '随时可停',
    first_step: '写下最想验证的一件事',
  },
  {
    option: '先把信息问清楚',
    benefit: '减少信息缺口',
    cost: '需要等一次沟通',
    risk: '容易一直停在准备阶段',
    reversibility: '沟通后仍可换方向',
    first_step: '列三个具体问题',
  },
];
const question = {
  question: '你更想先理清哪一部分？',
  options: ['先做个小试验', '先把信息问清楚'],
  allow_free_text: true,
  why: '先从你最在意的地方开始，不替你做决定。',
};
const saved = {
  fact_id: 'local-preference',
  write_status: 'saved',
  summary: '偏好先看简短结论（合成示例）',
  revision: 1,
};
const pending = {
  proposal_id: 'local-proposal',
  write_status: 'pending_confirmation',
  category: 'health',
  summary: '希望跟进一项健康安排（合成示例）',
  revision: 1,
};
const text = '先把选择缩小到一个可验证的小步骤。下面两种走法各有代价，你可以按自己的节奏来。';

export function demoSteps(scenario: DemoScenario): DemoStep[] {
  const start: DemoStep[] = [
    {
      type: 'started',
      payload: { run_id: `local-${scenario}`, thread_id: 'local-thread', message_id: 'local-message' },
    },
    { type: 'status', payload: { text: '我先看看你刚才提到的情况。' } },
    { type: 'tool_call', payload: { name: 'memory_search', summary: '正在查看相关记忆' }, hold: 450 },
    { type: 'tool_result', payload: { name: 'memory_search', summary: '找到 2 条相关记忆' } },
  ];
  if (scenario === 'error')
    return [
      ...start.slice(0, 3),
      { type: 'text_delta', payload: { text: '已经理清的内容会保留。' } },
      {
        type: 'error',
        payload: { code: 'LOCAL_INTERRUPTED', message: '这次演示中途停下了，可以重试这一轮。', retryable: true },
      },
    ];
  if (scenario === 'resumed')
    return [
      ...start,
      { type: 'text_delta', payload: { text: '旧片段' } },
      { type: 'text_reset', payload: { text: '从已确认的片段继续，原来的重复文字已替换。', reason: 'resumed' } },
      {
        type: 'final',
        payload: { envelope: { schema: 'core3.0', answer: '从已确认的片段继续，原来的重复文字已替换。' } },
      },
    ];
  const content: DemoStep[] =
    scenario === 'review'
      ? [
          {
            type: 'text_delta',
            payload: { text: '第一版：现在就把所有安排定下来。' },
            reviewPending: true,
            hold: 1600,
          },
          { type: 'text_reset', payload: { text, reason: 'revised' }, reviewPending: false },
        ]
      : [
          { type: 'text_delta', payload: { text: text.slice(0, 20) } },
          { type: 'text_delta', payload: { text: text.slice(20) } },
        ];
  return [
    ...start,
    ...content,
    { type: 'memory_receipt', payload: saved },
    { type: 'memory_receipt', payload: pending },
    { type: 'present_options', payload: { options } },
    { type: 'ask_user', payload: question },
    {
      type: 'final',
      payload: {
        envelope: { schema: 'core4.0', message_id: 'local-message', text, receipts: [saved, pending], asked: question },
      },
    },
  ];
}

// Exercise the same byte decoder and public event projection as a real stream.
export async function playDemo(
  scenario: DemoScenario,
  accept: (event: ChatEvent, pending?: boolean) => void,
  signal: AbortSignal,
  delay = 100,
) {
  for (const [index, step] of demoSteps(scenario).entries()) {
    signal.throwIfAborted();
    const frame = `id: ${index + 1}\nevent: ${step.type}\ndata: ${JSON.stringify(step.payload)}\n\n`;
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
        if (event && !signal.aborted) accept(event, step.reviewPending);
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
