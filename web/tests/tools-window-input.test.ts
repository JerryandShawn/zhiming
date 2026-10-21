import { describe, expect, it } from 'vitest';
import { markInputUnavailable, validateWindowInput } from '../src/tools/inputValidation';

const query = { purpose: '签约', startDate: '2026-10-21', endDate: '2026-10-27', offset: 0, limit: 31 };
const invalidIssue = (value: unknown, field: string, code?: string) => {
  const result = validateWindowInput(value);
  expect(result.status).toBe('invalid');
  if (result.status === 'invalid')
    expect(result.issues).toContainEqual(expect.objectContaining({ field, ...(code ? { code } : {}) }));
  return result;
};

describe('window viewer query validation, not natal or engine validation', () => {
  it.each(['签约', '面试', '搬家', '出行', '表白', '开业'])(
    'accepts exact purpose %s without pretending a sample exists',
    (purpose) => {
      expect(validateWindowInput({ ...query, purpose })).toMatchObject({
        status: 'valid',
        query: { purpose },
        coverage: 'query-fields-only',
      });
    },
  );

  it.each(['1901-01-01', '2000-02-29', '2096-02-29', '2099-12-31'])(
    'accepts real supported calendar date %s',
    (date) => {
      expect(validateWindowInput({ ...query, startDate: date, endDate: date })).toMatchObject({ status: 'valid' });
    },
  );

  it.each([
    '2026-02-29',
    '2000-02-30',
    '2026-04-31',
    '2026-13-01',
    '2026-00-01',
    '2026-10-00',
    '2026-10-32',
    '２０２６-10-21',
    '2026-1-01',
    '2026-10-21T00:00:00Z',
    ' 2026-10-21',
    '2026-10-21 ',
    '2026/10/21',
    '2026-10-21\n',
    true,
    42,
  ])('rejects malformed start date %s', (date) => {
    invalidIssue({ ...query, startDate: date }, 'startDate', 'invalid-date');
  });

  it.each(['1900-12-31', '2100-01-01'])('rejects date outside declared year range %s', (date) => {
    invalidIssue({ ...query, startDate: date }, 'startDate', 'date-out-of-range');
  });

  it.each([undefined, null, '', ' '])('associates an empty date with its own field %s', (date) => {
    invalidIssue({ ...query, endDate: date }, 'endDate', 'required');
  });

  it.each([
    ['2024-01-01', '2024-12-31', '366天'],
    ['2026-01-01', '2027-01-01', '366天'],
    ['2026-03-08', '2026-03-08', '1天'],
  ])('counts inclusive UTC calendar days %s through %s', (startDate, endDate, days) => {
    const result = validateWindowInput({ ...query, startDate, endDate });
    expect(result.status).toBe('valid');
    if (result.status === 'valid')
      expect(result.summary).toContainEqual({ id: 'days', label: '含起止日期', value: days });
  });

  it('rejects 367 inclusive days and reversed dates on the end field', () => {
    invalidIssue({ ...query, startDate: '2024-01-01', endDate: '2025-01-01' }, 'endDate', 'range-too-long');
    invalidIssue({ ...query, startDate: '2026-10-27', endDate: '2026-10-21' }, 'endDate', 'range-order');
  });

  it.each([true, false, '0', undefined, null, NaN, Infinity, -Infinity, -1, 0.5])(
    'rejects invalid offset %s',
    (offset) => {
      invalidIssue({ ...query, offset }, 'offset', 'invalid-offset');
    },
  );

  it.each([0, -0, 7, 1e20])('retains existing nonnegative integer offset semantics %s', (offset) => {
    expect(validateWindowInput({ ...query, offset })).toMatchObject({ status: 'valid', query: { offset } });
  });

  it.each([true, '1', null, NaN, Infinity, 0, 32, 1.5])('rejects invalid page limit %s', (limit) => {
    invalidIssue({ ...query, limit }, 'limit', 'invalid-limit');
  });

  it.each([1, 31])('allows page limit boundary %s', (limit) => {
    expect(validateWindowInput({ ...query, limit })).toMatchObject({ status: 'valid' });
  });

  it.each(['签約', ' 签约', '签约 ', '', '__proto__', null])(
    'does not normalize an unsupported purpose %s',
    (purpose) => {
      invalidIssue({ ...query, purpose }, 'purpose', 'invalid-choice');
    },
  );

  it.each([null, undefined, [], false, 'query', 4])('returns one safe shape issue for non-record %s', (value) => {
    const result = invalidIssue(value, 'query', 'invalid-shape');
    if (result.status === 'invalid') expect(result.issues).toHaveLength(1);
  });

  it('retains WindowChoice compatibility without reading or exporting helper or extra fields', () => {
    const input = Object.freeze(
      Object.defineProperty({ ...query, birth: { hidden: 'not-checked' } }, 'summary', {
        get() {
          throw new Error('must not read');
        },
      }),
    );
    const result = validateWindowInput(input);
    expect(result.status).toBe('valid');
    if (result.status === 'valid') {
      expect(result.query).toEqual(query);
      result.query.startDate = '2026-10-22';
      expect(input.startDate).toBe(query.startDate);
      expect(result.query).not.toHaveProperty('birth');
    }
  });

  it('does not inherit required fields from a prototype', () => {
    invalidIssue(Object.create(query), 'purpose', 'invalid-choice');
    expect(validateWindowInput(Object.assign(Object.create(null), query))).toMatchObject({ status: 'valid' });
  });

  it('keeps valid but unpublished conditions separate from field errors', () => {
    const checked = validateWindowInput({ ...query, purpose: '搬家' });
    const unavailable = markInputUnavailable(checked);
    expect(unavailable).toMatchObject({
      status: 'unavailable',
      code: 'sample-unavailable',
      coverage: 'query-fields-only',
      query: { purpose: '搬家' },
    });
    expect(unavailable).not.toHaveProperty('issues');
    const invalid = validateWindowInput({ ...query, endDate: '' });
    expect(markInputUnavailable(invalid)).toBe(invalid);
  });
});
