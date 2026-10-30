import type { OrganizeProposal, PlanEdit, SuggestedTopic } from './http';

// In-memory draft service for tests and future explicit previews. No source messages are changed.
type Options = { delayMs?: number; unimplemented?: boolean };
const source = { message_id: 'synthetic:m1', revision: 1, start: 0, end: 2 };
const topic: SuggestedTopic = {
  id: 'synthetic:t1',
  space_id: 'daily',
  title: '合成话题',
  message_ids: ['synthetic:m1'],
  start_at: '2026-10-27T17:00:00+08:00',
  end_at: '2026-10-27T17:00:00+08:00',
  sample: '合成摘要',
  confidence: 0.6,
  source_refs: [source],
};
const seed: OrganizeProposal = {
  batch_id: 'synthetic:b1',
  subject_id: 'synthetic:s1',
  revision: 1,
  plan_fingerprint: 'a'.repeat(64),
  status: 'proposed',
  quality_gate: 'record_only',
  source_refs: [source],
  topics: [topic],
  needs_review: ['synthetic:t1'],
  ignored_count: 0,
  encoder_mode: 'synthetic',
  degradation: null,
};
const reply = (status: number, value: unknown) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const fail = (status: number, code: string, request_id?: string, extra = {}) =>
  reply(status, {
    ok: false,
    ...(request_id ? { request_id } : {}),
    error: { code, message: '合成服务错误', retryable: false, ...extra },
  });

export function createOrganizeFakeFetch(options: Options = {}): typeof fetch {
  const proposals = new Map<string, OrganizeProposal>([[seed.batch_id, structuredClone(seed)]]);
  const ledger = new Map<string, { body: string; status: number; value: unknown }>();
  let sequence = 0;
  const receipt = (request_id: string, entity_id: string, revision: number, write_status = 'updated') => ({
    ok: true,
    request_id,
    receipt: { operation_id: `synthetic:organize-op${++sequence}`, write_status, entity_id, revision },
  });
  function write(requestId: string, raw: string, run: () => { status: number; value: unknown } | Response) {
    const prior = ledger.get(requestId);
    if (prior)
      return prior.body === raw ? reply(prior.status, prior.value) : fail(409, 'IDEMPOTENCY_CONFLICT', requestId);
    const result = run();
    if (result instanceof Response) return result;
    ledger.set(requestId, { body: raw, ...result });
    return reply(result.status, result.value);
  }
  function applyEdit(proposal: OrganizeProposal, edit: PlanEdit) {
    const topics = proposal.topics.map((item) => ({ ...item, message_ids: [...item.message_ids] }));
    const index = topics.findIndex((item) => item.id === edit.target_id);
    if (index < 0) throw new Error('SCOPE_NOT_FOUND');
    if (edit.kind === 'ignore') {
      topics.splice(index, 1);
      return { topics, ignored_count: proposal.ignored_count + 1 };
    }
    if (edit.kind === 'rename') topics[index]!.title = edit.title;
    if (edit.kind === 'move') topics[index]!.space_id = edit.space_id;
    if (edit.kind === 'merge') {
      const selected = topics.filter((item) => edit.target_ids.includes(item.id));
      const target = topics[index]!;
      target.message_ids = [...new Set(selected.flatMap((item) => item.message_ids))];
      for (const item of selected) if (item.id !== target.id) topics.splice(topics.indexOf(item), 1);
    }
    if (edit.kind === 'split') {
      const target = topics[index]!;
      target.message_ids = target.message_ids.filter((id) => !edit.message_ids.includes(id));
      topics.push({
        ...target,
        id: `synthetic:split${sequence + 1}`,
        title: edit.title,
        message_ids: [...edit.message_ids],
      });
    }
    return { topics, ignored_count: proposal.ignored_count };
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
    if (options.unimplemented) return fail(501, 'DRAFT_NOT_IMPLEMENTED');
    const url = new URL(String(input), 'https://fake.invalid');
    const path = url.pathname.split('/').map(decodeURIComponent);
    const method = init?.method ?? 'GET';
    if (method === 'GET' && url.pathname === '/api/organize/proposal') {
      const batchId = url.searchParams.get('batch_id');
      return reply(200, {
        items: [...proposals.values()].filter((item) => !batchId || item.batch_id === batchId),
        next_cursor: null,
      });
    }
    let body: Record<string, unknown>;
    try {
      body = JSON.parse(typeof init?.body === 'string' ? init.body : '') as Record<string, unknown>;
    } catch {
      return fail(422, 'VALIDATION_ERROR');
    }
    const requestId = String(body.request_id),
      raw = String(init?.body);
    if (method === 'POST' && url.pathname === '/api/organize/proposal')
      return write(requestId, raw, () => ({
        status: 202,
        value: receipt(requestId, 'synthetic:b2', 1, 'queued'),
      }));
    const batchId = path[3] === 'apply' || path[3] === 'revert' ? path[4] : path[3];
    const proposal = batchId ? proposals.get(batchId) : undefined;
    if (!proposal) return fail(404, 'SCOPE_NOT_FOUND', requestId);
    if (method === 'PATCH' && path[2] === 'organize' && path.length === 4)
      return write(requestId, raw, () => {
        if (body.expected_revision !== proposal.revision)
          return fail(409, 'REVISION_CONFLICT', requestId, { current_revision: proposal.revision });
        let edited: ReturnType<typeof applyEdit> = {
          topics: proposal.topics.map((item) => ({ ...item, message_ids: [...item.message_ids] })),
          ignored_count: proposal.ignored_count,
        };
        try {
          for (const edit of body.edits as PlanEdit[]) edited = applyEdit({ ...proposal, ...edited }, edit);
        } catch {
          return fail(404, 'SCOPE_NOT_FOUND', requestId);
        }
        const revision = proposal.revision + 1;
        proposals.set(proposal.batch_id, {
          ...proposal,
          ...edited,
          revision,
          plan_fingerprint: String.fromCharCode(97 + ((revision - 1) % 26)).repeat(64),
          status: 'proposed',
        });
        return { status: 200, value: receipt(requestId, proposal.batch_id, revision) };
      });
    if (method === 'POST' && path[4] === 'review')
      return write(requestId, raw, () => {
        if (body.expected_revision !== proposal.revision)
          return fail(409, 'REVISION_CONFLICT', requestId, { current_revision: proposal.revision });
        if (body.plan_fingerprint !== proposal.plan_fingerprint) return fail(409, 'REVIEW_PLAN_CHANGED', requestId);
        if (body.accepted !== true) return fail(422, 'VALIDATION_ERROR', requestId);
        const revision = proposal.revision + 1;
        proposals.set(proposal.batch_id, { ...proposal, revision, status: 'reviewed' });
        return {
          status: 200,
          value: {
            ...receipt(requestId, proposal.batch_id, revision),
            review: {
              receipt_id: `synthetic:review${sequence}`,
              batch_id: proposal.batch_id,
              revision,
              plan_fingerprint: proposal.plan_fingerprint,
              reviewed_at: '2026-10-27T17:00:00+08:00',
              expires_at: '2026-10-28T17:00:00+08:00',
            },
          },
        };
      });
    if (method === 'POST' && path[3] === 'apply') return fail(409, 'QUALITY_GATE_CLOSED', requestId);
    if (method === 'POST' && path[3] === 'revert') return fail(404, 'SCOPE_NOT_FOUND', requestId);
    return fail(404, 'SCOPE_NOT_FOUND', requestId);
  };
}

export const organizeFakeSeed = seed;
