import { object, rows, string, type Decision, type Envelope, type Question, type Receipt, type Review } from './types';
import { hasBirthFields, publicChatText } from './publicProjection';
import { isWireOptionsV1, isWireReviewV1 } from './wireV1';

export function receipt(value: unknown): Receipt | undefined {
  const data = object(value);
  const fact = string(data.fact_id) || string(data.id),
    proposal = string(data.proposal_id);
  if (
    (!fact && !proposal) ||
    !string(data.write_status) ||
    hasBirthFields(fact) ||
    hasBirthFields(proposal) ||
    hasBirthFields(string(data.write_status))
  )
    return;
  const category = string(data.category).trim();
  const field = string(data.field).trim().toLowerCase();
  const privateProfile =
    field === 'birth' || field.startsWith('birth.') || string(data.kind).trim().toLowerCase() === 'profile';
  // Profile confirmation and withdrawal belong to their dedicated UI. A generic
  // chat memory card must neither reveal these values nor PATCH them as memories.
  if (privateProfile) return;
  return {
    fact_id: fact || undefined,
    proposal_id: proposal || undefined,
    write_status: string(data.write_status),
    summary: publicChatText(string(data.summary) || string(data.content)),
    ...(category && category.length <= 120 && !/[\r\n]/.test(category) && !hasBirthFields(category)
      ? { category }
      : {}),
    revision: Number.isInteger(data.revision) && Number(data.revision) >= 0 ? Number(data.revision) : undefined,
    undo_token:
      string(data.undo_token) && !hasBirthFields(string(data.undo_token)) ? string(data.undo_token) : undefined,
    ...(typeof data.sensitive === 'boolean' ? { sensitive: data.sensitive } : {}),
  };
}

export function question(value: unknown): Question | undefined {
  const data = object(value);
  if (!string(data.question).trim()) return;
  const items = rows(data.options)
    .map((item) => ({
      label: typeof item === 'string' ? item : string(object(item).label),
      id: typeof item === 'string' ? '' : string(object(item).id),
    }))
    .filter((item) => item.label.trim() && !hasBirthFields(item.label));
  const askId = string(data.ask_id);
  const hasStableIds =
    Boolean(askId) && !hasBirthFields(askId) && items.every((item) => item.id && !hasBirthFields(item.id));
  return {
    question: publicChatText(string(data.question)),
    options: items.map((item) => publicChatText(item.label)),
    allow_free_text: data.allow_free_text === true,
    why: publicChatText(string(data.why)),
    ...(hasStableIds ? { askId, optionIds: items.map((item) => item.id) } : {}),
    ...(typeof data.multi === 'boolean' ? { multi: data.multi } : {}),
  };
}

export function decisions(value: unknown): Decision[] {
  return rows(value)
    .map(object)
    .filter((item) => string(item.option) || string(item.title))
    .map((item) => ({
      option: publicChatText(string(item.option) || string(item.title)),
      benefit: publicChatText(string(item.benefit)),
      cost: publicChatText(string(item.cost)),
      risk: publicChatText(string(item.risk)),
      reversibility: publicChatText(string(item.reversibility)),
      first_step: publicChatText(string(item.first_step)),
      ...(string(item.id) && !hasBirthFields(string(item.id)) ? { id: string(item.id) } : {}),
      ...(Array.isArray(item.unknowns)
        ? {
            unknowns: rows(item.unknowns)
              .filter((entry): entry is string => typeof entry === 'string')
              .map(publicChatText),
          }
        : {}),
    }));
}

export function review(value: unknown): Review | undefined {
  if (!isWireReviewV1(value)) return;
  return {
    state: value.state,
    reasons: value.reasons
      .filter((reason) => !hasBirthFields(reason.code))
      .map((reason) => ({ code: reason.code, severity: reason.severity })),
    ...(value.revision_id && !hasBirthFields(value.revision_id) ? { revisionId: value.revision_id } : {}),
  };
}

function emptyEnvelope(): Envelope {
  return { answer: '', professional_appendix: '', receipts: [], decisions: [], evidence: [] };
}

function version(data: Record<string, unknown>): 'core3.0' | 'core4.0' | 'legacy' | undefined {
  const markers = ['schema', 'schema_version'].filter((key) => Object.hasOwn(data, key)).map((key) => data[key]);
  if (!markers.length) return 'legacy';
  if (!markers.every((marker) => marker === markers[0])) return;
  return markers[0] === 'core3.0' || markers[0] === 'core4.0' ? markers[0] : undefined;
}

/** One public projection for persisted results, history and both stream formats. */
export function normalizeEnvelope(value: unknown): Envelope | undefined {
  const data = object(value),
    schema = version(data);
  if (!schema) return;
  if (schema === 'core4.0') {
    if (typeof data.text !== 'string') return;
    const asked = question(data.asked);
    const options = isWireOptionsV1(data.options) ? decisions(data.options.options) : [];
    const checked = review(data.review);
    return {
      ...emptyEnvelope(),
      schema,
      answer: publicChatText(data.text),
      ...(string(data.message_id) && !hasBirthFields(string(data.message_id))
        ? { messageId: string(data.message_id) }
        : {}),
      receipts: rows(data.receipts)
        .map(receipt)
        .filter((item) => item !== undefined),
      ...(asked ? { question: asked } : {}),
      decisions: options,
      ...(checked ? { review: checked } : {}),
    };
  }
  if (typeof data.answer !== 'string' && typeof data.plain_summary !== 'string') return;
  const meta = object(data.meta),
    interrupt = object(meta.interrupt);
  const versions = Object.fromEntries(
    Object.entries(object(interrupt.state_version)).filter(
      ([key, value]) => !hasBirthFields(key) && Number.isInteger(value) && Number(value) >= 0,
    ),
  );
  return {
    ...(schema === 'core3.0' ? { schema } : {}),
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
    ...(string(interrupt.id) && !hasBirthFields(string(interrupt.id))
      ? {
          interrupt: {
            id: string(interrupt.id),
            state_version: versions,
            questions: rows(interrupt.questions)
              .filter((item): item is string => typeof item === 'string')
              .map(publicChatText),
          },
        }
      : {}),
  };
}

/** Legacy history callers need an empty projection when metadata is absent. */
export function envelope(value: unknown): Envelope {
  return normalizeEnvelope(value) ?? emptyEnvelope();
}
