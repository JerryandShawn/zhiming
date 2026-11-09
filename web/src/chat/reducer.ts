import type { ChatEvent, Receipt, StreamState } from './types';

function mergeReceipts(current: Receipt[], added: Receipt[]): Receipt[] {
  const result: Receipt[] = [];
  for (const item of [...current, ...added]) {
    const matches = (known: Receipt) =>
      Boolean(
        (item.fact_id && known.fact_id === item.fact_id) ||
        (item.proposal_id && known.proposal_id === item.proposal_id),
      );
    const index = result.findIndex(matches);
    if (index < 0) result.push(item);
    else {
      const known = result.filter(matches);
      result[index] = {
        ...item,
        fact_id: item.fact_id || known.find((receipt) => receipt.fact_id)?.fact_id,
        proposal_id: item.proposal_id || known.find((receipt) => receipt.proposal_id)?.proposal_id,
      };
      for (let duplicate = result.length - 1; duplicate > index; duplicate--)
        if (matches(result[duplicate])) result.splice(duplicate, 1);
    }
  }
  return result;
}
/** @deprecated Compatibility for old local callers; wire review/phase drives new streams. */
export function withReviewPending(state: StreamState, pending: boolean): StreamState {
  return { ...state, reviewPending: !state.complete && !state.error && pending };
}
export function reduceChat(state: StreamState, event: ChatEvent): StreamState {
  switch (event.type) {
    case 'started':
      return {
        ...state,
        runId: event.run_id,
        threadId: event.thread_id || state.threadId,
        messageId: event.message_id || state.messageId,
        ...(event.area_id ? { areaId: event.area_id } : {}),
        ...(event.topic_id ? { topicId: event.topic_id } : {}),
        ...(event.incognito !== undefined ? { incognito: event.incognito } : {}),
      };
    case 'status':
      return {
        ...state,
        status: event.text,
        ...(event.phase
          ? {
              phase: event.phase,
              reviewPending:
                !state.complete && !state.error && (event.phase === 'reviewing' || state.review?.state === 'pending'),
            }
          : {}),
      };
    case 'text_delta':
      return { ...state, text: state.text + event.text };
    case 'text_reset':
      return {
        ...state,
        text: event.text,
        revised: event.reason === 'revised' || state.revised,
        ...(event.revision_id ? { revisionId: event.revision_id } : {}),
      };
    case 'tool_call':
      if (event.call_id && state.tools.some((tool) => tool.callId === event.call_id)) return state;
      return {
        ...state,
        tools: [
          ...state.tools,
          {
            name: event.name,
            summary: event.summary,
            done: false,
            ...(event.call_id ? { callId: event.call_id } : {}),
          },
        ],
      };
    case 'tool_result': {
      let index = -1;
      for (let item = state.tools.length - 1; item >= 0; item--) {
        if (
          event.call_id
            ? state.tools[item].callId === event.call_id
            : state.tools[item].name === event.name && !state.tools[item].done
        ) {
          index = item;
          break;
        }
      }
      const tools = [...state.tools];
      const completed = {
        name: event.name,
        summary: event.summary,
        done: true,
        ...(event.call_id ? { callId: event.call_id } : {}),
        ...(event.ok !== undefined ? { ok: event.ok } : {}),
      };
      if (index >= 0) tools[index] = { ...tools[index], ...completed };
      else tools.push(completed);
      return { ...state, tools, receipts: mergeReceipts(state.receipts, event.receipt ? [event.receipt] : []) };
    }
    case 'memory_receipt':
      return { ...state, receipts: mergeReceipts(state.receipts, [event.receipt]) };
    case 'ask_user':
      return { ...state, question: event.question, answered: undefined };
    case 'present_options':
      return {
        ...state,
        decisions: event.options,
        ...(event.optionsId ? { optionsId: event.optionsId } : {}),
        ...(event.prompt !== undefined ? { optionsPrompt: event.prompt } : {}),
      };
    case 'review':
      return {
        ...state,
        review: event.review,
        reviewPending: !state.complete && !state.error && event.review.state === 'pending',
        revised: event.review.state === 'revised' || state.revised,
        ...(event.review.revisionId ? { revisionId: event.review.revisionId } : {}),
        ...(event.review.state !== 'pending' && state.phase === 'reviewing' ? { phase: undefined, status: '' } : {}),
      };
    case 'final':
      return {
        ...state,
        text: event.envelope.schema === 'core4.0' ? event.envelope.answer : event.envelope.answer || state.text,
        envelope: event.envelope,
        complete: true,
        status: '',
        reviewPending: false,
        ...(event.envelope.review
          ? {
              review: event.envelope.review,
              revised: event.envelope.review.state === 'revised' || state.revised,
              ...(event.envelope.review.revisionId ? { revisionId: event.envelope.review.revisionId } : {}),
            }
          : {}),
        messageId: event.envelope.messageId || event.message_id || state.messageId,
        question: event.envelope.question ?? state.question,
        error: undefined,
        errorCode: undefined,
        retryable: undefined,
        receipts: mergeReceipts(state.receipts, event.envelope.receipts),
        decisions: event.envelope.decisions.length ? event.envelope.decisions : state.decisions,
      };
    case 'error':
      return {
        ...state,
        status: '',
        error: event.message,
        errorCode: event.code,
        retryable: event.retryable,
        reviewPending: false,
      };
  }
}
