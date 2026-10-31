import { validDate } from '../../calendar/data';
import { TodayDataError, type DailyEvidenceRef, type DailyTransitView } from './types';

const sourceCommit = 'b51470b8e32eb72b8151df4eca7eee2e1584bee5';
const gods = ['比肩', '劫财', '食神', '伤官', '正财', '偏财', '正官', '七杀', '正印', '偏印'];
function requireValue(condition: unknown): asserts condition {
  if (!condition) throw new TodayDataError('INVALID_SAMPLE', '这份流日样例尚未通过公开投影核对。');
}
function record(value: unknown): Record<string, unknown> {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value));
  return value as Record<string, unknown>;
}
function keys(value: unknown, expected: string[]): Record<string, unknown> {
  const result = record(value);
  requireValue(Object.keys(result).sort().join('|') === [...expected].sort().join('|'));
  return result;
}
function text(value: unknown, max = 400): value is string {
  return (
    typeof value === 'string' &&
    value.length > 0 &&
    value.length <= max &&
    Array.from(value).every((character) => character.codePointAt(0)! >= 32)
  );
}
export function assertTodayDate(value: unknown): asserts value is string {
  if (typeof value !== 'string' || !validDate(value) || value < '1901-01-01' || value > '2099-12-31')
    throw new TodayDataError('INVALID_DATE', '请使用1901至2099年的有效公历日期。');
}
export function dailyEvidenceKey(ref: DailyEvidenceRef): string {
  return JSON.stringify([ref.date, ref.documentId, ref.alias]);
}
function evidenceRef(value: unknown, date: string, documentId: string): DailyEvidenceRef {
  const ref = keys(value, ['date', 'documentId', 'alias']);
  requireValue(ref.date === date && ref.documentId === documentId);
  requireValue(typeof ref.alias === 'string' && /^[cr][1-9]\d*$/.test(ref.alias));
  return { date, documentId, alias: ref.alias };
}
export function freezeDaily<T>(value: T): T {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freezeDaily);
    Object.freeze(value);
  }
  return value;
}

/** Accept only the offline public format; raw P8/owner/profile objects cannot cross this boundary. */
export function projectPublicDailySample(value: unknown): DailyTransitView {
  const row = keys(value, [
    'date',
    'documentId',
    'snapshotAtBeijing',
    'basis',
    'hasBeijingComparison',
    'dayGanzhi',
    'dayTenGod',
    'highlights',
    'evidence',
    'limits',
    'provenance',
  ]);
  assertTodayDate(row.date);
  requireValue(typeof row.documentId === 'string' && /^tool-[0-9a-f]{64}$/.test(row.documentId));
  requireValue(row.snapshotAtBeijing === `${row.date}T12:00:00+08:00` && row.basis === 'true_solar');
  requireValue(typeof row.hasBeijingComparison === 'boolean');
  requireValue(
    typeof row.dayGanzhi === 'string' && /^[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]$/.test(row.dayGanzhi),
  );
  requireValue(typeof row.dayTenGod === 'string' && gods.includes(row.dayTenGod));
  const provenance = keys(row.provenance, [
    'sourceCommit',
    'sourceFile',
    'sourceSha256',
    'mode',
    'contractStatus',
    'integrity',
  ]);
  requireValue(
    provenance.sourceCommit === sourceCommit &&
      provenance.sourceFile === `docs/v4/contracts/samples/daily_transit/ayuan_${row.date}.json`,
  );
  requireValue(typeof provenance.sourceSha256 === 'string' && /^[0-9a-f]{64}$/.test(provenance.sourceSha256));
  requireValue(
    provenance.mode === 'published-synthetic-engine' && provenance.integrity === 'document-and-alias-digests-verified',
  );
  requireValue(['offset_normalized', 'aligned'].includes(String(provenance.contractStatus)));
  requireValue(Array.isArray(row.evidence) && row.evidence.length > 0 && row.evidence.length <= 100);
  const evidence = new Set<string>();
  for (const item of row.evidence) {
    const entry = keys(item, ['ref', 'label', 'summary']);
    const ref = evidenceRef(entry.ref, row.date, row.documentId),
      key = dailyEvidenceKey(ref);
    requireValue(!evidence.has(key) && text(entry.summary) && text(entry.label, 60));
    requireValue(entry.label === `${ref.alias} · ${ref.alias.startsWith('r') ? '规则依据' : '盘面依据'}`);
    evidence.add(key);
  }
  requireValue(Array.isArray(row.highlights) && row.highlights.length === 3);
  const used = new Set<string>(),
    systems = new Set<string>();
  for (const item of row.highlights) {
    const entry = keys(item, ['id', 'system', 'title', 'summary', 'school', 'refs']);
    requireValue(['bazi', 'ziwei', 'astro'].includes(String(entry.system)) && !systems.has(String(entry.system)));
    requireValue(typeof entry.id === 'string' && new RegExp(`^daily\\.${entry.system}\\.[a-z0-9._-]+$`).test(entry.id));
    requireValue(text(entry.title, 60) && text(entry.summary) && text(entry.school, 100));
    requireValue(Array.isArray(entry.refs) && entry.refs.length > 1);
    for (const value of entry.refs) {
      const ref = evidenceRef(value, row.date, row.documentId),
        key = dailyEvidenceKey(ref);
      requireValue(evidence.has(key));
      used.add(key);
    }
    systems.add(String(entry.system));
  }
  requireValue(evidence.size === used.size);
  requireValue(Array.isArray(row.limits) && row.limits.length > 0 && row.limits.every((item) => text(item)));
  return freezeDaily(structuredClone(row) as unknown as DailyTransitView);
}
