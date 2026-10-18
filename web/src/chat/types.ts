export type JsonObject = Record<string, unknown>;
export function object(value: unknown): JsonObject {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as JsonObject) : {};
}
export function string(value: unknown): string {
  return typeof value === 'string' ? value : '';
}
export function rows(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export type Receipt = {
  fact_id?: string;
  proposal_id?: string;
  write_status: string;
  summary: string;
  revision?: number;
  undo_token?: string;
};
export type Question = { question: string; options: string[]; allow_free_text: boolean; why: string };
export type Decision = {
  option: string;
  benefit: string;
  cost: string;
  risk: string;
  reversibility: string;
  first_step: string;
};
export type Envelope = {
  answer: string;
  professional_appendix: string;
  receipts: Receipt[];
  decisions: Decision[];
  evidence: { ref: string; claim: string }[];
  interrupt?: { id: string; state_version: JsonObject; questions: string[] };
};
export type ChatEvent =
  | { type: 'started'; run_id: string; thread_id?: string; message_id?: string }
  | { type: 'status'; text: string }
  | { type: 'tool_call' | 'tool_result'; name: string; summary: string; receipt?: Receipt }
  | { type: 'text_delta'; text: string }
  | { type: 'text_reset'; text: string; reason: 'revised' | 'resumed' }
  | { type: 'memory_receipt'; receipt: Receipt }
  | { type: 'ask_user'; question: Question }
  | { type: 'present_options'; options: Decision[] }
  | { type: 'final'; envelope: Envelope }
  | { type: 'error'; code: string; message: string; retryable: boolean };
export type StreamState = {
  runId: string;
  text: string;
  status: string;
  revised: boolean;
  complete: boolean;
  tools: { name: string; summary: string; done: boolean }[];
  receipts: Receipt[];
  question?: Question;
  decisions: Decision[];
  envelope?: Envelope;
  error?: string;
};
export const initialStream = (): StreamState => ({
  runId: '',
  text: '',
  status: '',
  revised: false,
  complete: false,
  tools: [],
  receipts: [],
  decisions: [],
});
export type ChatPayload = {
  request_id: string;
  message: string;
  session_id: string;
  case_ids: string[];
  images: string[];
  depth: 'fast' | 'standard';
  draw_id?: string;
  selection?: { date?: string; system?: string; systems?: string[]; focus?: string; key?: string };
};
export type PendingChat = {
  namespace: string;
  payload: ChatPayload;
  runId: string;
  restoreOnly?: boolean;
  resume?: {
    runId: string;
    interrupt_id: string;
    state_version: JsonObject;
    message_id: string;
  };
};
export type HistoryRow = {
  role: string;
  content: string;
  at: string;
  source: string;
  cursor: string;
  turn_id: string;
  run_id?: string;
  status?: string;
  meta?: unknown;
};
export type CompletedTurn = { requestId: string; runId: string; prompt: string; state: StreamState };
export type Run = { id: string; operation_id: string; status: string; result?: unknown; error?: string };
