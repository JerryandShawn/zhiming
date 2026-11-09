import { describe, expect, it } from 'vitest';
// @ts-expect-error The reproducible sample generator is a plain Node ESM script.
import { projectSample, readRef } from '../scripts/prepare-chart-samples.mjs';

describe('sample document references', () => {
  const sample = {
    documents: [
      { document_id: 'other', payload: {} },
      { document_id: 'selected', payload: { 'a/b': { '~key': ['correct'] } } },
    ],
  };
  it('selects by document id and decodes JSON pointer escapes', () => {
    expect(readRef(sample, { document_id: 'selected', path: '/a~1b/~0key/0' })).toBe('correct');
  });
  it.each([
    { document_id: 'missing', path: '' },
    { document_id: 'selected', path: 'a' },
    { document_id: 'selected', path: '/a~2b' },
    { document_id: 'selected', path: '/a~1b/~0key/00' },
    { document_id: 'selected', path: '/a~1b/~0key/-' },
    { document_id: 'selected', path: '/__proto__' },
  ])('rejects invalid references without guessing: %j', (ref) => {
    expect(() => readRef(sample, ref)).toThrow();
  });
  it('uses the declared primary reference after document reorder and excludes private siblings', () => {
    const input = {
      view: { primary: [{ document_id: 'actual', path: '/nested' }] },
      documents: [
        {
          document_id: 'time',
          kind: 'time_basis',
          payload: {
            time_basis: { requires_confirmation: true, utc: 'private' },
            interpretation: { comparisons: [] },
            charts: [],
          },
        },
        { document_id: 'decoy', payload: { nested: { planets: { decoy: true } } } },
        {
          document_id: 'actual',
          payload: { nested: { planets: { actual: true }, civil_time: 'private', request: { birth: 'private' } } },
        },
      ],
    };
    const projected = projectSample(input, 'astro', 'hash');
    expect(projected.data.planets).toEqual({ actual: true });
    expect(projected.basis.time_basis).toEqual({ requires_confirmation: true });
    expect(JSON.stringify(projected)).not.toContain('private');
    expect(() => projectSample({ ...input, view: { primary: [] } }, 'astro', 'hash')).toThrow();
  });
});
