import { object, string, type ChatEvent, type Review } from './types';
import { decisions, normalizeEnvelope, question, receipt } from './envelopes';
import { hasBirthFields, publicChatText } from './publicProjection';
import { parseWireEventV1, type WireEventV1, type WireReviewV1 } from './wireV1';
export { decisions, envelope, normalizeEnvelope, receipt } from './envelopes';

export function chatEvent(value: unknown, namedType = ''): ChatEvent | undefined {
  const data = object(value);
  if (Object.hasOwn(data, 'v')) {
    const wire = parseWireEventV1(data, namedType);
    const event = wire && projectWire(wire);
    return event ? { ...event, v: 1, run_id: wire!.run_id, seq: wire!.seq, ts: wire!.ts } : undefined;
  }
  return legacyEvent(data, namedType);
}

// Persisted v3 results and old unversioned streams retain their separate read path.
function legacyEvent(data: Record<string, unknown>, namedType: string): ChatEvent | undefined {
  const type = string(data.type) || namedType;
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

function projectReview(value: WireReviewV1): Review {
  return {
    state: value.state,
    reasons: value.reasons.filter((reason) => Boolean(publicId(reason.code))),
    ...(publicId(value.revision_id) ? { revisionId: value.revision_id } : {}),
  };
}

function projectWire(wire: WireEventV1): ChatEvent | undefined {
  if (!publicId(wire.run_id)) return;
  switch (wire.type) {
    case 'started':
      if (!publicId(wire.thread_id) || !publicId(wire.message_id)) return;
      return {
        type: wire.type,
        run_id: wire.run_id,
        thread_id: wire.thread_id,
        message_id: wire.message_id,
        ...(publicId(wire.area_id) ? { area_id: wire.area_id } : {}),
        ...(publicId(wire.topic_id) ? { topic_id: wire.topic_id } : {}),
        incognito: wire.incognito,
      };
    case 'status':
      return { type: wire.type, text: publicChatText(wire.text), phase: wire.phase };
    case 'tool_call':
    case 'tool_result':
      if (!publicId(wire.call_id) || !publicId(wire.name)) return;
      return {
        type: wire.type,
        call_id: wire.call_id,
        name: wire.name,
        summary: publicChatText(wire.summary),
        ...(wire.type === 'tool_result' ? { ok: wire.ok, receipt: receipt(wire.receipt) } : {}),
      };
    case 'text_delta':
      return { type: wire.type, text: wire.text };
    case 'text_reset':
      return {
        type: wire.type,
        text: wire.text,
        reason: wire.reason,
        ...(publicId(wire.revision_id) ? { revision_id: wire.revision_id } : {}),
      };
    case 'memory_receipt': {
      const item = receipt(wire);
      return item ? { type: wire.type, receipt: { ...item, sensitive: wire.sensitive } } : undefined;
    }
    case 'ask_user': {
      if (!publicId(wire.ask_id)) return;
      const options = wire.options.filter((item) => publicId(item.id) && !hasBirthFields(item.label));
      return {
        type: wire.type,
        question: {
          askId: wire.ask_id,
          question: publicChatText(wire.question),
          options: options.map((item) => item.label),
          optionIds: options.map((item) => item.id),
          allow_free_text: wire.allow_free_text,
          multi: wire.multi,
          why: publicChatText(wire.why),
        },
      };
    }
    case 'present_options':
      if (!publicId(wire.options_id) || wire.options.some((item) => !publicId(item.id))) return;
      return {
        type: wire.type,
        optionsId: wire.options_id,
        ...(wire.prompt !== undefined ? { prompt: publicChatText(wire.prompt) } : {}),
        options: wire.options.map((item) => ({
          id: item.id,
          option: publicChatText(item.title),
          benefit: publicChatText(item.benefit),
          cost: publicChatText(item.cost),
          risk: publicChatText(item.risk),
          reversibility: item.reversibility,
          first_step: publicChatText(item.first_step),
          unknowns: item.unknowns.map(publicChatText),
        })),
      };
    case 'review':
      return { type: wire.type, review: projectReview(wire) };
    case 'final': {
      if (!publicId(wire.message_id)) return;
      const result = normalizeEnvelope(wire.envelope);
      return result ? { type: wire.type, envelope: result, message_id: wire.message_id } : undefined;
    }
    case 'error':
      return {
        type: wire.type,
        code: publicId(wire.code),
        message: publicChatText(wire.message) || '本轮没有完成',
        retryable: wire.retryable,
      };
  }
}

function publicId(value: unknown): string {
  const id = string(value);
  return hasBirthFields(id) ? '' : id;
}
