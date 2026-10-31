/** Draft public viewer types, copied from export-tool-samples.py's projection. */
export type ToolName = 'window_search' | 'synastry';
export type Purpose = '签约' | '面试' | '搬家' | '出行' | '表白' | '开业';
export type RelationKind = 'romantic' | 'friendship' | 'collaboration';
export type Side = 'a' | 'b';
export type PillarName = 'year' | 'month' | 'day' | 'hour';
export type PlanetName = '太阳' | '月亮' | '水星' | '金星' | '火星' | '木星' | '土星' | '天王' | '海王' | '冥王';
export type EvidenceRef = { document_id: string; alias: string };
export type PublicEvidence = {
  ref: EvidenceRef;
  kind: 'fact' | 'rule';
  summary: string;
  value_sha256: string;
  claim_id: string;
  evidence_refs?: EvidenceRef[];
  school?: string;
  school_label?: string;
  source?: { title: string; url?: string; status?: string };
  catalog_id?: string;
};
export type ToolSample<K extends ToolName, T> = {
  format: 'frontend-tool-sample-v1';
  tool: K;
  document_id: string;
  data: T;
  evidence: PublicEvidence[];
  effects: { model_calls: 0; writes: 0; alias_registry: 'ephemeral_only' };
  limits: string[];
  provenance: {
    source_ref: string;
    source_commit: string;
    source_path: string;
    source_sha256: string;
    mode: 'published-synthetic-engine';
    integrity: 'root-document-pointer-alias-and-fact-digests-verified';
  };
};
export type RuleFamily = 'bazi_relation' | 'bazi_ten_god' | 'ziwei_mutagen' | 'astro_aspect';
export type WindowHit = {
  date: string;
  family: RuleFamily;
  label: string;
  base_weight: number;
  layer_factor: number;
  contribution: number;
  reason: 'published_project_weight' | 'incomplete_relation_zero_weight';
  ref: EvidenceRef;
  evidence_refs: EvidenceRef[];
};
export type WindowRank = { date: string; rank: number; score: number; positive_sum: number; negative_sum: number };
export type WindowCandidate = {
  date: string;
  rank: number;
  score: number;
  positive_hits: WindowHit[];
  negative_hits: WindowHit[];
  neutral_hits: WindowHit[];
};
export type WindowData = {
  purpose: Purpose;
  range: { start_date: string; end_date: string; inclusive: true; day_count: number };
  method: {
    ranking: 'score_descending_then_date_ascending';
    weights_version: 'project-six-purpose-ranking-v1';
    sample_clock: '12:00:00+08:00';
    daily_orb_degrees: 2;
    election_hours_searched: false;
    prediction_validated: false;
  };
  weights: {
    version: 'project-six-purpose-ranking-v1';
    layer_factors: { yearly: 1; monthly: 2; daily: 3 };
    purpose_weights: Record<Purpose, Record<RuleFamily, Record<string, number>>>;
    prediction_validated: false;
  };
  ranking_summary: WindowRank[];
  candidates: WindowCandidate[];
  pagination: {
    total: number;
    offset: number;
    limit: number;
    returned: number;
    has_more: boolean;
    next_offset: number | null;
  };
  query_sha256: string;
  ignored_condition_count: number;
};
export type WindowSample = ToolSample<'window_search', WindowData>;
export type PlanetPosition = { longitude: number; retrograde: boolean };
export type CrossAspect = {
  from: PlanetName;
  to: PlanetName;
  aspect: '合相' | '六合' | '刑相' | '拱相' | '冲相';
  angle: number;
  orb_degrees: number;
};
export type Palace = { name: string; index: number; ganzhi: string; major: string[]; minor: string[] };
export type SynastryData = {
  kind: RelationKind;
  as_of_date: string;
  sample_consent: 'user_confirmed';
  requires_fresh_consent: true;
  bazi: {
    pillars_a: Record<PillarName, string>;
    pillars_b: Record<PillarName, string>;
    day_stem_combination: { a: string; b: string; met: boolean; transformation_established: false };
    branch_relations: {
      a_pillar: PillarName;
      b_pillar: PillarName;
      a: string;
      b: string;
      kind: '地支六合' | '地支六冲';
    }[];
    visible_a: { stems: string[]; element_counts: Record<string, number>; qi_strength_assessed: false };
    visible_b: { stems: string[]; element_counts: Record<string, number>; qi_strength_assessed: false };
    element_complement: { recipient: Side; elements: string[] }[];
    useful_complement: {
      recipient: Side;
      method: '扶抑' | '调候' | '格局';
      candidate_stems: string[];
      other_exposed_stems: string[];
      overlap: string[];
      candidate_only: true;
      effective_strength_assessed: false;
      aggregation: 'union_of_parallel_candidates_not_consensus';
    }[];
  };
  astro: {
    positions_a: Record<PlanetName, PlanetPosition>;
    positions_b: Record<PlanetName, PlanetPosition>;
    orb_degrees: number;
    aspects: CrossAspect[];
    basis: 'actual_UTC_not_true_solar';
  };
  ziwei: {
    cross_views: {
      recipient: Side;
      own_spouse_palace: Palace;
      other_life_palace: Palace;
      same_branch: boolean;
      shared_star_names: string[];
    }[];
    compatibility_score: null;
  };
  basis: Record<
    Side,
    {
      primary: 'true_solar';
      comparisons: { basis: 'beijing_standard' | 'standard'; has_reported_difference: boolean }[];
    }
  >;
};
export type SynastrySample = ToolSample<'synastry', SynastryData>;
export type PublishedSample = WindowSample | SynastrySample;
export type WindowQuery = { purpose: Purpose; startDate: string; endDate: string; offset: number; limit: number };
export type WindowChoice = WindowQuery & {
  summary: { total: number; returned: number; first_rank: number | null; last_rank: number | null };
};
export type SynastryQuery = {
  a: 'ayuan' | 'xiaohe';
  b: 'ayuan' | 'xiaohe';
  kind: RelationKind;
  asOfDate: string;
  orbDegrees: number;
};
export type FreshConsent = { queryKey: string; a: true; b: true };
export type ToolRead<T> = { status: 'ready'; sample: T } | { status: 'unavailable'; message: string };
export type ToolPort = {
  /** One activation and request generation per mounted route/view. */
  createScope(): ToolPort;
  /** Invalidate pending reads and revoke this scope's active evidence. */
  reset(): void;
  windows: readonly WindowChoice[];
  windowSearch(query: WindowQuery, signal?: AbortSignal): Promise<ToolRead<WindowSample>>;
  synastry(
    query: SynastryQuery,
    consent: FreshConsent | undefined,
    signal?: AbortSignal,
  ): Promise<ToolRead<SynastrySample>>;
  resolveEvidence(ref: EvidenceRef): PublicEvidence | undefined;
};
