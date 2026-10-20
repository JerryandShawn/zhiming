import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const published = resolve(root, 'public/fonts');
const families = ['noto-sans-sc', 'noto-serif-sc'] as const;
const descriptors = ['font-family', 'font-style', 'font-display', 'font-weight', 'src', 'unicode-range'] as const;
type Face = Record<(typeof descriptors)[number], string>;
type FileRecord = { file: string; bytes: number; sha256: string };
const source = (family: string) => resolve(root, 'node_modules/@fontsource-variable', family);
const hash = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');

// Parse the restricted published @font-face grammar independently of the generator.
// Comparing ordered faces matters: overlapping Unicode faces use source order.
function faces(css: string): Face[] {
  const cleaned = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const blocks = [...cleaned.matchAll(/@font-face\s*\{([^{}]*)\}/g)];
  expect(cleaned.replace(/@font-face\s*\{([^{}]*)\}/g, '').trim()).toBe('');
  return blocks.map((match) => {
    const entries = match[1]
      .split(';')
      .map((entry) => entry.trim())
      .filter(Boolean)
      .map((entry) => {
        const separator = entry.indexOf(':');
        expect(separator).toBeGreaterThan(0);
        return [entry.slice(0, separator).trim(), entry.slice(separator + 1).trim()] as const;
      });
    expect(entries).toHaveLength(descriptors.length);
    expect(new Set(entries.map(([name]) => name)).size).toBe(descriptors.length);
    expect(entries.map(([name]) => name).sort()).toEqual([...descriptors].sort());
    return Object.fromEntries(entries) as Face;
  });
}
function coverage(value: string): Set<number> {
  const points = new Set<number>();
  for (const range of value.split(',')) {
    const match = /^U\+([0-9a-f]{1,6})(?:-([0-9a-f]{1,6}))?$/i.exec(range.trim());
    expect(match, 'The pinned published range grammar changed').not.toBeNull();
    const start = Number.parseInt(match![1], 16),
      end = Number.parseInt(match![2] ?? match![1], 16);
    expect(start).toBeLessThanOrEqual(end);
    expect(end).toBeLessThanOrEqual(0x10ffff);
    for (let point = start; point <= end; point++) points.add(point);
  }
  return points;
}
function officialFaces(family: string) {
  return faces(
    readFileSync(resolve(source(family), 'index.css'), 'utf8')
      .replaceAll('./files/', './')
      .replaceAll(' SC Variable', ' SC'),
  );
}
function publicFaces() {
  return faces(readFileSync(resolve(published, 'fonts.css'), 'utf8'));
}
function expectedFiles(): FileRecord[] {
  return families.flatMap((family) =>
    readdirSync(resolve(source(family), 'files'))
      .filter((name) => name.endsWith('.woff2'))
      .sort()
      .map((file) => {
        const bytes = readFileSync(resolve(source(family), 'files', file));
        return { file, bytes: bytes.length, sha256: hash(bytes) };
      }),
  );
}

describe('published Fontsource coverage and binary invariants', () => {
  it('retains every ordered per-face descriptor from both pinned external packages regardless of CSS whitespace', () => {
    for (const family of families) {
      const metadata = JSON.parse(readFileSync(resolve(source(family), 'package.json'), 'utf8')) as { version: string };
      expect(metadata.version).toBe('5.3.1');
    }
    const expected = families.flatMap(officialFaces),
      actual = publicFaces();
    expect(expected).toHaveLength(202);
    expect(actual.map((face) => descriptors.map((key) => face[key]))).toEqual(
      expected.map((face) => descriptors.map((key) => face[key])),
    );
  });

  it.each(families)('retains each %s Unicode mapping, including supplementary-plane code points', (family) => {
    const expected = officialFaces(family);
    const name = expected[0]['font-family'];
    const actual = publicFaces().filter((face) => face['font-family'] === name);
    expect(actual).toHaveLength(101);
    expect(new Set(actual.map((face) => face.src)).size).toBe(101);
    const union = new Set<number>();
    actual.forEach((face, index) => {
      const points = coverage(face['unicode-range']);
      expect([...points].sort((a, b) => a - b)).toEqual(
        [...coverage(expected[index]['unicode-range'])].sort((a, b) => a - b),
      );
      for (const point of points) union.add(point);
    });
    expect(actual.reduce((count, face) => count + face['unicode-range'].split(',').length, 0)).toBe(9068);
    expect(union.size).toBe(15609);
    expect(union.has(0x1f1e9)).toBe(true);
    expect([...union].some((point) => point > 0xffff)).toBe(true);
    expect(union.has(0x4e00)).toBe(true);
    expect(union.has(0x0301)).toBe(true);
  });

  it('copies every official WOFF2 byte-for-byte and binds the entire manifest to those independent hashes', () => {
    const expected = expectedFiles();
    const manifest = JSON.parse(readFileSync(resolve(published, 'manifest.json'), 'utf8')) as {
      source: string;
      bytes: number;
      files: FileRecord[];
    };
    expect(manifest.source).toBe('@fontsource-variable/noto-{sans,serif}-sc@5.3.1');
    expect(manifest.files).toEqual(expected);
    expect(manifest.bytes).toBe(expected.reduce((sum, item) => sum + item.bytes, 0));
    expect(manifest.bytes).toBe(10531532);
    expect(
      readdirSync(published)
        .filter((name) => name.endsWith('.woff2'))
        .sort(),
    ).toEqual(expected.map((item) => item.file).sort());
    for (const file of expected) {
      const bytes = readFileSync(resolve(published, file.file));
      expect(bytes.length, file.file).toBe(file.bytes);
      expect(hash(bytes), file.file).toBe(file.sha256);
    }
  });

  it('keeps every CSS source local and present, including the explicitly preloaded slices', () => {
    const available = new Set(expectedFiles().map((file) => file.file));
    for (const face of publicFaces()) {
      const path = /^url\(\.\/([a-z0-9.-]+\.woff2)\) format\('woff2-variations'\)$/.exec(face.src);
      expect(path, 'A font source must remain a local published WOFF2 slice').not.toBeNull();
      expect(available.has(path![1])).toBe(true);
    }
    const html = readFileSync(resolve(root, 'index.html'), 'utf8');
    const preloads = [...html.matchAll(/href="\/fonts\/([^"/]+\.woff2)"/g)];
    expect(preloads.length).toBeGreaterThan(0);
    for (const match of preloads) expect(available.has(match[1])).toBe(true);
  });

  it.each(families)('ships the unchanged %s license beside the published fonts', (family) => {
    const original = readFileSync(resolve(source(family), 'LICENSE'));
    const copied = readFileSync(resolve(published, `${family}-OFL.txt`));
    expect(copied.equals(original)).toBe(true);
    expect(copied.toString('utf8')).toContain('SIL OPEN FONT LICENSE Version 1.1');
  });
});
