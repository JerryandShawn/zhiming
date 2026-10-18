import type { ChatEvent, Receipt, StreamState } from './types';

function mergeReceipts(current: Receipt[], added: Receipt[]): Receipt[] {
  const result = new Map(current.map((item) => [item.fact_id || item.proposal_id, item]));
  for (const item of added) result.set(item.fact_id || item.proposal_id, item);
  return [...result.values()];
}
export function reduceChat(state: StreamState, event: ChatEvent): StreamState {
  switch (event.type) {
    case 'started':
      return { ...state, runId: event.run_id };
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
      return { ...state, question: event.question };
    case 'present_options':
      return { ...state, decisions: event.options };
    case 'final':
      return {
        ...state,
        text: event.envelope.answer || state.text,
        envelope: event.envelope,
        complete: true,
        status: '',
        receipts: mergeReceipts(state.receipts, event.envelope.receipts),
        decisions: event.envelope.decisions.length ? event.envelope.decisions : state.decisions,
      };
    case 'error':
      return { ...state, status: '', error: event.message };
  }
}
