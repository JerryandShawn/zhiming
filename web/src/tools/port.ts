import type { EvidenceRef, FreshConsent, PublishedSample, SynastryQuery, ToolPort, WindowQuery } from './types';

export const purposes = ['签约', '面试', '搬家', '出行', '表白', '开业'] as const;
export const kindLabels = { romantic: '亲密关系', friendship: '朋友相处', collaboration: '合作' } as const;
export const sampleNames = { ayuan: '阿远（合成）', xiaohe: '小禾（合成）' } as const;
export const synastryKey = (query: SynastryQuery) =>
  JSON.stringify([query.a, query.b, query.kind, query.asOfDate, query.orbDegrees]);
export const windowKey = (query: WindowQuery) =>
  JSON.stringify([query.purpose, query.startDate, query.endDate, query.offset, query.limit]);
const evidenceKey = (ref: EvidenceRef) => JSON.stringify([ref.document_id, ref.alias]);
export function validDate(value: string) {
  if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return (
    Number.isFinite(date.getTime()) &&
    date.toISOString().slice(0, 10) === value &&
    date.getUTCFullYear() >= 1901 &&
    date.getUTCFullYear() <= 2099
  );
}
export class ToolViewError extends Error {
  constructor(public code: 'CONSENT_REQUIRED' | 'INVALID_INPUT' | 'INVALID_PUBLIC_SAMPLE') {
    super(
      code === 'CONSENT_REQUIRED'
        ? '请先分别确认双方本次展示，并在条件改变后重新确认。'
        : '当前条件或公开样例暂不可用，请重新核对。',
    );
    this.name = 'ToolViewError';
  }
}

function validateCatalog(samples: readonly PublishedSample[]) {
  const documents = new Set<string>();
  for (const sample of samples) {
    const aliases = new Set(sample.evidence.map((item) => item.ref.alias));
    if (
      sample.format !== 'frontend-tool-sample-v1' ||
      !['window_search', 'synastry'].includes(sample.tool) ||
      !/^tool-[a-f0-9]{64}$/.test(sample.document_id) ||
      documents.has(sample.document_id) ||
      sample.effects.model_calls !== 0 ||
      sample.effects.writes !== 0 ||
      sample.effects.alias_registry !== 'ephemeral_only' ||
      sample.provenance.mode !== 'published-synthetic-engine' ||
      aliases.size !== sample.evidence.length ||
      sample.evidence.some(
        (item) =>
          item.ref.document_id !== sample.document_id ||
          !/^[cr][1-9][0-9]*$/.test(item.ref.alias) ||
          item.evidence_refs?.some((ref) => ref.document_id !== sample.document_id || !aliases.has(ref.alias)),
      )
    )
      throw new ToolViewError('INVALID_PUBLIC_SAMPLE');
    documents.add(sample.document_id);
  }
}

/** Verified public synthetic exporter projections only. This is not a future
 * real API's owner authority. Every mounted viewer owns an independent scope,
 * including two viewers displaying the same document at the same time.
 */
export function createToolDemoPort(
  samples: readonly PublishedSample[],
  wait: (signal?: AbortSignal) => Promise<void> = async () => {},
): ToolPort {
  validateCatalog(samples);
  const catalogSamples = structuredClone(samples);
  const windows = catalogSamples.filter((sample) => sample.tool === 'window_search');
  const catalog = windows.map(({ data }) => ({
    purpose: data.purpose,
    startDate: data.range.start_date,
    endDate: data.range.end_date,
    offset: data.pagination.offset,
    limit: data.pagination.limit,
    summary: {
      total: data.pagination.total,
      returned: data.pagination.returned,
      first_rank: data.candidates[0]?.rank ?? null,
      last_rank: data.candidates.at(-1)?.rank ?? null,
    },
  }));

  function createScope(): ToolPort {
    let generation = 0,
      active: PublishedSample | undefined;
    const reset = () => {
      generation++;
      active = undefined;
    };
    const begin = () => {
      reset();
      return generation;
    };
    const ready = async (id: number, signal?: AbortSignal) => {
      signal?.throwIfAborted();
      await wait(signal);
      signal?.throwIfAborted();
      if (id !== generation) throw new DOMException('View changed', 'AbortError');
    };
    const activate = <T extends PublishedSample>(sample: T) => {
      active = sample;
      return { status: 'ready' as const, sample: structuredClone(sample) };
    };
    return {
      createScope,
      reset,
      windows: structuredClone(catalog),
      async windowSearch(input, signal) {
        const id = begin(),
          query = structuredClone(input);
        const start = Date.parse(`${query.startDate}T00:00:00Z`),
          end = Date.parse(`${query.endDate}T00:00:00Z`);
        if (
          !purposes.includes(query.purpose) ||
          !validDate(query.startDate) ||
          !validDate(query.endDate) ||
          end < start ||
          end - start > 365 * 86400000 ||
          !Number.isInteger(query.offset) ||
          query.offset < 0 ||
          !Number.isInteger(query.limit) ||
          query.limit < 1 ||
          query.limit > 31
        )
          throw new ToolViewError('INVALID_INPUT');
        await ready(id, signal);
        const index = catalog.findIndex((item) => windowKey(item) === windowKey(query));
        return index < 0
          ? {
              status: 'unavailable',
              message: '当前只提供签约 2026-10-21 至 10-27 的已发布分页样例；此条件尚无样例，也没有接入实时计算。',
            }
          : activate(windows[index]);
      },
      async synastry(input, consent: FreshConsent | undefined, signal) {
        const id = begin(),
          query = structuredClone(input);
        // Fresh confirmation is checked before either side is looked up.
        if (!consent || consent.a !== true || consent.b !== true || consent.queryKey !== synastryKey(query))
          throw new ToolViewError('CONSENT_REQUIRED');
        if (
          !validDate(query.asOfDate) ||
          !Number.isFinite(query.orbDegrees) ||
          query.orbDegrees < 0 ||
          query.orbDegrees > 10 ||
          !Object.hasOwn(kindLabels, query.kind) ||
          !Object.hasOwn(sampleNames, query.a) ||
          !Object.hasOwn(sampleNames, query.b) ||
          query.a === query.b
        )
          throw new ToolViewError('INVALID_INPUT');
        await ready(id, signal);
        const sample = catalogSamples.find(
          (item) =>
            item.tool === 'synastry' &&
            item.data.kind === query.kind &&
            item.data.as_of_date === query.asOfDate &&
            item.data.astro.orb_degrees === query.orbDegrees,
        );
        if (!sample || query.a !== 'ayuan' || query.b !== 'xiaohe')
          return {
            status: 'unavailable',
            message: '当前仅有阿远与小禾、亲密关系、2026-10-21、统一容许度 6° 的固定公开样例；没有为新条件重新计算。',
          };
        if (sample.tool !== 'synastry' || sample.data.requires_fresh_consent !== true)
          throw new ToolViewError('INVALID_PUBLIC_SAMPLE');
        return activate(sample);
      },
      resolveEvidence(ref) {
        if (!active || active.document_id !== ref.document_id) return undefined;
        const found = active.evidence.find((item) => evidenceKey(item.ref) === evidenceKey(ref));
        return found ? structuredClone(found) : undefined;
      },
    };
  }
  return createScope();
}
