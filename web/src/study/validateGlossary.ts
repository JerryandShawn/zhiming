import type { GlossaryData, GlossarySource, GlossaryTerm, SourceRegistry, StudySystem, SystemCounts } from './types';
import {
  array,
  fields,
  integer,
  normalize,
  plainText,
  stringList,
  studyNeed,
  studySystems,
  unique,
} from './validation';
const sourceUrls = new Set([
  'https://gml.noaa.gov/grad/solcalc/calcdetails.html',
  'https://docs.iztro.com/posts/palace',
  'https://docs.iztro.com/learn/mutagen',
  'https://docs.iztro.com/learn/palace',
  'https://www.astro.com/swisseph/swephprg.htm',
]);
const sourceKinds = new Set([
  'project_implementation',
  'official_scientific_documentation',
  'official_implementation_documentation',
  'project_editorial',
  'public_domain_transcription',
  'primary_bibliographic_scan',
]);
function system(value: unknown): StudySystem {
  studyNeed(value === 'bazi' || value === 'ziwei' || value === 'astro' || value === 'tarot');
  return value;
}
function counts(value: unknown, expected: readonly number[]): SystemCounts {
  const row = fields(value, studySystems),
    result = { bazi: 0, ziwei: 0, astro: 0, tarot: 0 };
  studySystems.forEach((key, index) => {
    result[key] = integer(row[key]);
    studyNeed(result[key] === expected[index]);
  });
  return result;
}
function source(value: unknown): GlossarySource {
  const row = fields(value, [
    'source_id',
    'title',
    'kind',
    'url',
    'path',
    'locator',
    'verification_status',
    'edition_page_status',
  ]);
  const id = plainText(row.source_id),
    kind = plainText(row.kind),
    url = row.url === null ? null : plainText(row.url),
    path = row.path === null ? null : plainText(row.path);
  studyNeed(url !== null || path !== null);
  studyNeed(sourceKinds.has(kind));
  studyNeed(url === null || sourceUrls.has(url));
  studyNeed(
    path === null ||
      (/^(mingjing_core|hermes)\//.test(path) &&
        !path.includes('\\') &&
        path.split('/').every((part) => part && part !== '.' && part !== '..')),
  );
  let locator: string;
  if (id === 'project-tarot-editorial' && typeof row.locator === 'string') {
    plainText(row.locator.replace('<index>', ''));
    locator = row.locator;
  } else locator = plainText(row.locator);
  return {
    source_id: id,
    title: plainText(row.title),
    kind,
    url,
    path,
    locator,
    verification_status: plainText(row.verification_status),
    edition_page_status: plainText(row.edition_page_status),
  };
}
function term(value: unknown, registered: Set<string>): GlossaryTerm {
  const row = fields(value, [
    'term_id',
    'system',
    'term',
    'aliases',
    'definition_kind',
    'plain_explanation',
    'example',
    'sources',
    'school_differences',
    'pending_review',
  ]);
  const name = plainText(row.term_id),
    selectedSystem = system(row.system);
  studyNeed(name.startsWith(`${selectedSystem}-`));
  const sources = array(row.sources).map((value) => {
    const item = fields(value, ['source_id', 'locator', 'support_scope']);
    const id = plainText(item.source_id);
    studyNeed(registered.has(id));
    return { source_id: id, locator: plainText(item.locator), support_scope: plainText(item.support_scope) };
  });
  const differences = array(row.school_differences).map((value) => {
    const item = fields(value, ['school', 'note', 'source_ids']);
    const ids = stringList(item.source_ids);
    studyNeed(unique(ids) && ids.every((id) => registered.has(id)));
    return { school: plainText(item.school), note: plainText(item.note), source_ids: ids };
  });
  studyNeed(sources.length > 0 && unique(sources.map((item) => item.source_id)));
  return {
    term_id: name,
    system: selectedSystem,
    term: plainText(row.term),
    aliases: stringList(row.aliases),
    definition_kind: plainText(row.definition_kind),
    plain_explanation: plainText(row.plain_explanation),
    example: plainText(row.example),
    sources,
    school_differences: differences,
    pending_review: stringList(row.pending_review),
  };
}
export function readGlossary(
  termsValue: unknown,
  sourcesValue: unknown,
): { terms: GlossaryData; sources: SourceRegistry } {
  const sourceRoot = fields(sourcesValue, ['version', 'stage', 'sources']);
  studyNeed(sourceRoot.version === 'p8-glossary-sources-v1' && sourceRoot.stage === 'draft_source_registry');
  const sources = array(sourceRoot.sources).map(source);
  studyNeed(sources.length === 39 && unique(sources.map((item) => item.source_id)));
  const row = fields(termsValue, [
    'version',
    'stage',
    'language',
    'description',
    'systems',
    'planned_minimum_entries',
    'entry_count',
    'system_counts',
    'entries',
    'limits',
    'sources_file',
    'source_registry_version',
    'planned_system_minimums',
    'review_tag',
  ]);
  studyNeed(
    row.version === 'p8-glossary-v1' &&
      row.stage === 'draft_complete_200_for_review' &&
      row.language === 'zh-CN' &&
      row.review_tag === 'v1_ready_editorial_reviewed',
  );
  studyNeed(
    row.planned_minimum_entries === 200 &&
      row.entry_count === 212 &&
      row.sources_file === 'sources_v1.json' &&
      row.source_registry_version === sourceRoot.version,
  );
  const labels = fields(row.systems, studySystems);
  studyNeed(
    labels.bazi === '八字' && labels.ziwei === '紫微斗数' && labels.astro === '西方占星' && labels.tarot === '塔罗',
  );
  const entries = array(row.entries).map((value) => term(value, new Set(sources.map((item) => item.source_id))));
  studyNeed(entries.length === 212 && unique(entries.map((item) => item.term_id)));
  const names = new Set<string>();
  for (const item of entries)
    for (const value of [item.term, ...item.aliases]) {
      const key = JSON.stringify([item.system, normalize(value)]);
      studyNeed(!names.has(key));
      names.add(key);
    }
  const actual = studySystems.map((key) => entries.filter((item) => item.system === key).length);
  studyNeed(actual.every((count, index) => count === [72, 55, 50, 35][index]));
  const terms: GlossaryData = {
    version: 'p8-glossary-v1',
    stage: 'draft_complete_200_for_review',
    language: 'zh-CN',
    description: plainText(row.description),
    systems: { bazi: '八字', ziwei: '紫微斗数', astro: '西方占星', tarot: '塔罗' },
    planned_minimum_entries: 200,
    entry_count: 212,
    system_counts: counts(row.system_counts, [72, 55, 50, 35]),
    entries,
    limits: stringList(row.limits),
    sources_file: 'sources_v1.json',
    source_registry_version: 'p8-glossary-sources-v1',
    planned_system_minimums: counts(row.planned_system_minimums, [60, 55, 50, 35]),
    review_tag: 'v1_ready_editorial_reviewed',
  };
  return { terms, sources: { version: 'p8-glossary-sources-v1', stage: plainText(sourceRoot.stage), sources } };
}
