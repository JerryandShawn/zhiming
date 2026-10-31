import { parseRunEventV1, type RunEventV1 } from '../contracts/runEvents';
import { identifier } from '../chat/wireChecksV1';

export type LegacyRunElements = {
  answer: HTMLElement;
  status: HTMLElement;
  review: HTMLElement;
  interrupted: HTMLElement;
};
export type LegacyApplyResult = 'applied' | 'duplicate' | 'invalid' | 'foreign' | 'gap' | 'stale' | 'terminal';

/** An explicitly mounted view only. It never queries the page, fetches, or binds the old sender. */
export function createLegacyRunView(options: { runId: string; elements: LegacyRunElements; isCurrent: () => boolean }) {
  if (!identifier(options.runId)) throw new Error('运行标识尚未核对。');
  const { elements, isCurrent, runId } = options;
  let seq = 0,
    text = '',
    pending = false,
    revised = false,
    terminal = false,
    disposed = false;
  const reviewLabel = () => {
    elements.review.textContent = pending ? '复核中' : revised ? '已修订' : '';
    elements.review.hidden = !elements.review.textContent;
  };
  function applyEvent(event: RunEventV1) {
    switch (event.type) {
      case 'text_delta':
        text += event.text;
        elements.answer.textContent = text;
        break;
      case 'text_reset':
        text = event.text;
        elements.answer.textContent = text;
        if (event.reason === 'revised') revised = true;
        reviewLabel();
        break;
      case 'status':
        elements.status.textContent = event.text;
        break;
      case 'tool_call':
      case 'tool_result':
        elements.status.textContent = event.summary;
        break;
      case 'review':
        pending = event.state === 'pending';
        if (event.state === 'revised') revised = true;
        reviewLabel();
        break;
      case 'error':
        terminal = true;
        pending = false;
        if (event.code === 'RUN_CANCELLED') {
          elements.interrupted.textContent = '已中断';
          elements.interrupted.hidden = false;
          elements.status.textContent = '';
        } else elements.status.textContent = '本轮尚未完成，已显示的内容保留。';
        reviewLabel();
        break;
      case 'final':
        text = event.envelope.text;
        elements.answer.textContent = text;
        pending = false;
        if (event.envelope.review.state === 'revised') revised = true;
        elements.status.textContent = '';
        terminal = true;
        reviewLabel();
        break;
    }
  }
  return {
    accept(value: unknown, eventName: string): LegacyApplyResult {
      if (disposed || !isCurrent()) return 'stale';
      const event = parseRunEventV1(value, eventName);
      if (!event) return 'invalid';
      if (event.run_id !== runId) return 'foreign';
      if (event.seq <= seq) return 'duplicate';
      if (terminal) return 'terminal';
      if (event.seq !== seq + 1) return 'gap';
      applyEvent(event);
      seq = event.seq;
      return 'applied';
    },
    snapshot: () => ({ runId, lastEventId: seq ? String(seq) : undefined, text, terminal }),
    dispose() {
      disposed = true;
    },
  };
}
