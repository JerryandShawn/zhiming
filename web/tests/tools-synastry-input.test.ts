import { afterEach, describe, expect, it, vi } from 'vitest';
import { markInputUnavailable, validateSynastryInput, validateWindowInput } from '../src/tools/inputValidation';

const query = { a: 'ayuan', b: 'xiaohe', kind: 'romantic', asOfDate: '2026-10-21', orbDegrees: 6 };
const invalidIssue = (value: unknown, field: string, code?: string) => {
  const result = validateSynastryInput(value);
  expect(result.status).toBe('invalid');
  if (result.status === 'invalid')
    expect(result.issues).toContainEqual(expect.objectContaining({ field, ...(code ? { code } : {}) }));
  return result;
};
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('synastry viewer fields without consent or natal authority', () => {
  it.each(['romantic', 'friendship', 'collaboration'])(
    'accepts current kind %s independently of sample coverage',
    (kind) => {
      expect(validateSynastryInput({ ...query, kind })).toMatchObject({
        status: 'valid',
        query: { kind },
        coverage: 'query-fields-only',
      });
    },
  );

  it.each([0, -0, 0.1, 6, 10])('accepts finite inclusive orb %s', (orbDegrees) => {
    expect(validateSynastryInput({ ...query, orbDegrees })).toMatchObject({ status: 'valid', query: { orbDegrees } });
  });

  it.each([true, false, '6', undefined, null, NaN, Infinity, -Infinity, -0.1, 10.1])(
    'rejects orb %s without defaulting or coercion',
    (orbDegrees) => {
      invalidIssue({ ...query, orbDegrees }, 'orbDegrees', 'invalid-orb');
    },
  );

  it.each(['2026-02-29', '２０２６-10-21', '2026-10-21\n', '2026-10-21T00:00:00+08:00'])(
    'rejects invalid as-of calendar date %s',
    (asOfDate) => {
      invalidIssue({ ...query, asOfDate }, 'asOfDate', 'invalid-date');
    },
  );

  it.each(['1901-01-01', '2000-02-29', '2099-12-31'])(
    'checks date format/range only, not unavailable birth chronology %s',
    (asOfDate) => {
      expect(validateSynastryInput({ ...query, asOfDate })).toMatchObject({
        status: 'valid',
        coverage: 'query-fields-only',
      });
    },
  );

  it.each(['1900-12-31', '2100-01-01'])('rejects unsupported year %s', (asOfDate) => {
    invalidIssue({ ...query, asOfDate }, 'asOfDate', 'date-out-of-range');
  });

  it.each(['a', 'b'])('associates unknown person with %s', (side) => {
    invalidIssue({ ...query, [side]: 'toString' }, side, 'invalid-choice');
  });

  it('rejects duplicate viewer objects without claiming a P8-native ban', () => {
    invalidIssue({ ...query, b: 'ayuan' }, 'b', 'same-object');
  });

  it.each(['Romantic', ' romantic', '', '__proto__', true])('rejects unknown relation kind %s', (kind) => {
    invalidIssue({ ...query, kind }, 'kind', 'invalid-choice');
  });

  it('keeps reverse ordering and other valid conditions intact when unavailable', () => {
    const checked = validateSynastryInput({ ...query, a: 'xiaohe', b: 'ayuan', kind: 'collaboration', orbDegrees: 0 });
    const result = markInputUnavailable(checked);
    expect(result).toMatchObject({
      status: 'unavailable',
      query: { a: 'xiaohe', b: 'ayuan', kind: 'collaboration', orbDegrees: 0 },
    });
    if (result.status === 'unavailable') {
      expect(result.summary).toContainEqual({ id: 'a', label: 'A方', value: '小禾（合成）' });
      expect(result.summary).toContainEqual({ id: 'b', label: 'B方', value: '阿远（合成）' });
      expect(result.summary).toContainEqual({ id: 'orbDegrees', label: '统一相位容许度', value: '0°' });
    }
  });

  it.each([null, undefined, false, [], 'value', 6])('returns safe shape issue for %s', (value) => {
    invalidIssue(value, 'query', 'invalid-shape');
  });

  it('projects a frozen record without treating extra consent, birth or revision as validated', () => {
    const input = Object.freeze({ ...query, consent: 'user_confirmed', birth: { date: '2050-01-01' }, revision: true });
    const result = validateSynastryInput(input);
    expect(result).toMatchObject({ status: 'valid', query, coverage: 'query-fields-only' });
    if (result.status === 'valid') {
      expect(Object.keys(result.query)).toEqual(['a', 'b', 'kind', 'asOfDate', 'orbDegrees']);
      result.query.a = 'xiaohe';
      expect(input.a).toBe('ayuan');
    }
  });

  it('keeps invalid reports when unavailable is requested and never echoes raw input', () => {
    const invalid = invalidIssue({ ...query, a: '<private-source-value>', orbDegrees: NaN }, 'a');
    expect(markInputUnavailable(invalid)).toBe(invalid);
    expect(JSON.stringify(invalid)).not.toContain('<private-source-value>');
  });

  it('does not fetch or write browser storage during field checks or unavailable mapping', () => {
    const fetch = vi.fn(() => {
      throw new Error('unexpected I/O');
    });
    vi.stubGlobal('fetch', fetch);
    const write = vi.spyOn(Storage.prototype, 'setItem');
    const result = validateSynastryInput(query);
    markInputUnavailable(result);
    validateWindowInput({ purpose: '面试', startDate: '2026-10-21', endDate: '2026-10-27', offset: 0, limit: 31 });
    expect(fetch).not.toHaveBeenCalled();
    expect(write).not.toHaveBeenCalled();
  });
});
