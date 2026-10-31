import type { ThreadAcceptance } from '../threads/contracts';

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
  category?: string;
  revision?: number;
  undo_token?: string;
  sensitive?: boolean;
};
export type Question = {
  question: string;
  options: string[];
  allow_free_text: boolean;
  why: string;
  askId?: string;
  optionIds?: string[];
  multi?: boolean;
};
export type Decision = {
  id?: string;
  option: string;
  benefit: string;
  cost: string;
  risk: string;
  reversibility: string;
  first_step: string;
  unknowns?: string[];
};
export type StatusPhase = 'thinking' | 'tool' | 'writing' | 'reviewing';
export type Review = {
  state: 'pending' | 'passed' | 'revised' | 'skipped';
  reasons: { code: string; severity: 1 | 2 | 3 | 4 | 5 }[];
  revisionId?: string;
};
export type Envelope = {
  schema?: 'core3.0' | 'core4.0';
  messageId?: string;
  question?: Question;
  answer: string;
  professional_appendix: string;
  receipts: Receipt[];
  decisions: Decision[];
  evidence: { ref: string; claim: string }[];
  interrupt?: { id: string; state_version: JsonObject; questions: string[] };
  review?: Review;
};
export type EventMetadata = { v?: 1; run_id?: string; seq?: number; ts?: string };
export type ChatEvent = EventMetadata &
  (
    | {
        type: 'started';
        run_id: string;
        thread_id?: string;
        message_id?: string;
        area_id?: string;
        topic_id?: string;
        incognito?: boolean;
      }
    | { type: 'status'; text: string; phase?: StatusPhase }
    | {
        type: 'tool_call' | 'tool_result';
        name: string;
        summary: string;
        receipt?: Receipt;
        call_id?: string;
        ok?: boolean;
      }
    | { type: 'text_delta'; text: string }
    | { type: 'text_reset'; text: string; reason: 'revised' | 'resumed'; revision_id?: string }
    | { type: 'memory_receipt'; receipt: Receipt }
    | { type: 'ask_user'; question: Question }
    | { type: 'present_options'; options: Decision[]; optionsId?: string; prompt?: string }
    | { type: 'review'; review: Review }
    | { type: 'final'; envelope: Envelope; message_id?: string }
    | { type: 'error'; code: string; message: string; retryable: boolean }
  );
export type StreamState = {
  threadId?: string;
  messageId?: string;
  errorCode?: string;
  retryable?: boolean;
  reviewPending?: boolean;
  phase?: StatusPhase;
  review?: Review;
  revisionId?: string;
  areaId?: string;
  topicId?: string;
  incognito?: boolean;
  optionsId?: string;
  optionsPrompt?: string;
  answered?: string;
  runId: string;
  text: string;
  status: string;
  revised: boolean;
  complete: boolean;
  tools: { name: string; summary: string; done: boolean; callId?: string; ok?: boolean }[];
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
  thread?: { threadId: string; incognito: boolean; acceptance?: ThreadAcceptance };
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
