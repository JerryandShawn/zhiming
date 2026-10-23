import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { vi } from 'vitest';
import { readGlossary } from '../src/study/validateGlossary';
import { readLearning } from '../src/study/validateLearning';
import type { LearningSample, StudyBundle, StudyEvidenceRef } from '../src/study/types';

export const studyFiles = [
  '/data/study/glossary/manifest.json',
  '/data/study/glossary/terms_v1.json',
  '/data/study/glossary/sources_v1.json',
  '/data/study/learning/manifest.json',
  '/data/study/learning/learning-ayuan-bazi.json',
  '/data/study/learning/learning-ayuan-ziwei.json',
  '/data/study/learning/learning-ayuan-astro.json',
] as const;
export const glossaryManifestUrl = studyFiles[0];
export const learningManifestUrl = studyFiles[3];
const publicRoot = path.resolve('public');
let originalBodies: Map<string, string> | undefined;
export function bodies() {
  originalBodies ??= new Map(
    studyFiles.map((url) => [url, fs.readFileSync(path.join(publicRoot, url.slice(1)), 'utf8')]),
  );
  return new Map(originalBodies);
}
export function jsonObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Expected fixture object');
  return value as Record<string, unknown>;
}
export function jsonArray(value: unknown): unknown[] {
  if (!Array.isArray(value)) throw new Error('Expected fixture array');
  return value;
}
export const parseBody = (data: Map<string, string>, url: string): unknown => JSON.parse(data.get(url)!);
export const hashBody = (body: string) => createHash('sha256').update(body, 'utf8').digest('hex');
export function rewriteAsset(data: Map<string, string>, url: string, body: string, rehash = false) {
  data.set(url, body);
  if (!rehash) return;
  const manifestUrl = url.slice(0, url.lastIndexOf('/') + 1) + 'manifest.json';
  const manifest = jsonObject(parseBody(data, manifestUrl));
  const entry = jsonArray(manifest.entries)
    .map(jsonObject)
    .find((row) => row.file === url.slice(url.lastIndexOf('/') + 1));
  if (!entry) throw new Error('Missing fixture manifest entry');
  entry.bytes = Buffer.byteLength(body, 'utf8');
  entry.sha256 = hashBody(body);
  data.set(manifestUrl, JSON.stringify(manifest));
}
export function rawBundle() {
  const data = bodies();
  return {
    terms: parseBody(data, studyFiles[1]),
    sources: parseBody(data, studyFiles[2]),
    learning: studyFiles.slice(4).map((url) => parseBody(data, url)),
  };
}
export function bundle(): StudyBundle {
  const raw = rawBundle();
  return {
    ...readGlossary(raw.terms, raw.sources),
    learning: raw.learning.map((value, index) => readLearning(value, (['bazi', 'ziwei', 'astro'] as const)[index])),
  };
}
export function evidenceRef(sample: LearningSample, index = 0): StudyEvidenceRef {
  const { document_id, alias, claim_id } = sample.evidence[index];
  return { sample_id: sample.sample_id, document_id, alias, claim_id };
}
export function gate<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
export function fixtureFetch(
  data = bodies(),
  intercept?: (url: string, options: RequestInit | undefined) => Promise<Response | undefined>,
) {
  const fetcher = vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
    const url = String(input);
    if (!studyFiles.some((file) => file === url)) throw new Error('Unexpected non-static request');
    const intercepted = await intercept?.(url, options);
    if (intercepted) return intercepted;
    if (!data.has(url)) return new Response('', { status: 404 });
    return new Response(data.get(url), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetcher);
  return fetcher;
}
