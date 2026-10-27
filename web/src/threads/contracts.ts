import { bounded, identifier, keys, record, text } from '../chat/wireChecksV1';

// P3 api_runtime_v1 -> thread_runtime_api_v1, fixed at 27b8af95 (2026-10-27).
// This DTO is separate from /api/chat's message_id-bearing legacy receipt.
export type ThreadMessage = Readonly<{
  request_id: string;
  message: string;
  subject_id: string;
  conversation_id: string;
  case_ids: readonly string[];
  depth: 'standard' | 'deep';
}>;
export const runStates = [
  'queued',
  'running',
  'inbox_wait',
  'succeeded',
  'failed',
  'stale',
  'cancelled',
  'revoked',
] as const;
export type ThreadAcceptance = Readonly<
  {
    run_id: string;
    thread_id: string;
    status: (typeof runStates)[number];
    run_url: string;
  } & ({ runtime: 'v3' } | { runtime: 'v4'; events_url: string })
>;

export class ThreadRequestError extends Error {
  constructor(public code: 'input' | 'receipt' | 'obsolete' | 'network' | 'http') {
    super(
      {
        input: '这条消息包含尚未支持或无效的内容，请保留原来的输入。',
        receipt: '运行接收回执尚未核对，请保留原来的请求。',
        obsolete: '当前会话已经切换，本次结果不会显示。',
        network: '没有收到确认，请保留原请求标识和内容再核对。',
        http: '这次请求没有得到确认，请保留原来的输入。',
      }[code],
    );
    this.name = 'ThreadRequestError';
  }
}

// Python str.strip whitespace differs from JS trim (notably U+001C and U+FEFF).
const pythonWhitespace = new Set([
  9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201,
  8202, 8232, 8233, 8239, 8287, 12288,
]);
const blankMessage = (value: string) =>
  Array.from(value).every((letter) => pythonWhitespace.has(letter.codePointAt(0)!));
export const opaqueThreadId = (value: unknown): value is string =>
  text(value) &&
  value.length > 0 &&
  value.trim().length > 0 &&
  Array.from(value).every((letter) => letter.codePointAt(0)! >= 32 && letter.codePointAt(0) !== 127);

/** Validate without trimming, inventing IDs, dropping attachments, or widening depth. */
export function threadMessage(value: unknown, incognito: boolean): ThreadMessage {
  const invalid = () => {
    throw new ThreadRequestError('input');
  };
  if (!record(value) || !keys(value, ['request_id', 'message'], ['subject_id', 'conversation_id', 'case_ids', 'depth']))
    return invalid();
  const subject = Object.hasOwn(value, 'subject_id') ? value.subject_id : 'self';
  const conversation = Object.hasOwn(value, 'conversation_id') ? value.conversation_id : 'shared';
  const cases = Object.hasOwn(value, 'case_ids') ? value.case_ids : [];
  const depth = Object.hasOwn(value, 'depth') ? value.depth : 'standard';
  if (
    !identifier(value.request_id) ||
    !bounded(value.message, 16000, 1) ||
    blankMessage(value.message) ||
    !bounded(subject, 200, 1) ||
    !bounded(conversation, 200, 1) ||
    !Array.isArray(cases) ||
    cases.length > 8 ||
    (incognito && cases.length > 0) ||
    (depth !== 'standard' && depth !== 'deep')
  )
    return invalid();
  // Array.every skips holes; JSON would turn those into unsupported null entries.
  for (let index = 0; index < cases.length; index++)
    if (!Object.hasOwn(cases, index) || !text(cases[index])) return invalid();
  return Object.freeze({
    request_id: value.request_id,
    message: value.message,
    subject_id: subject,
    conversation_id: conversation,
    case_ids: Object.freeze([...cases] as string[]),
    depth,
  });
}

/** Accept only the server's exact same-run relative URLs before sending auth headers. */
export function threadAcceptance(value: unknown): ThreadAcceptance {
  const invalid = () => {
    throw new ThreadRequestError('receipt');
  };
  if (!record(value)) return invalid();
  const runtime = value.runtime;
  const fields = ['run_id', 'thread_id', 'status', 'runtime', 'run_url'];
  if (runtime === 'v4') fields.push('events_url');
  if (
    !keys(value, fields) ||
    (runtime !== 'v3' && runtime !== 'v4') ||
    !identifier(value.run_id) ||
    !opaqueThreadId(value.thread_id) ||
    !runStates.some((state) => state === value.status)
  )
    return invalid();
  const path = `/api/runs/${value.run_id}`;
  if (value.run_url !== path || (runtime === 'v4' && value.events_url !== `${path}/events`)) return invalid();
  const common = {
    run_id: value.run_id,
    thread_id: value.thread_id,
    status: value.status as ThreadAcceptance['status'],
    run_url: path,
  };
  return runtime === 'v4'
    ? Object.freeze({ ...common, runtime, events_url: `${path}/events` })
    : Object.freeze({ ...common, runtime });
}
