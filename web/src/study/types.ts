export type StudySystem = 'bazi' | 'ziwei' | 'astro' | 'tarot';
export type LearningSystem = Exclude<StudySystem, 'tarot'>;
export type SystemCounts = Record<StudySystem, number>;
export type GlossaryTerm = {
  term_id: string;
  system: StudySystem;
  term: string;
  aliases: string[];
  definition_kind: string;
  plain_explanation: string;
  example: string;
  sources: { source_id: string; locator: string; support_scope: string }[];
  school_differences: { school: string; note: string; source_ids: string[] }[];
  pending_review: string[];
};
export type GlossarySource = {
  source_id: string;
  title: string;
  kind: string;
  url: string | null;
  path: string | null;
  locator: string;
  verification_status: string;
  edition_page_status: string;
};
export type SourceRegistry = { version: 'p8-glossary-sources-v1'; stage: string; sources: GlossarySource[] };
export type GlossaryData = {
  version: 'p8-glossary-v1';
  stage: 'draft_complete_200_for_review';
  language: 'zh-CN';
  description: string;
  systems: Record<StudySystem, string>;
  planned_minimum_entries: 200;
  entry_count: 212;
  system_counts: SystemCounts;
  entries: GlossaryTerm[];
  limits: string[];
  sources_file: 'sources_v1.json';
  source_registry_version: 'p8-glossary-sources-v1';
  planned_system_minimums: SystemCounts;
  review_tag: 'v1_ready_editorial_reviewed';
};
export type LearningRef = { document_id: string; alias: string; claim_id: string };
export type StudyEvidenceRef = LearningRef & { sample_id: string };
export type LearningSource = { title: string; status: string; url?: string; locator?: string };
export type LearningEvidence = LearningRef & {
  kind: 'fact' | 'rule';
  value_sha256: string;
  summary: string;
  basis: 'true_solar' | 'standard' | 'beijing_standard' | 'actual_UTC';
  evidence_refs?: LearningRef[];
  school?: string;
  sources?: LearningSource[];
};
export type LearningCard = {
  point_id: string;
  kind: 'orientation' | 'matched_condition' | 'boundary';
  title: string;
  text: string;
  school: string;
  sources: LearningSource[];
  c_aliases: string[];
  r_aliases: string[];
  citations: string;
  evidence_refs: LearningRef[];
  limits: string[];
};
export type LearningSample = {
  format: 'frontend-learning-sample-v1';
  sample_id: string;
  system: LearningSystem;
  status: 'learning_only' | 'insufficient_evidence';
  cards: LearningCard[];
  evidence: LearningEvidence[];
  effects: { model_calls: 0; writes: 0; alias_registry: 'reuse_input_projection_no_registration' };
  limits: string[];
  provenance: {
    source_commit: string;
    mode: 'published-synthetic-snapshot';
    source_files: { path: string; sha256: string }[];
    source_document_ids: string[];
    integrity: 'original-documents-pointer-alias-claim-branch-and-card-templates-verified';
  };
};
export type StudyMetadata = {
  source_commit: string;
  mode: 'static-educational-only';
  glossary: Pick<GlossaryData, 'version' | 'stage' | 'review_tag' | 'entry_count' | 'system_counts' | 'limits'> & {
    source_count: number;
    source_stage: string;
  };
  learning: {
    sample_id: string;
    system: LearningSystem;
    status: LearningSample['status'];
    card_count: number;
    limits: string[];
  }[];
  effects: { model_calls: 0; business_writes: 0; progress_api: 'unavailable' };
};
export type TermSummary = Pick<GlossaryTerm, 'term_id' | 'system' | 'term' | 'aliases'>;
export type TermDetail = { term: GlossaryTerm; sources: GlossarySource[]; metadata: StudyMetadata['glossary'] };
export type TermResolution =
  | { status: 'unavailable'; message: string }
  | { status: 'resolved'; term: TermSummary }
  | { status: 'ambiguous'; candidates: TermSummary[] };
export type StudyRead<T> = { status: 'ready'; value: T } | { status: 'unavailable'; message: string };
export type SearchQuery = { text: string; system?: StudySystem };
export interface StudyScope {
  metadata(): StudyMetadata;
  reset(): void;
  dispose(): void;
  search(query: SearchQuery, signal?: AbortSignal): Promise<StudyRead<TermSummary[]>>;
  resolveTerm(label: string, system?: StudySystem, signal?: AbortSignal): Promise<TermResolution>;
  readTerm(termId: string, signal?: AbortSignal): Promise<StudyRead<TermDetail>>;
  readLearning(sampleId: string, signal?: AbortSignal): Promise<StudyRead<LearningSample>>;
  resolveEvidence(ref: StudyEvidenceRef): LearningEvidence | undefined;
}
export interface StudyPort {
  metadata(): StudyMetadata;
  createScope(): StudyScope;
  dispose(): void;
}
export type StudyBundle = { terms: GlossaryData; sources: SourceRegistry; learning: LearningSample[] };
