import { kindLabels, purposes, sampleNames } from './port';
import { synastryInputSummary, windowInputSummary } from './inputSummary';
import type { SynastryQuery, WindowQuery } from './types';
import type {
  FieldIssue,
  InputValidation,
  InvalidInput,
  SynastryField,
  UnavailableInput,
  WindowField,
} from './inputValidationTypes';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const hasChoice = (choices: object, value: unknown) => typeof value === 'string' && Object.hasOwn(choices, value);
const ownFields = (input: Record<string, unknown>, names: readonly string[]) =>
  Object.fromEntries(names.map((name) => [name, Object.hasOwn(input, name) ? input[name] : undefined]));
const invalidShape = <Field extends string>(): InvalidInput<Field> => ({
  status: 'invalid',
  issues: [{ field: 'query', code: 'invalid-shape', message: '查询条件未能展开，请重新填写。' }],
});

/** Calendar dates only: never read the clock or local timezone. */
function dayIndex<Field extends string>(value: unknown, field: Field, issues: FieldIssue<Field>[]) {
  const issue = (code: FieldIssue<Field>['code'], message: string) => issues.push({ field, code, message });
  if (value === undefined || value === null || (typeof value === 'string' && !value.trim())) {
    issue('required', '请填写日期。');
    return;
  }
  if (typeof value !== 'string' || value.length !== 10 || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value)) {
    issue('invalid-date', '请使用完整的年、月、日日期。');
    return;
  }
  const [year, month, day] = value.split('-').map(Number);
  if (year < 1901 || year > 2099) {
    issue('date-out-of-range', '日期须在1901年至2099年之间。');
    return;
  }
  const milliseconds = Date.UTC(year, month - 1, day),
    date = new Date(milliseconds);
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    issue('invalid-date', '这个日历日期不存在，请重新核对。');
    return;
  }
  return milliseconds / 86400000;
}

/** Project only current viewer fields; auxiliary WindowChoice.summary is not authority. */
export function validateWindowInput(value: unknown): InputValidation<WindowQuery, WindowField> {
  if (!isRecord(value)) return invalidShape<WindowField>();
  const input = ownFields(value, ['purpose', 'startDate', 'endDate', 'offset', 'limit']);
  const issues: FieldIssue<WindowField>[] = [];
  if (typeof input.purpose !== 'string' || !purposes.some((purpose) => purpose === input.purpose))
    issues.push({ field: 'purpose', code: 'invalid-choice', message: '请选择签约、面试、搬家、出行、表白或开业。' });
  const start = dayIndex(input.startDate, 'startDate', issues),
    end = dayIndex(input.endDate, 'endDate', issues);
  if (start !== undefined && end !== undefined) {
    if (end < start) issues.push({ field: 'endDate', code: 'range-order', message: '结束日期不能早于起始日期。' });
    else if (end - start > 365)
      issues.push({ field: 'endDate', code: 'range-too-long', message: '含起止日期，最多查看366天。' });
  }
  // Match the published viewer: no invented safe-integer cap on a nonnegative offset.
  if (typeof input.offset !== 'number' || !Number.isInteger(input.offset) || input.offset < 0)
    issues.push({ field: 'offset', code: 'invalid-offset', message: '分页偏移须为零或正整数。' });
  if (typeof input.limit !== 'number' || !Number.isInteger(input.limit) || input.limit < 1 || input.limit > 31)
    issues.push({ field: 'limit', code: 'invalid-limit', message: '每页天数须为1至31之间的整数。' });
  if (issues.length) return { status: 'invalid', issues };
  const query = {
    purpose: input.purpose,
    startDate: input.startDate,
    endDate: input.endDate,
    offset: input.offset,
    limit: input.limit,
  } as WindowQuery;
  return {
    status: 'valid',
    query,
    coverage: 'query-fields-only',
    summary: windowInputSummary(query, end! - start! + 1),
  };
}

/** Query validation is independent of fresh display consent and backend owner authority. */
export function validateSynastryInput(value: unknown): InputValidation<SynastryQuery, SynastryField> {
  if (!isRecord(value)) return invalidShape<SynastryField>();
  const input = ownFields(value, ['a', 'b', 'kind', 'asOfDate', 'orbDegrees']);
  const issues: FieldIssue<SynastryField>[] = [];
  for (const side of ['a', 'b'] as const)
    if (!hasChoice(sampleNames, input[side]))
      issues.push({ field: side, code: 'invalid-choice', message: `请选择${side.toUpperCase()}方合成对象。` });
  if (hasChoice(sampleNames, input.a) && hasChoice(sampleNames, input.b) && input.a === input.b)
    issues.push({ field: 'b', code: 'same-object', message: '请选择与A方不同的合成对象。' });
  if (!hasChoice(kindLabels, input.kind))
    issues.push({ field: 'kind', code: 'invalid-choice', message: '请选择亲密关系、朋友相处或合作。' });
  dayIndex(input.asOfDate, 'asOfDate', issues);
  if (
    typeof input.orbDegrees !== 'number' ||
    !Number.isFinite(input.orbDegrees) ||
    input.orbDegrees < 0 ||
    input.orbDegrees > 10
  )
    issues.push({ field: 'orbDegrees', code: 'invalid-orb', message: '容许度须为0至10度之间的数值。' });
  if (issues.length) return { status: 'invalid', issues };
  const query = {
    a: input.a,
    b: input.b,
    kind: input.kind,
    asOfDate: input.asOfDate,
    orbDegrees: input.orbDegrees,
  } as SynastryQuery;
  return {
    status: 'valid',
    query,
    coverage: 'query-fields-only',
    summary: synastryInputSummary(query),
  };
}

/** Call only after the existing port returns unavailable; never infer availability from shape. */
export function markInputUnavailable<Query extends object, Field extends string>(
  checked: InputValidation<Query, Field>,
): InvalidInput<Field> | UnavailableInput<Query> {
  if (checked.status === 'invalid') return checked;
  return {
    ...checked,
    query: { ...checked.query },
    summary: checked.summary.map((item) => ({ ...item })),
    status: 'unavailable',
    code: 'sample-unavailable',
    message: '条件格式已核对，但当前没有对应的已发布样例；尚未接入实时计算。',
  };
}
