import { describe, expect, it } from 'vitest';
import { readGlossary } from '../src/study/validateGlossary';
import { readLearning } from '../src/study/validateLearning';
import { glossaryManifest, learningManifest } from '../src/study/manifests';
import { STUDY_COMMIT } from '../src/study/validation';
import {
  bodies,
  bundle,
  glossaryManifestUrl,
  jsonArray,
  jsonObject,
  learningManifestUrl,
  parseBody,
  rawBundle,
} from './study-test-fixtures';

describe('published study projections retain the full reviewed catalog', () => {
  it('keeps 212 terms, 39 sources, original stages and 15 cards with 33 independently scoped evidence rows', () => {
    const data = bundle();
    expect(data.terms.entry_count).toBe(212);
    expect(data.terms.system_counts).toEqual({ bazi: 72, ziwei: 55, astro: 50, tarot: 35 });
    expect(data.sources.sources).toHaveLength(39);
    expect(data.sources.stage).toBe('draft_source_registry');
    expect(data.terms.stage).toBe('draft_complete_200_for_review');
    expect(data.terms.review_tag).toBe('v1_ready_editorial_reviewed');
    expect(data.learning.map((item) => [item.system, item.cards.length, item.evidence.length])).toEqual([
      ['bazi', 11, 23],
      ['ziwei', 2, 5],
      ['astro', 2, 5],
    ]);
    expect(data.learning.map((item) => item.provenance.source_commit)).toEqual(Array(3).fill(STUDY_COMMIT));
    expect(data.learning[2].cards[0].c_aliases).toEqual(['c2']);
    expect(
      data.learning.every((item) => item.evidence.some((row) => row.kind === 'rule' && row.basis === 'true_solar')),
    ).toBe(true);
    expect(
      data.learning.every((item) => item.evidence.some((row) => row.kind === 'fact' && row.basis === 'actual_UTC')),
    ).toBe(true);
  });

  for (const level of ['root', 'term', 'term-source', 'source-root', 'source'] as const)
    it(`refuses unexpected private fields at glossary ${level}`, () => {
      const raw = rawBundle(),
        terms = jsonObject(raw.terms),
        sources = jsonObject(raw.sources);
      const firstTerm = jsonObject(jsonArray(terms.entries)[0]);
      const target =
        level === 'root'
          ? terms
          : level === 'term'
            ? firstTerm
            : level === 'term-source'
              ? jsonObject(jsonArray(firstTerm.sources)[0])
              : level === 'source-root'
                ? sources
                : jsonObject(jsonArray(sources.sources)[0]);
      target.owner_user_id = 'SYNTHETIC_PRIVATE_SENTINEL';
      expect(() => readGlossary(terms, sources)).toThrow('样例依据已更新，待重新复核。');
    });

  it('rejects an incomplete or miscounted dictionary instead of silently dropping terms', () => {
    for (const change of [
      (root: Record<string, unknown>) => {
        jsonArray(root.entries).pop();
      },
      (root: Record<string, unknown>) => {
        jsonObject(root.system_counts).bazi = 73;
      },
      (root: Record<string, unknown>) => {
        root.review_tag = 'approved_for_predictions';
      },
      (root: Record<string, unknown>) => {
        root.stage = 'production_verified';
      },
    ]) {
      const raw = rawBundle(),
        terms = jsonObject(raw.terms);
      change(terms);
      expect(() => readGlossary(terms, raw.sources)).toThrow();
    }
  });

  it('rejects unregistered references and duplicate normalized names within one system', () => {
    for (const change of [
      (root: Record<string, unknown>) => {
        const first = jsonObject(jsonArray(root.entries)[0]);
        jsonObject(jsonArray(first.sources)[0]).source_id = 'not-registered';
      },
      (root: Record<string, unknown>) => {
        const entries = jsonArray(root.entries).map(jsonObject);
        const first = entries[0],
          next = entries.find((item) => item !== first && item.system === first.system)!;
        jsonArray(next.aliases).push(` ${String(first.term).normalize('NFKC')} `);
      },
    ]) {
      const raw = rawBundle(),
        terms = jsonObject(raw.terms);
      change(terms);
      expect(() => readGlossary(terms, raw.sources)).toThrow();
    }
  });

  it('retains the exact tarot index locator as plain text, but rejects markup and source escape paths', () => {
    const raw = rawBundle(),
      sources = jsonObject(raw.sources);
    const editorial = jsonArray(sources.sources)
      .map(jsonObject)
      .find((row) => row.source_id === 'project-tarot-editorial')!;
    const valid = readGlossary(raw.terms, sources);
    expect(valid.sources.sources.find((row) => row.source_id === 'project-tarot-editorial')!.locator).toContain(
      '<index>',
    );
    editorial.locator = String(editorial.locator) + '<script>invalid</script>';
    expect(() => readGlossary(raw.terms, sources)).toThrow();
    const escape = rawBundle(),
      escaped = jsonObject(jsonArray(jsonObject(escape.sources).sources)[0]);
    escaped.path = 'mingjing_core/../private.txt';
    expect(() => readGlossary(escape.terms, escape.sources)).toThrow();
  });

  it('enforces the source registry stage and named kind rather than accepting invented authority labels', () => {
    for (const change of [
      (root: Record<string, unknown>) => {
        root.stage = 'officially_verified';
      },
      (root: Record<string, unknown>) => {
        jsonObject(jsonArray(root.sources)[0]).kind = 'prediction_authority';
      },
    ]) {
      const raw = rawBundle(),
        sources = jsonObject(raw.sources);
      change(sources);
      expect(() => readGlossary(raw.terms, sources)).toThrow();
    }
  });

  for (const level of ['root', 'card', 'evidence', 'provenance'] as const)
    it(`does not downcast unexpected learning ${level} fields into trusted display data`, () => {
      const root = jsonObject(rawBundle().learning[0]);
      const target =
        level === 'root'
          ? root
          : level === 'card'
            ? jsonObject(jsonArray(root.cards)[0])
            : level === 'evidence'
              ? jsonObject(jsonArray(root.evidence)[0])
              : jsonObject(root.provenance);
      target.observed = { owner_user_id: 'SYNTHETIC_PRIVATE_SENTINEL' };
      expect(() => readLearning(root, 'bazi')).toThrow();
    });

  it('rejects cross-case, changed-claim and unregistered card or rule inputs', () => {
    for (const field of ['document_id', 'claim_id', 'alias'] as const) {
      const root = jsonObject(rawBundle().learning[2]);
      const ref = jsonObject(jsonArray(jsonObject(jsonArray(root.cards)[0]).evidence_refs)[0]);
      ref[field] = field === 'alias' ? 'c1' : `${field === 'document_id' ? 'doc' : 'demo-claim'}-${'0'.repeat(64)}`;
      expect(() => readLearning(root, 'astro')).toThrow();
    }
    const root = jsonObject(rawBundle().learning[0]);
    const rule = jsonArray(root.evidence)
      .map(jsonObject)
      .find((item) => item.kind === 'rule')!;
    jsonObject(jsonArray(rule.evidence_refs)[0]).claim_id = 'demo-claim-' + '0'.repeat(64);
    expect(() => readLearning(root, 'bazi')).toThrow();
  });

  it('refuses changed effects, case/system identity and original source metadata', () => {
    for (const change of [
      (root: Record<string, unknown>) => {
        jsonObject(root.effects).writes = 1;
      },
      (root: Record<string, unknown>) => {
        root.sample_id = 'ayuan-ziwei';
      },
      (root: Record<string, unknown>) => {
        jsonObject(root.provenance).source_commit = '0'.repeat(40);
      },
      (root: Record<string, unknown>) => {
        jsonObject(jsonArray(jsonObject(root.provenance).source_files)[0]).sha256 = '0'.repeat(64);
      },
    ]) {
      const root = jsonObject(rawBundle().learning[0]);
      change(root);
      expect(() => readLearning(root, 'bazi')).toThrow();
    }
  });

  it('requires fixed complete manifests and rejects duplicates or path traversal before asset access', () => {
    const data = bodies();
    expect(glossaryManifest(parseBody(data, glossaryManifestUrl))).toHaveLength(2);
    expect(learningManifest(parseBody(data, learningManifestUrl))).toHaveLength(3);
    for (const url of [glossaryManifestUrl, learningManifestUrl]) {
      const original = jsonObject(parseBody(data, url));
      const read = url === glossaryManifestUrl ? glossaryManifest : learningManifest;
      expect(() => read({ ...original, source_commit: 'f'.repeat(40) })).toThrow();
      const duplicate = structuredClone(original),
        entries = jsonArray(duplicate.entries);
      entries[1] = structuredClone(entries[0]);
      expect(() => read(duplicate)).toThrow();
      const traversal = structuredClone(original);
      jsonObject(jsonArray(traversal.entries)[0]).file = '../private.json';
      expect(() => read(traversal)).toThrow();
    }
  });
});
