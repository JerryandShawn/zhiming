import { describe, expect, it } from 'vitest';
import { buildTermMatcher, MATCH_LIMITS, type TermSegment } from '../src/study/termMatching';
import type { StudySystem, TermSummary } from '../src/study/types';

const term = (
  label: string,
  aliases: string[] = [],
  system: StudySystem = 'bazi',
  termId = `${system}-${label}`,
): TermSummary => ({ term_id: termId, system, term: label, aliases });

const links = (segments: TermSegment[]) => segments.filter((segment) => segment.kind === 'term');
const original = (segments: TermSegment[]) => segments.map((segment) => segment.text).join('');

describe('plain-text study term recognition', () => {
  it('keeps every original character while recognizing the longest term at each position', () => {
    const match = buildTermMatcher([term('月亮'), term('星座', ['月亮星座'])]);
    const text = '🙂先看月亮星座，再看月亮。\n没有改写解释，也没有添个人联想。';
    const segments = match(text);
    expect(original(segments)).toBe(text);
    expect(links(segments)).toEqual([
      { kind: 'term', text: '月亮星座', label: '月亮星座' },
      { kind: 'term', text: '月亮', label: '月亮' },
    ]);
  });

  it('uses normalized lookup labels without changing full-width spelling or original whitespace', () => {
    const match = buildTermMatcher([term('天顶', ['MC']), term('太阳返照', ['Solar Return'])]);
    const text = '（ＭＣ）与 SOLAR\t \nRETURN。';
    const segments = match(text);
    expect(original(segments)).toBe(text);
    expect(links(segments)).toEqual([
      { kind: 'term', text: 'ＭＣ', label: 'mc' },
      { kind: 'term', text: 'SOLAR\t \nRETURN', label: 'solar return' },
    ]);
  });

  it('treats punctuation in published labels literally and leaves unrelated markup as plain text', () => {
    const match = buildTermMatcher([term('a+b'), term('[.*]')]);
    const text = '<script>plain text</script>（a+b） + （[.*]） + abc + axb';
    const segments = match(text);
    expect(original(segments)).toBe(text);
    expect(links(segments).map((segment) => segment.text)).toEqual(['a+b', '[.*]']);
    expect(segments[0]).toEqual({ kind: 'text', text: '<script>plain text</script>（' });
  });

  it('does not turn a short ASCII label into a button inside another word or identifier', () => {
    const match = buildTermMatcher([term('天顶', ['MC'])]);
    const text = 'MC MCU _MC MC_ MC2 2MC （ＭＣ）';
    const segments = match(text);
    expect(original(segments)).toBe(text);
    expect(links(segments).map((segment) => segment.text)).toEqual(['MC', 'ＭＣ']);
  });

  it('never cuts a compatibility character expansion or a combining-mark cluster', () => {
    const partial = buildTermMatcher([term('ff'), term('fi')]);
    expect(partial('（ﬃ）')).toEqual([{ kind: 'text', text: '（ﬃ）' }]);
    const whole = buildTermMatcher([term('ffi')]);
    expect(links(whole('（ﬃ）'))).toEqual([{ kind: 'term', text: 'ﬃ', label: 'ffi' }]);
    const combining = buildTermMatcher([term('ab')]);
    expect(combining('ab\u0301')).toEqual([{ kind: 'text', text: 'ab\u0301' }]);
  });

  it('uses Unicode character boundaries around astral text and keeps ordinary single-character prose unlinked', () => {
    const match = buildTermMatcher([term('𠮷星'), term('火')]);
    const text = '🙂𠮷星，火；𠮷星🌙';
    const segments = match(text);
    expect(original(segments)).toBe(text);
    expect(links(segments).map((segment) => segment.text)).toEqual(['𠮷星', '𠮷星']);
    expect(match('火')).toEqual([{ kind: 'text', text: '火' }]);
  });

  it('recognizes one shared label once and leaves system selection to explicit resolution', () => {
    const match = buildTermMatcher([term('共同词', [], 'bazi'), term('共同词', [], 'ziwei'), term('专属词')]);
    const text = '共同词、专属词';
    expect(links(match(text)).map((segment) => segment.label)).toEqual(['共同词', '专属词']);
    expect(links(match(text, 'ziwei')).map((segment) => segment.label)).toEqual(['共同词']);
    expect(match(text, 'tarot')).toEqual([{ kind: 'text', text }]);
    // Segments carry a lookup label, never an arbitrarily selected term_id.
    expect(links(match('共同词'))).toEqual([{ kind: 'term', text: '共同词', label: '共同词' }]);
  });

  it('keeps the whole response readable when text exceeds the display work budget', () => {
    const match = buildTermMatcher([term('八字')]);
    const text = `八字${'🙂'.repeat(MATCH_LIMITS.textPoints)}`;
    expect(match(text)).toEqual([{ kind: 'text', text }]);
  });

  it('limits interactive buttons while retaining the full unmatched suffix as original text', () => {
    const match = buildTermMatcher([term('八字')]);
    const text = Array(MATCH_LIMITS.buttons + 7)
      .fill('八字')
      .join('，');
    const segments = match(text);
    expect(links(segments)).toHaveLength(MATCH_LIMITS.buttons);
    expect(original(segments)).toBe(text);
    expect(segments.at(-1)).toEqual({ kind: 'text', text: `，${Array(7).fill('八字').join('，')}` });
  });

  it('falls back to unchanged text when the supplied index exceeds its work budget', () => {
    const labels = Array.from({ length: MATCH_LIMITS.labels + 1 }, (_, index) => `术语${index}`);
    const match = buildTermMatcher([term('八字', labels)]);
    const text = '八字与术语0';
    expect(match(text)).toEqual([{ kind: 'text', text }]);
  });

  it('does not retain a mutable caller-owned term index', () => {
    const input = [term('八字', ['四柱'])];
    const match = buildTermMatcher(input);
    input[0].term = '个人联想';
    input[0].aliases.splice(0, 1, '另一联想');
    const text = '八字、四柱、个人联想、另一联想';
    const segments = match(text);
    expect(original(segments)).toBe(text);
    expect(links(segments).map((segment) => segment.label)).toEqual(['八字', '四柱']);
  });
});
