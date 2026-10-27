import type { ApiSpace, ApiTopic } from './http';

// In-memory stand-in for the draft spaces/topics routes. Preview and tests only: synthetic data,
// no storage, no network. It mirrors the draft's idempotency and revision rules so the UI is
// exercised against the same failure shapes the real service will return.
type Options = { unimplemented?: boolean; delayMs?: number };
const at = '2026-10-27T17:00:00+08:00';
const seedSpaces: ApiSpace[] = [
  ['daily', '日常', false],
  ['career', '事业', false],
  ['relationships', '感情', true],
  ['family', '家庭', false],
  ['wellbeing', '身心', true],
  ['finance', '财务', false],
  ['metaphysics', '命理', false],
].map(([id, name, sensitive], order) => ({
  id: id as string,
  revision: 1,
  name: name as string,
  description: '',
  order,
  hidden: false,
  sensitive: sensitive as boolean,
}));
const seedTopics: ApiTopic[] = [
  ['synthetic:t-job', 'career', '合成样例：是否换岗', 'open', '比较两份合成岗位的节奏与成长。'],
  ['synthetic:t-review', 'career', '合成样例：季度复盘', 'archived', ''],
  ['synthetic:t-walk', 'daily', '合成样例：晚饭后散步', 'open', ''],
].map(([id, space_id, title, status, summary], index) => ({
  id: id as string,
  space_id: space_id as string,
  revision: 1,
  title: title as string,
  status: status as ApiTopic['status'],
  summary: summary as string,
  source_refs: [],
  case_id: null,
  updated_at: at,
  summary_until_message_id: null,
  created_at: `2026-10-2${index}T09:00:00+08:00`,
  last_at: at,
}));

export function createSpacesFakeFetch(options: Options = {}): typeof fetch {
  const spaces = new Map(seedSpaces.map((item) => [item.id, { ...item }]));
  const topics = new Map(seedTopics.map((item) => [item.id, { ...item }]));
  const ledger = new Map<string, { body: string; status: number; value: unknown }>();
  let sequence = 0;
  const reply = (status: number, value: unknown) =>
    new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
  const fail = (status: number, code: string, request_id?: string, extra = {}) =>
    reply(status, {
      ok: false,
      ...(request_id ? { request_id } : {}),
      error: { code, message: '合成服务错误', retryable: false, ...extra },
    });
  const receipt = (request_id: string, entity_id: string, revision: number, write_status = 'updated') => ({
    ok: true,
    request_id,
    receipt: { operation_id: `synthetic:op${++sequence}`, write_status, entity_id, revision },
  });
  function write(request_id: string, body: string, run: () => { status: number; value: unknown } | Response): Response {
    const prior = ledger.get(request_id);
    if (prior)
      return prior.body === body ? reply(prior.status, prior.value) : fail(409, 'IDEMPOTENCY_CONFLICT', request_id);
    const result = run();
    if (result instanceof Response) return result;
    ledger.set(request_id, { body, ...result });
    return reply(result.status, result.value);
  }
  function route(method: string, url: URL, raw: string): Response {
    if (options.unimplemented) return fail(501, 'DRAFT_NOT_IMPLEMENTED');
    const path = url.pathname.split('/').map(decodeURIComponent);
    if (method === 'GET' && url.pathname === '/api/spaces') {
      const hidden = url.searchParams.get('include_hidden') === 'true';
      const items = [...spaces.values()].filter((item) => hidden || !item.hidden).sort((a, b) => a.order - b.order);
      return reply(200, { items, next_cursor: null });
    }
    if (method === 'GET' && path[2] === 'spaces' && path[4] === 'topics') {
      if (!spaces.has(path[3])) return fail(404, 'SCOPE_NOT_FOUND');
      const items = [...topics.values()]
        .filter((item) => item.space_id === path[3])
        .sort((a, b) => b.last_at.localeCompare(a.last_at) || a.id.localeCompare(b.id));
      return reply(200, { items, next_cursor: null });
    }
    let body: Record<string, unknown>;
    try {
      body = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return fail(422, 'VALIDATION_ERROR');
    }
    const request_id = String(body.request_id);
    const now = new Date().toISOString().replace('Z', '+00:00');
    if (method === 'POST' && path[2] === 'spaces' && path[4] === 'topics')
      return write(request_id, raw, () => {
        if (!spaces.has(path[3])) return fail(404, 'SCOPE_NOT_FOUND', request_id);
        const id = `synthetic:t${++sequence}`;
        topics.set(id, {
          id,
          space_id: path[3],
          revision: 1,
          title: String(body.title).trim(),
          status: 'open',
          summary: '',
          source_refs: [],
          case_id: null,
          updated_at: now,
          summary_until_message_id: null,
          created_at: now,
          last_at: now,
        });
        return { status: 201, value: receipt(request_id, id, 1, 'saved') };
      });
    if (method === 'PATCH' && path[2] === 'topics')
      return write(request_id, raw, () => {
        const item = topics.get(path[3]);
        if (!item) return fail(404, 'SCOPE_NOT_FOUND', request_id);
        if (body.expected_revision !== item.revision)
          return fail(409, 'REVISION_CONFLICT', request_id, { current_revision: item.revision });
        const patch = body.patch as Partial<ApiTopic>;
        if (patch.space_id && !spaces.has(patch.space_id)) return fail(404, 'SCOPE_NOT_FOUND', request_id);
        Object.assign(item, patch, { revision: item.revision + 1, updated_at: now });
        return { status: 200, value: receipt(request_id, item.id, item.revision) };
      });
    if (method === 'PATCH' && path[2] === 'spaces')
      return write(request_id, raw, () => {
        const item = spaces.get(path[3]);
        if (!item) return fail(404, 'SCOPE_NOT_FOUND', request_id);
        if (body.expected_revision !== item.revision)
          return fail(409, 'REVISION_CONFLICT', request_id, { current_revision: item.revision });
        Object.assign(item, body.patch, { revision: item.revision + 1 });
        return { status: 200, value: receipt(request_id, item.id, item.revision) };
      });
    return fail(404, 'SCOPE_NOT_FOUND');
  }
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
    const url = new URL(String(input), 'https://fake.invalid');
    return route(init?.method ?? 'GET', url, typeof init?.body === 'string' ? init.body : '');
  };
}
/** Test hook: lets a scenario bump a topic revision as if another device edited it. */
export const fakeSeed = { spaces: seedSpaces, topics: seedTopics };
