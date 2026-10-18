import { object, rows, string, type ChatEvent, type Decision, type Envelope, type Receipt } from './types';
import { hasBirthFields, publicChatText } from './publicProjection';

export function receipt(value: unknown): Receipt | undefined {
  const data = object(value),
    fact = string(data.fact_id) || string(data.id),
    proposal = string(data.proposal_id);
  if ((!fact && !proposal) || !string(data.write_status)) return;
  return {
    fact_id: fact || undefined,
    proposal_id: proposal || undefined,
    write_status: string(data.write_status),
    summary: publicChatText(string(data.summary) || string(data.content)),
    revision: Number.isInteger(data.revision) ? (data.revision as number) : undefined,
    undo_token: string(data.undo_token) || undefined,
  };
}
export function decisions(value: unknown): Decision[] {
  return rows(value)
    .map(object)
    .filter((item) => string(item.option) || string(item.title))
    .map((item) => ({
      option: string(item.option) || string(item.title),
      benefit: string(item.benefit),
      cost: string(item.cost),
      risk: string(item.risk),
      reversibility: string(item.reversibility),
      first_step: string(item.first_step),
    }));
}
export function envelope(value: unknown): Envelope {
  const data = object(value),
    meta = object(data.meta),
    interrupt = object(meta.interrupt);
  return {
    answer: publicChatText(string(data.answer) || string(data.plain_summary)),
    professional_appendix: publicChatText(string(data.professional_appendix)),
    receipts: rows(data.memory_receipts ?? meta.saved_receipts)
      .map(receipt)
      .filter((item) => item !== undefined),
    decisions: decisions(data.decision_options),
    evidence: rows(data.evidence)
      .map(object)
      .filter((item) => !hasBirthFields(string(item.claim)) && !hasBirthFields(string(item.ref)))
      .map((item) => ({ ref: string(item.ref), claim: string(item.claim) })),
    ...(string(interrupt.id)
      ? {
          interrupt: {
            id: string(interrupt.id),
            state_version: object(interrupt.state_version),
            questions: rows(interrupt.questions).filter((item) => typeof item === 'string'),
          },
        }
      : {}),
  };
}

// This is a client projection of the blueprint, not the missing P4 server schema.
export function chatEvent(value: unknown, namedType = ''): ChatEvent | undefined {
  const data = object(value),
    type = string(data.type) || namedType;
  switch (type) {
    case 'started':
      return string(data.run_id)
        ? { type, run_id: string(data.run_id), thread_id: string(data.thread_id), message_id: string(data.message_id) }
        : undefined;
    case 'status':
      return { type, text: string(data.text) };
    case 'tool_call':
    case 'tool_result':
      return string(data.name)
        ? {
            type,
            name: string(data.name),
            summary: string(data.summary),
            receipt: receipt(data.receipt),
          }
        : undefined;
    case 'text_delta':
      return typeof data.text === 'string' ? { type, text: data.text } : undefined;
    case 'text_reset':
      return typeof data.text === 'string' && ['revised', 'resumed'].includes(string(data.reason))
        ? {
            type,
            text: data.text,
            reason: data.reason as 'revised' | 'resumed',
          }
        : undefined;
    case 'memory_receipt': {
      const item = receipt(data);
      return item ? { type, receipt: item } : undefined;
    }
    case 'ask_user':
      return string(data.question)
        ? {
            type,
            question: {
              question: string(data.question),
              options: rows(data.options)
                .map((item) => (typeof item === 'string' ? item : string(object(item).label)))
                .filter(Boolean),
              allow_free_text: data.allow_free_text === true,
              why: string(data.why),
            },
          }
        : undefined;
    case 'present_options':
      return { type, options: decisions(data.options) };
    case 'final':
      return Object.keys(object(data.envelope)).length ? { type, envelope: envelope(data.envelope) } : undefined;
    case 'result':
      return Object.keys(object(data.result)).length ? { type: 'final', envelope: envelope(data.result) } : undefined;
    case 'error':
      return {
        type,
        code: string(data.code),
        message: string(data.message) || '本轮没有完成',
        retryable: data.retryable === true,
      };
    default:
      return undefined;
  }
}
