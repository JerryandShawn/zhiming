import { object, string, type ChatEvent } from './types';
import { decisions, normalizeEnvelope, question, receipt } from './envelopes';
import { hasBirthFields, publicChatText } from './publicProjection';
export { decisions, envelope, normalizeEnvelope, receipt } from './envelopes';

// This is a client projection of the blueprint, not the missing P4 server schema.
export function chatEvent(value: unknown, namedType = ''): ChatEvent | undefined {
  const data = object(value),
    type = string(data.type) || namedType;
  switch (type) {
    case 'started':
      return string(data.run_id) && !hasBirthFields(string(data.run_id))
        ? {
            type,
            run_id: string(data.run_id),
            thread_id: publicId(data.thread_id),
            message_id: publicId(data.message_id),
          }
        : undefined;
    case 'status':
      return { type, text: publicChatText(string(data.text)) };
    case 'tool_call':
    case 'tool_result':
      return string(data.name) && !hasBirthFields(string(data.name))
        ? {
            type,
            name: string(data.name),
            summary: publicChatText(string(data.summary)),
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
    case 'ask_user': {
      const asked = question(data);
      return asked ? { type, question: asked } : undefined;
    }
    case 'present_options':
      return { type, options: decisions(data.options) };
    case 'final':
    case 'result': {
      const result = normalizeEnvelope(type === 'final' ? data.envelope : data.result);
      return result
        ? {
            type: 'final',
            envelope: result,
            ...(publicId(data.message_id) ? { message_id: publicId(data.message_id) } : {}),
          }
        : undefined;
    }
    case 'error':
      return {
        type,
        code: publicId(data.code),
        message: publicChatText(string(data.message)) || '本轮没有完成',
        retryable: data.retryable === true,
      };
    default:
      return undefined;
  }
}

function publicId(value: unknown): string {
  const id = string(value);
  return hasBirthFields(id) ? '' : id;
}
