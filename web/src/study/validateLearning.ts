import type {
  LearningCard,
  LearningEvidence,
  LearningRef,
  LearningSample,
  LearningSource,
  LearningSystem,
} from './types';
import { array, fields, hex, identifier, plainText, stringList, studyNeed, STUDY_COMMIT, unique } from './validation';
const urls = new Set([
  'https://zh.wikisource.org/wiki/三命通會/卷二#论人元司事',
  'https://docs.iztro.com/posts/palace',
  'https://www.astro.com/swisseph/swephprg.htm',
  'https://donglishuzhai.net/chapter/3722.html',
]);
export const sourceShas: Record<string, string> = {
  'learning-ayuan-bazi.json': '3f4ad34140fed9a80b2899c75fe9c736dbfb6a0a40e27bd662cd5d5f52f5b497',
  'ayuan_bazi.json': 'fe11a98184a296417f927d16cc57ee3ba664d77865393b9f20b2f867b0ea313b',
  'learning-ayuan-ziwei.json': 'f6ec9b9709afa2266e6caebbc306d16eb9f33c970a6b5cc85aa13693b3ec90a0',
  'ayuan_ziwei.json': '306b1f368a310b6963187b983245e7c2d492b1ef59fbf99f8c5f28c3cd19571e',
  'learning-ayuan-astro.json': '1731e7bdeb4d06b29e7bcff3c9bcab0b2c306ebdac57e9e78ee9acf0bcf847a4',
  'ayuan_astro.json': '35a0bb10dce92aac401a49905b6c0d08fb127179de92418c79166c5ad8ea7f7c',
};
export function learningRef(value: unknown): LearningRef {
  const row = fields(value, ['document_id', 'alias', 'claim_id']);
  const alias = plainText(row.alias);
  studyNeed(/^[cr][1-9][0-9]*$/.test(alias));
  return { document_id: identifier(row.document_id, 'doc'), alias, claim_id: identifier(row.claim_id, 'demo-claim') };
}
const refKey = (ref: LearningRef) => JSON.stringify([ref.document_id, ref.alias, ref.claim_id]);
function source(value: unknown): LearningSource {
  const row = fields(value, ['title', 'status'], ['url', 'locator']);
  const url = row.url === undefined ? undefined : plainText(row.url);
  studyNeed(url === undefined || urls.has(url));
  return {
    title: plainText(row.title),
    status: plainText(row.status),
    ...(url ? { url } : {}),
    ...(row.locator === undefined ? {} : { locator: plainText(row.locator) }),
  };
}
function card(value: unknown): LearningCard {
  const row = fields(value, [
    'point_id',
    'kind',
    'title',
    'text',
    'school',
    'sources',
    'c_aliases',
    'r_aliases',
    'citations',
    'evidence_refs',
    'limits',
  ]);
  const kind = row.kind;
  studyNeed(kind === 'orientation' || kind === 'matched_condition' || kind === 'boundary');
  const c = stringList(row.c_aliases),
    rules = stringList(row.r_aliases);
  studyNeed(
    c.length > 0 &&
      c.every((id) => /^c[1-9][0-9]*$/.test(id)) &&
      rules.every((id) => /^r[1-9][0-9]*$/.test(id)) &&
      unique([...c, ...rules]),
  );
  const references = array(row.evidence_refs).map(learningRef),
    names = [...c, ...rules];
  studyNeed(references.length === names.length && references.every((ref, index) => ref.alias === names[index]));
  studyNeed(row.citations === names.map((name) => `〔${name}〕`).join(''));
  return {
    point_id: plainText(row.point_id),
    kind,
    title: plainText(row.title),
    text: plainText(row.text),
    school: plainText(row.school),
    sources: array(row.sources).map(source),
    c_aliases: c,
    r_aliases: rules,
    citations: plainText(row.citations),
    evidence_refs: references,
    limits: stringList(row.limits),
  };
}
function evidence(value: unknown): LearningEvidence {
  const row = fields(
    value,
    ['document_id', 'alias', 'claim_id', 'kind', 'value_sha256', 'summary', 'basis'],
    ['evidence_refs', 'school', 'sources'],
  );
  const ref = learningRef({ document_id: row.document_id, alias: row.alias, claim_id: row.claim_id });
  const kind = row.kind,
    basis = row.basis;
  studyNeed(kind === 'fact' || kind === 'rule');
  studyNeed(basis === 'true_solar' || basis === 'standard' || basis === 'beijing_standard' || basis === 'actual_UTC');
  studyNeed((kind === 'fact') === ref.alias.startsWith('c'));
  if (kind === 'fact')
    studyNeed(row.evidence_refs === undefined && row.school === undefined && row.sources === undefined);
  const common: LearningEvidence = {
    ...ref,
    kind,
    basis,
    value_sha256: hex(row.value_sha256),
    summary: plainText(row.summary),
  };
  return kind === 'fact'
    ? common
    : {
        ...common,
        evidence_refs: array(row.evidence_refs).map(learningRef),
        school: plainText(row.school),
        sources: array(row.sources).map(source),
      };
}
function provenance(value: unknown, system: LearningSystem): LearningSample['provenance'] {
  const row = fields(value, ['source_commit', 'mode', 'source_files', 'source_document_ids', 'integrity']);
  studyNeed(
    row.source_commit === STUDY_COMMIT &&
      row.mode === 'published-synthetic-snapshot' &&
      row.integrity === 'original-documents-pointer-alias-claim-branch-and-card-templates-verified',
  );
  const expected = [`learning-ayuan-${system}.json`, `ayuan_${system}.json`];
  const files = array(row.source_files).map((value, index) => {
    const file = fields(value, ['path', 'sha256']);
    studyNeed(
      index < expected.length &&
        file.path === `docs/v4/contracts/samples/${expected[index]}` &&
        file.sha256 === sourceShas[expected[index]],
    );
    return { path: plainText(file.path), sha256: hex(file.sha256) };
  });
  const documents = array(row.source_document_ids).map((id) => identifier(id, 'doc'));
  studyNeed(files.length === 2 && unique(documents) && documents.length === (system === 'astro' ? 4 : 1));
  return {
    source_commit: STUDY_COMMIT,
    mode: 'published-synthetic-snapshot',
    source_files: files,
    source_document_ids: documents,
    integrity: 'original-documents-pointer-alias-claim-branch-and-card-templates-verified',
  };
}
export function readLearning(value: unknown, system: LearningSystem): LearningSample {
  studyNeed(system === 'bazi' || system === 'ziwei' || system === 'astro');
  const row = fields(value, [
    'format',
    'sample_id',
    'system',
    'status',
    'cards',
    'evidence',
    'effects',
    'limits',
    'provenance',
  ]);
  studyNeed(
    row.format === 'frontend-learning-sample-v1' && row.sample_id === `ayuan-${system}` && row.system === system,
  );
  const cards = array(row.cards).map(card),
    facts = array(row.evidence).map(evidence),
    origins = provenance(row.provenance, system);
  const status = row.status;
  studyNeed(status === 'learning_only' || status === 'insufficient_evidence');
  studyNeed(
    (status === 'learning_only') === cards.length > 0 &&
      unique(cards.map((item) => item.point_id)) &&
      unique(facts.map((item) => item.alias)),
  );
  const available = new Set(facts.map(refKey));
  studyNeed(facts.every((item) => origins.source_document_ids.includes(item.document_id)));
  studyNeed(cards.every((item) => item.evidence_refs.every((ref) => available.has(refKey(ref)))));
  studyNeed(
    facts.every(
      (item) =>
        !item.evidence_refs ||
        item.evidence_refs.every((ref) => ref.alias.startsWith('c') && available.has(refKey(ref))),
    ),
  );
  const effects = fields(row.effects, ['model_calls', 'writes', 'alias_registry']);
  studyNeed(
    effects.model_calls === 0 &&
      effects.writes === 0 &&
      effects.alias_registry === 'reuse_input_projection_no_registration',
  );
  return {
    format: 'frontend-learning-sample-v1',
    sample_id: `ayuan-${system}`,
    system,
    status,
    cards,
    evidence: facts,
    effects: { model_calls: 0, writes: 0, alias_registry: 'reuse_input_projection_no_registration' },
    limits: stringList(row.limits),
    provenance: origins,
  };
}
