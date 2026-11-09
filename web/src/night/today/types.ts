export type DailySystem = 'bazi' | 'ziwei' | 'astro';
export type DailyEvidenceRef = { date: string; documentId: string; alias: string };
export type DailyEvidence = { ref: DailyEvidenceRef; label: string; summary: string };
export type DailyHighlight = {
  id: string;
  system: DailySystem;
  title: string;
  summary: string;
  school: string;
  refs: DailyEvidenceRef[];
};
export type DailyTransitView = {
  date: string;
  documentId: string;
  snapshotAtBeijing: string;
  basis: 'true_solar';
  hasBeijingComparison: boolean;
  dayGanzhi: string;
  dayTenGod: string;
  highlights: DailyHighlight[];
  evidence: DailyEvidence[];
  limits: string[];
  provenance: {
    sourceCommit: string;
    sourceFile: string;
    sourceSha256: string;
    mode: 'published-synthetic-engine';
    contractStatus: 'offset_normalized' | 'aligned';
    integrity: 'document-and-alias-digests-verified';
  };
};
export type TodayReadResult =
  { status: 'ready'; date: string; transit: DailyTransitView } | { status: 'empty'; date: string; message: string };
export type TodayPort = {
  availableDates: readonly string[];
  read(date: string, signal?: AbortSignal): Promise<TodayReadResult>;
  resolveEvidence(ref: DailyEvidenceRef): DailyEvidence | undefined;
};
export type TodayPortOptions = {
  delayMs?: number;
  wait?: (date: string, signal?: AbortSignal) => Promise<void>;
  failureDates?: readonly string[];
  emptyDates?: readonly string[];
  samples?: readonly unknown[];
};
export class TodayDataError extends Error {
  constructor(
    public code: 'INVALID_DATE' | 'INVALID_SAMPLE' | 'UNAVAILABLE',
    message: string,
  ) {
    super(message);
    this.name = 'TodayDataError';
  }
}
