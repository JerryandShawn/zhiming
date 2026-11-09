export const STUDY_COMMIT = '0f1d6e676259b961819de4da5ea3f343d58dbe98';
export const studySystems = ['bazi', 'ziwei', 'astro', 'tarot'] as const;
export class StudyDataError extends Error {
  constructor(public code: 'INVALID_DATA' | 'INVALID_QUERY' | 'DISPOSED' = 'INVALID_DATA') {
    super(
      code === 'INVALID_QUERY'
        ? '请重新核对查询条件。'
        : code === 'DISPOSED'
          ? '此研习页面已关闭，请重新打开。'
          : '样例依据已更新，待重新复核。',
    );
    this.name = 'StudyDataError';
  }
}
export function studyNeed(condition: unknown): asserts condition {
  if (!condition) throw new StudyDataError();
}
export const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
export const unique = (values: readonly string[]) => new Set(values).size === values.length;
export const normalize = (value: string) =>
  value.normalize('NFKC').toLocaleLowerCase('en-US').trim().replace(/\s+/gu, ' ');
export function fields(value: unknown, required: readonly string[], optional: readonly string[] = []) {
  studyNeed(
    record(value) &&
      required.every((key) => Object.hasOwn(value, key)) &&
      Object.keys(value).every((key) => required.includes(key) || optional.includes(key)),
  );
  return value;
}
export function plainText(value: unknown): string {
  studyNeed(
    typeof value === 'string' &&
      value.trim().length > 0 &&
      value.length <= 16000 &&
      !value.includes('<') &&
      !/[\p{Cc}\p{Cf}]/u.test(value.replace(/[\n\t]/g, '')),
  );
  return value;
}
export function stringList(value: unknown): string[] {
  studyNeed(Array.isArray(value));
  return value.map(plainText);
}
export function integer(value: unknown, minimum = 0, maximum = 2000000): number {
  studyNeed(typeof value === 'number' && Number.isSafeInteger(value) && value >= minimum && value <= maximum);
  return value;
}
export function hex(value: unknown, length = 64): string {
  studyNeed(typeof value === 'string' && new RegExp(`^[a-f0-9]{${length}}$`).test(value));
  return value;
}
export function identifier(value: unknown, prefix: 'doc' | 'demo-claim'): string {
  const text = plainText(value);
  studyNeed(new RegExp(`^${prefix}-[a-f0-9]{64}$`).test(text));
  return text;
}
export function array(value: unknown): unknown[] {
  studyNeed(Array.isArray(value));
  return value;
}
