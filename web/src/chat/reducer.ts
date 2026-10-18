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
// Local view state only: the current wire protocol has no frozen review phase.
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
      };
    case 'status':
      return { ...state, status: event.text };
    case 'text_delta':
      return { ...state, text: state.text + event.text };
    case 'text_reset':
      return { ...state, text: event.text, revised: event.reason === 'revised' || state.revised };
    case 'tool_call':
      return { ...state, tools: [...state.tools, { name: event.name, summary: event.summary, done: false }] };
    case 'tool_result': {
      let index = -1;
      for (let item = state.tools.length - 1; item >= 0; item--) {
        if (state.tools[item].name === event.name && !state.tools[item].done) {
          index = item;
          break;
        }
      }
      const tools = [...state.tools];
      if (index >= 0) tools[index] = { ...tools[index], summary: event.summary, done: true };
      else tools.push({ name: event.name, summary: event.summary, done: true });
      return { ...state, tools, receipts: mergeReceipts(state.receipts, event.receipt ? [event.receipt] : []) };
    }
    case 'memory_receipt':
      return { ...state, receipts: mergeReceipts(state.receipts, [event.receipt]) };
    case 'ask_user':
      return { ...state, question: event.question, answered: undefined };
    case 'present_options':
      return { ...state, decisions: event.options };
    case 'final':
      return {
        ...state,
        text: event.envelope.schema === 'core4.0' ? event.envelope.answer : event.envelope.answer || state.text,
        envelope: event.envelope,
        complete: true,
        status: '',
        reviewPending: false,
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
