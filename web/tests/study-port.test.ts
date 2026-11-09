import { afterEach, describe, expect, it, vi } from 'vitest';
import { createStudyPort } from '../src/study/port';
import type { SearchQuery } from '../src/study/types';
import { bundle, evidenceRef, gate } from './study-test-fixtures';

afterEach(() => vi.unstubAllGlobals());

describe('read-only study scope ownership', () => {
  it('searches the complete catalog, resolves an exact alias and leaves browser state and transport untouched', async () => {
    const data = bundle(),
      port = createStudyPort(data),
      scope = port.createScope();
    const writes = vi.spyOn(Storage.prototype, 'setItem'),
      removes = vi.spyOn(Storage.prototype, 'removeItem');
    const fetcher = vi.fn(() => {
      throw new Error('Study scope must not fetch');
    });
    vi.stubGlobal('fetch', fetcher);
    expect(await scope.search({ text: '' })).toMatchObject({ status: 'ready', value: expect.any(Array) });
    const all = await scope.search({ text: '' });
    if (all.status !== 'ready') throw new Error('Published catalog unavailable');
    expect(all.value).toHaveLength(212);
    const bazi = await scope.search({ text: '', system: 'bazi' });
    if (bazi.status !== 'ready') throw new Error('Published bazi catalog unavailable');
    expect(bazi.value).toHaveLength(72);
    expect(bazi.value.every((item) => item.system === 'bazi')).toBe(true);
    const target = data.terms.entries.find((item) => item.aliases.length)!;
    expect(await scope.resolveTerm(` ${target.aliases[0]} `, target.system)).toMatchObject({
      status: 'resolved',
      term: { term_id: target.term_id },
    });
    const detail = await scope.readTerm(target.term_id);
    if (detail.status !== 'ready') throw new Error('Published term unavailable');
    expect(detail.value.term).toEqual(target);
    expect(detail.value.sources.length).toBeGreaterThan(0);
    expect(
      detail.value.sources.every((source) => data.sources.sources.some((row) => row.source_id === source.source_id)),
    ).toBe(true);
    expect(scope.metadata().effects).toEqual({ model_calls: 0, business_writes: 0, progress_api: 'unavailable' });
    expect(writes).not.toHaveBeenCalled();
    expect(removes).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('returns all same-label systems as ambiguous instead of picking the first match', async () => {
    const data = bundle();
    const left = data.terms.entries.find((item) => item.system === 'bazi')!;
    const right = data.terms.entries.find((item) => item.system === 'ziwei')!;
    const alias = '跨体系合成歧义词';
    left.aliases.push(alias);
    right.aliases.push(alias);
    const scope = createStudyPort(data).createScope();
    const result = await scope.resolveTerm(alias);
    if (result.status !== 'ambiguous') throw new Error('Expected both explicitly ambiguous systems');
    expect(result.candidates.map((item) => item.term_id)).toEqual([left.term_id, right.term_id]);
    expect(await scope.resolveTerm(alias, 'ziwei')).toMatchObject({
      status: 'resolved',
      term: { term_id: right.term_id },
    });
    expect(await scope.resolveTerm('__synthetic_unlisted_term__')).toMatchObject({ status: 'unavailable' });
    expect(await scope.readTerm('__synthetic_unlisted_id__')).toMatchObject({ status: 'unavailable' });
  });

  it('finds full-width and differently cased aliases without changing the displayed original spelling', async () => {
    const data = bundle(),
      term = data.terms.entries.find((item) => item.system === 'astro')!;
    const original = term.term;
    term.aliases.push('ＳＹＮＴＨＥＴＩＣ　ＡＳＣ');
    const scope = createStudyPort(data).createScope();
    expect(await scope.resolveTerm(' synthetic  asc ', 'astro')).toMatchObject({
      status: 'resolved',
      term: { term_id: term.term_id, term: original, aliases: expect.arrayContaining(['ＳＹＮＴＨＥＴＩＣ　ＡＳＣ']) },
    });
    const results = await scope.search({ text: 'Synthetic ASC', system: 'astro' });
    expect(results).toMatchObject({ status: 'ready', value: [{ term_id: term.term_id, term: original }] });
  });

  it('does not expose evidence before a successful case read and matches the full case/document/alias/claim', async () => {
    const data = bundle(),
      scope = createStudyPort(data).createScope();
    const a = data.learning[0],
      b = data.learning[1],
      aRef = evidenceRef(a),
      bRef = evidenceRef(b);
    expect(aRef.alias).toBe(bRef.alias);
    expect(scope.resolveEvidence(aRef)).toBeUndefined();
    await scope.readLearning(a.sample_id);
    expect(scope.resolveEvidence(aRef)).toMatchObject({
      document_id: aRef.document_id,
      alias: aRef.alias,
      claim_id: aRef.claim_id,
    });
    for (const invalid of [
      bRef,
      { ...aRef, sample_id: b.sample_id },
      { ...aRef, document_id: bRef.document_id },
      { ...aRef, claim_id: 'demo-claim-' + '0'.repeat(64) },
    ])
      expect(scope.resolveEvidence(invalid)).toBeUndefined();
    await scope.readLearning(b.sample_id);
    expect(scope.resolveEvidence(aRef)).toBeUndefined();
    expect(scope.resolveEvidence(bRef)).toBeDefined();
  });

  it('gives sibling views separate activation and a dictionary sheet cannot revoke the learning view', async () => {
    const data = bundle(),
      port = createStudyPort(data),
      left = port.createScope(),
      right = port.createScope();
    const ref = evidenceRef(data.learning[0]);
    await left.readLearning(ref.sample_id);
    expect(right.resolveEvidence(ref)).toBeUndefined();
    await right.readLearning(ref.sample_id);
    await left.readTerm(data.terms.entries[0].term_id);
    expect(left.resolveEvidence(ref)).toBeUndefined();
    expect(right.resolveEvidence(ref)).toBeDefined();
    left.dispose();
    expect(right.resolveEvidence(ref)).toBeDefined();
    port.dispose();
    expect(right.resolveEvidence(ref)).toBeUndefined();
    expect(() => right.metadata()).toThrow();
    await expect(right.readLearning(ref.sample_id)).rejects.toMatchObject({ code: 'DISPOSED' });
    expect(() => port.createScope()).toThrow();
  });

  it('revokes evidence before empty, unavailable, invalid or aborted replacement reads', async () => {
    const data = bundle(),
      scope = createStudyPort(data).createScope(),
      ref = evidenceRef(data.learning[0]);
    await scope.readLearning(ref.sample_id);
    expect(await scope.search({ text: '__synthetic_unlisted_term__' })).toEqual({ status: 'ready', value: [] });
    expect(scope.resolveEvidence(ref)).toBeUndefined();
    await scope.readLearning(ref.sample_id);
    expect(await scope.readLearning('unavailable-case')).toMatchObject({ status: 'unavailable' });
    expect(scope.resolveEvidence(ref)).toBeUndefined();
    await scope.readLearning(ref.sample_id);
    await expect(scope.search({ text: '学'.repeat(1001) })).rejects.toMatchObject({ code: 'INVALID_QUERY' });
    expect(scope.resolveEvidence(ref)).toBeUndefined();
    await scope.readLearning(ref.sample_id);
    const controller = new AbortController();
    controller.abort();
    await expect(scope.readLearning(ref.sample_id, controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    expect(scope.resolveEvidence(ref)).toBeUndefined();
    await expect(scope.search({ text: '', system: 'unknown' } as unknown as SearchQuery)).rejects.toMatchObject({
      code: 'INVALID_QUERY',
    });
  });

  it('rejects A1 -> B -> A2 late completions, including an older request for the same case', async () => {
    const data = bundle(),
      waiting = [gate<void>(), gate<void>(), gate<void>()];
    let index = 0;
    const scope = createStudyPort(data, () => waiting[index++].promise).createScope();
    const a1 = scope.readLearning('ayuan-bazi'),
      rejectedA = expect(a1).rejects.toMatchObject({ name: 'AbortError' });
    const b = scope.readLearning('ayuan-ziwei'),
      rejectedB = expect(b).rejects.toMatchObject({ name: 'AbortError' });
    const a2 = scope.readLearning('ayuan-bazi');
    waiting[2].resolve();
    await expect(a2).resolves.toMatchObject({ status: 'ready', value: { sample_id: 'ayuan-bazi' } });
    waiting[0].resolve();
    waiting[1].resolve();
    await Promise.all([rejectedA, rejectedB]);
    expect(scope.resolveEvidence(evidenceRef(data.learning[0]))).toBeDefined();
    expect(scope.resolveEvidence(evidenceRef(data.learning[1]))).toBeUndefined();
  });

  it('an older failed read cannot erase a newer successful activation', async () => {
    const data = bundle(),
      old = gate<void>(),
      fresh = gate<void>();
    let count = 0;
    const scope = createStudyPort(data, () => (++count === 1 ? old.promise : fresh.promise)).createScope();
    const oldRead = scope.readLearning('ayuan-bazi');
    const rejected = expect(oldRead).rejects.toThrow('SYNTHETIC_OLD_FAILURE');
    const freshRead = scope.readLearning('ayuan-ziwei');
    fresh.resolve();
    await freshRead;
    old.reject(new Error('SYNTHETIC_OLD_FAILURE'));
    await rejected;
    expect(scope.resolveEvidence(evidenceRef(data.learning[1]))).toBeDefined();
    expect(scope.resolveEvidence(evidenceRef(data.learning[0]))).toBeUndefined();
  });

  for (const action of ['reset', 'dispose'] as const)
    it(`${action} before a pending read settles never reactivates the abandoned case`, async () => {
      const data = bundle(),
        waiting = gate<void>();
      const scope = createStudyPort(data, () => waiting.promise).createScope();
      const pending = scope.readLearning('ayuan-bazi');
      const rejected = expect(pending).rejects.toMatchObject(
        action === 'reset' ? { name: 'AbortError' } : { code: 'DISPOSED' },
      );
      scope[action]();
      waiting.resolve();
      await rejected;
      expect(scope.resolveEvidence(evidenceRef(data.learning[0]))).toBeUndefined();
    });

  it('returns copies without allowing a caller to alter catalog metadata, term text or active evidence', async () => {
    const data = bundle(),
      port = createStudyPort(data),
      scope = port.createScope();
    const expectedText = data.terms.entries[0].plain_explanation;
    data.terms.entries[0].plain_explanation = '外部输入后来修改';
    const term = await scope.readTerm(data.terms.entries[0].term_id);
    if (term.status !== 'ready') throw new Error('Expected published term');
    expect(term.value.term.plain_explanation).toBe(expectedText);
    term.value.term.plain_explanation = '调用方修改返回副本';
    const again = await scope.readTerm(data.terms.entries[0].term_id);
    expect(again).toMatchObject({ status: 'ready', value: { term: { plain_explanation: expectedText } } });
    const metadata = port.metadata();
    Object.assign(metadata.effects, { business_writes: 1 });
    expect(port.metadata().effects.business_writes).toBe(0);
    const ref = evidenceRef(data.learning[0]);
    await scope.readLearning(ref.sample_id);
    const first = scope.resolveEvidence(ref)!;
    const original = first.summary;
    first.summary = '调用方修改依据副本';
    expect(scope.resolveEvidence(ref)?.summary).toBe(original);
  });
});
