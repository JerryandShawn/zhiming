import type { StudySystem, TermSummary } from './types';

export type TermSegment = { kind: 'text'; text: string } | { kind: 'term'; text: string; label: string };
type Node = { next: Map<string, Node>; terminal?: { label: string; systems: Set<StudySystem> } };
type Unit = { value: string; start: number; end: number; first: boolean; last: boolean };
export type TermMatcher = (text: string, system?: StudySystem) => TermSegment[];
export const MATCH_LIMITS = { textPoints: 16000, labelPoints: 80, labels: 4096, indexPoints: 32768, buttons: 80 };

const normalized = (text: string) => text.normalize('NFKC').toLocaleLowerCase('en-US').trim().replace(/\s+/gu, ' ');
const node = (): Node => ({ next: new Map() });
const literal: TermMatcher = (text) => [{ kind: 'text', text }];
const asciiWord = (value: string | undefined) => value !== undefined && /^[a-z0-9_]$/iu.test(value);

function unitsFor(text: string): Unit[] | undefined {
  if (text.length > MATCH_LIMITS.textPoints * 2) return;
  const points = Array.from(text);
  if (points.length > MATCH_LIMITS.textPoints) return;
  const units: Unit[] = [];
  let offset = 0;
  for (const point of points) {
    const start = offset;
    offset += point.length;
    const converted = Array.from(point.normalize('NFKC').toLocaleLowerCase('en-US'));
    converted.forEach((value, index) => {
      const whitespace = /^\s$/u.test(value);
      if (whitespace && units.at(-1)?.value === ' ') {
        units[units.length - 1].end = offset;
        return;
      }
      units.push({
        value: whitespace ? ' ' : value,
        start,
        end: offset,
        first: index === 0,
        last: index === converted.length - 1,
      });
    });
  }
  return units;
}

function allowedBoundary(units: Unit[], start: number, end: number) {
  return (
    units[start].first &&
    units[end].last &&
    !/^\p{M}$/u.test(units[start].value) &&
    !/^\p{M}$/u.test(units[end + 1]?.value ?? '') &&
    !(asciiWord(units[start].value) && asciiWord(units[start - 1]?.value)) &&
    !(asciiWord(units[end].value) && asciiWord(units[end + 1]?.value))
  );
}

function longest(root: Node, units: Unit[], start: number, system?: StudySystem) {
  let current = root;
  let found: { end: number; label: string } | undefined;
  for (let index = start; index < units.length && index - start < MATCH_LIMITS.labelPoints; index++) {
    const next = current.next.get(units[index].value);
    if (!next) break;
    current = next;
    const terminal = current.terminal;
    if (terminal && (!system || terminal.systems.has(system)) && allowedBoundary(units, start, index))
      found = { end: index, label: terminal.label };
  }
  return found;
}

function segment(root: Node, text: string, system?: StudySystem): TermSegment[] {
  const units = unitsFor(text);
  if (!units) return literal(text);
  const result: TermSegment[] = [];
  let index = 0,
    copied = 0,
    buttons = 0;
  while (index < units.length && buttons < MATCH_LIMITS.buttons) {
    const found = longest(root, units, index, system);
    if (!found) {
      index++;
      continue;
    }
    const start = units[index].start,
      end = units[found.end].end;
    if (start > copied) result.push({ kind: 'text', text: text.slice(copied, start) });
    result.push({ kind: 'term', text: text.slice(start, end), label: found.label });
    copied = end;
    index = found.end + 1;
    buttons++;
  }
  if (copied < text.length || !result.length) result.push({ kind: 'text', text: text.slice(copied) });
  return result;
}

/** Plain text only. No regular expression is built from source terms. */
export function buildTermMatcher(terms: readonly TermSummary[]): TermMatcher {
  const labels = new Map<string, Set<StudySystem>>();
  let points = 0;
  if (terms.length > 512) return literal;
  for (const term of terms)
    for (const value of [term.term, ...term.aliases]) {
      const label = normalized(value),
        length = Array.from(label).length;
      // Single-character labels are ordinary prose too. They remain searchable in
      // the full glossary instead of turning every occurrence into a control.
      if (length < 2 || length > MATCH_LIMITS.labelPoints) continue;
      if (!labels.has(label)) {
        points += length;
        labels.set(label, new Set());
      }
      if (labels.size > MATCH_LIMITS.labels || points > MATCH_LIMITS.indexPoints) return literal;
      labels.get(label)!.add(term.system);
    }
  const root = node();
  for (const [label, systems] of labels) {
    let current = root;
    for (const point of Array.from(label)) {
      if (!current.next.has(point)) current.next.set(point, node());
      current = current.next.get(point)!;
    }
    current.terminal = { label, systems };
  }
  return (text, system) => segment(root, text, system);
}
