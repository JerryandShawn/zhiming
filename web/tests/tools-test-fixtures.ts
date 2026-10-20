import { purposes, synastryKey } from '../src/tools/port';
import type { PublicEvidence, SynastryQuery, SynastrySample, WindowSample } from '../src/tools/types';

export const documentId = (digit: string) => `tool-${digit.repeat(64)}`;
export const synastryQuery: SynastryQuery = {
  a: 'ayuan',
  b: 'xiaohe',
  kind: 'romantic',
  asOfDate: '2026-10-21',
  orbDegrees: 6,
};
export const freshConsent = () => ({ queryKey: synastryKey(synastryQuery), a: true as const, b: true as const });
export const publicEvidence = (document_id: string, alias = 'c1'): PublicEvidence => ({
  ref: { document_id, alias },
  kind: 'fact',
  summary: '独立合成依据',
  value_sha256: '1'.repeat(64),
  claim_id: `claim-${'2'.repeat(64)}`,
});
const provenance = {
  source_ref: 'synthetic-test',
  source_commit: '0'.repeat(40),
  source_path: 'synthetic-test.json',
  source_sha256: '3'.repeat(64),
  mode: 'published-synthetic-engine' as const,
  integrity: 'root-document-pointer-alias-and-fact-digests-verified' as const,
};
const shared = (digit: string) => ({
  format: 'frontend-tool-sample-v1' as const,
  document_id: documentId(digit),
  evidence: [publicEvidence(documentId(digit))],
  effects: { model_calls: 0 as const, writes: 0 as const, alias_registry: 'ephemeral_only' as const },
  limits: ['单测合成夹具，不代表来源文件摘要已经重算'],
  provenance,
});
export function windowFixture(digit = 'a', offset = 0): WindowSample {
  const ranked = { date: '2026-10-21', rank: 1, score: 0, positive_sum: 0, negative_sum: 0 };
  const purpose_weights = Object.fromEntries(
    purposes.map((purpose) => [
      purpose,
      {
        bazi_relation: {},
        bazi_ten_god: {},
        ziwei_mutagen: {},
        astro_aspect: {},
      },
    ]),
  ) as WindowSample['data']['weights']['purpose_weights'];
  return {
    ...shared(digit),
    tool: 'window_search',
    data: {
      purpose: '签约',
      range: { start_date: '2026-10-21', end_date: '2026-10-21', inclusive: true, day_count: 1 },
      method: {
        ranking: 'score_descending_then_date_ascending',
        weights_version: 'project-six-purpose-ranking-v1',
        sample_clock: '12:00:00+08:00',
        daily_orb_degrees: 2,
        election_hours_searched: false,
        prediction_validated: false,
      },
      weights: {
        version: 'project-six-purpose-ranking-v1',
        layer_factors: { yearly: 1, monthly: 2, daily: 3 },
        purpose_weights,
        prediction_validated: false,
      },
      ranking_summary: [ranked],
      candidates: offset ? [] : [{ ...ranked, positive_hits: [], negative_hits: [], neutral_hits: [] }],
      pagination: { total: 1, offset, limit: 31, returned: offset ? 0 : 1, has_more: false, next_offset: null },
      query_sha256: '4'.repeat(64),
      ignored_condition_count: 0,
    },
  };
}
/** The port/hook tests consume only these fields. Full scientific projection and
 * source-integrity tests use independently exported P8 fixtures, not this stub.
 */
export function synastryFixture(digit = 'c'): SynastrySample {
  return {
    ...shared(digit),
    tool: 'synastry',
    data: {
      kind: 'romantic',
      as_of_date: '2026-10-21',
      sample_consent: 'user_confirmed',
      requires_fresh_consent: true,
      astro: { orb_degrees: 6 },
    },
  } as SynastrySample;
}
export function gate<T>() {
  let resolve!: (value: T) => void, reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
