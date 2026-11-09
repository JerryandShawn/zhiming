import type { LearningSystem } from './types';
import { array, fields, hex, integer, studyNeed, STUDY_COMMIT, unique } from './validation';
export type OutputEntry = { file: string; sha256: string; bytes: number };
export type LearningEntry = OutputEntry & {
  system: LearningSystem;
  sample_id: string;
  cards: number;
  evidence: number;
};
const inputShas: Record<string, string> = {
  'mingjing_core/knowledge/p8_glossary/terms_v1.json':
    'b1005b6e1748c7cb0dc680ff0b43ea93c4e54819b3a23da49f8e5b3a0cd197b3',
  'mingjing_core/knowledge/p8_glossary/sources_v1.json':
    'a781219cbf9f364ca6fbe89e82ce5e4640a99851a29bc65988b7ddcfcf67f1f1',
  'docs/v4/contracts/glossary.schema.json': '42555c9db476bcce4f14c5e310b6bcae376c50e25c94abf01dade72cb40d5cc4',
  'docs/v4/contracts/glossary_sources.schema.json': 'cc7a23f9fecceb51918a01b6e6145342eff63a625611634ca2cc5e93084fd084',
};
function output(value: unknown, files: readonly string[]): OutputEntry {
  const row = fields(value, ['file', 'sha256', 'bytes']);
  studyNeed(typeof row.file === 'string' && files.includes(row.file));
  return { file: row.file, sha256: hex(row.sha256), bytes: integer(row.bytes, 1) };
}
export function glossaryManifest(value: unknown): OutputEntry[] {
  const row = fields(value, [
    'schema',
    'source_ref',
    'source_commit',
    'mode',
    'selection',
    'model_calls',
    'business_writes',
    'inputs',
    'entries',
    'entry_count',
    'system_counts',
    'source_count',
    'stage',
    'review_tag',
    'source_urls_fetched',
    'source_paths_checked_in_git_tree',
    'rendering',
  ]);
  studyNeed(
    row.schema === 'frontend-study-glossary-export-v1' &&
      row.source_ref === 'origin/v4/p8-calc' &&
      row.source_commit === STUDY_COMMIT &&
      row.mode === 'static-educational-only' &&
      row.selection === 'frozen-audited-commit',
  );
  studyNeed(
    row.model_calls === 0 &&
      row.business_writes === 0 &&
      row.source_urls_fetched === 0 &&
      row.source_paths_checked_in_git_tree === true &&
      row.rendering === 'plain_text_only_no_html_execution_no_current_user_evidence',
  );
  studyNeed(
    row.entry_count === 212 &&
      row.source_count === 39 &&
      row.stage === 'draft_complete_200_for_review' &&
      row.review_tag === 'v1_ready_editorial_reviewed',
  );
  const counts = fields(row.system_counts, ['bazi', 'ziwei', 'astro', 'tarot']);
  studyNeed(counts.bazi === 72 && counts.ziwei === 55 && counts.astro === 50 && counts.tarot === 35);
  const inputs = array(row.inputs).map((value) => {
    const item = fields(value, ['path', 'sha256', 'bytes']);
    studyNeed(
      typeof item.path === 'string' && Object.hasOwn(inputShas, item.path) && item.sha256 === inputShas[item.path],
    );
    integer(item.bytes, 1);
    return item.path;
  });
  studyNeed(inputs.length === 4 && unique(inputs));
  const entries = array(row.entries).map((value) => output(value, ['terms_v1.json', 'sources_v1.json']));
  studyNeed(entries.length === 2 && unique(entries.map((item) => item.file)));
  return entries;
}
export function learningManifest(value: unknown): LearningEntry[] {
  const row = fields(value, ['schema', 'source_commit', 'synthetic_only', 'model_calls', 'writes', 'entries']);
  studyNeed(
    row.schema === 'frontend-learning-export-v1' &&
      row.source_commit === STUDY_COMMIT &&
      row.synthetic_only === true &&
      row.model_calls === 0 &&
      row.writes === 0,
  );
  const entries = array(row.entries).map((value): LearningEntry => {
    const item = fields(value, ['file', 'system', 'sample_id', 'cards', 'evidence', 'sha256', 'bytes']),
      system = item.system;
    studyNeed(system === 'bazi' || system === 'ziwei' || system === 'astro');
    const file = `learning-ayuan-${system}.json`,
      sample_id = `ayuan-${system}`,
      cards = system === 'bazi' ? 11 : 2,
      evidence = system === 'bazi' ? 23 : 5;
    studyNeed(item.file === file && item.sample_id === sample_id && item.cards === cards && item.evidence === evidence);
    return { file, system, sample_id, cards, evidence, sha256: hex(item.sha256), bytes: integer(item.bytes, 1) };
  });
  studyNeed(entries.length === 3 && unique(entries.map((item) => item.system)));
  return entries;
}
