import type { StudyProgress, StudyProgressStatus } from './progressHttp';

// Synthetic personal progress only. Public course content, storage and real authentication are not involved.
type Options = { delayMs?: number; unimplemented?: boolean; lessons?: Record<string, string> };
const reply = (status: number, value: unknown) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const fail = (status: number, code: string, request_id?: string, extra = {}) =>
  reply(status, {
    ok: false,
    ...(request_id ? { request_id } : {}),
    error: { code, message: '合成服务错误', retryable: false, ...extra },
  });

export function createStudyProgressFakeFetch(options: Options = {}): typeof fetch {
  const lessons = options.lessons ?? { 'synthetic:l1': 'v1' };
  const progress = new Map<string, StudyProgress>();
  const ledger = new Map<string, { body: string; status: number; value: unknown }>();
  let sequence = 0;
  const receipt = (request_id: string, lesson_id: string, revision: number) => ({
    ok: true,
    request_id,
    receipt: {
      operation_id: `synthetic:study-op${++sequence}`,
      write_status: revision === 1 ? 'saved' : 'updated',
      entity_id: lesson_id,
      revision,
    },
  });
  const wait = (signal?: AbortSignal | null) =>
    new Promise<void>((resolve, reject) => {
      if (!options.delayMs) return resolve();
      const timer = setTimeout(resolve, options.delayMs);
      signal?.addEventListener('abort', () => {
        clearTimeout(timer);
        reject(new DOMException('已停止连接', 'AbortError'));
      });
    });
  return async (input, init) => {
    await wait(init?.signal);
    if (options.unimplemented) return fail(501, 'DRAFT_NOT_IMPLEMENTED');
    const url = new URL(String(input), 'https://fake.invalid');
    const match = /^\/api\/study\/progress\/([^/]+)$/.exec(url.pathname);
    if (!match) return fail(404, 'SCOPE_NOT_FOUND');
    const lessonId = decodeURIComponent(match[1]!);
    if (!Object.hasOwn(lessons, lessonId)) return fail(404, 'SCOPE_NOT_FOUND');
    const method = init?.method ?? 'GET';
    if (method === 'GET') {
      const current = progress.get(lessonId);
      return reply(200, { progress: current ?? null, revision: current?.revision ?? 0 });
    }
    if (method !== 'PUT') return fail(405, 'VALIDATION_ERROR');
    let body: {
      request_id?: string;
      expected_revision?: number;
      lesson_version?: string;
      status?: StudyProgressStatus;
      bookmark?: string | null;
    };
    try {
      body = JSON.parse(typeof init?.body === 'string' ? init.body : '') as typeof body;
    } catch {
      return fail(422, 'VALIDATION_ERROR');
    }
    const requestId = String(body.request_id);
    const raw = String(init?.body);
    const prior = ledger.get(requestId);
    if (prior)
      return prior.body === raw ? reply(prior.status, prior.value) : fail(409, 'IDEMPOTENCY_CONFLICT', requestId);
    const current = progress.get(lessonId);
    if (body.expected_revision !== (current?.revision ?? 0))
      return fail(409, 'REVISION_CONFLICT', requestId, current ? { current_revision: current.revision } : {});
    if (body.lesson_version !== lessons[lessonId])
      return fail(409, 'REVISION_CONFLICT', requestId, current ? { current_revision: current.revision } : {});
    const next: StudyProgress = Object.freeze({
      lesson_id: lessonId,
      lesson_version: body.lesson_version!,
      revision: (current?.revision ?? 0) + 1,
      status: body.status!,
      bookmark: body.bookmark ?? null,
    });
    progress.set(lessonId, next);
    const result = { status: 200, value: receipt(requestId, lessonId, next.revision) };
    ledger.set(requestId, { body: raw, ...result });
    return reply(result.status, result.value);
  };
}
