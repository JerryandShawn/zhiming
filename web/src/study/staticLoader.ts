import { publicAssetPath } from '../publicAsset';
import type { StudyPort } from './types';
import { createStudyPort } from './port';
import { glossaryManifest, learningManifest, type OutputEntry } from './manifests';
import { readGlossary } from './validateGlossary';
import { readLearning } from './validateLearning';
import { StudyDataError, studyNeed } from './validation';
const locations = {
  glossary: '/data/study/glossary/',
  learning: '/data/study/learning/',
} as const;
const allowed = new Set([
  '/data/study/glossary/manifest.json',
  '/data/study/glossary/terms_v1.json',
  '/data/study/glossary/sources_v1.json',
  '/data/study/learning/manifest.json',
  '/data/study/learning/learning-ayuan-bazi.json',
  '/data/study/learning/learning-ayuan-ziwei.json',
  '/data/study/learning/learning-ayuan-astro.json',
]);
const parse = (body: ArrayBuffer): unknown => JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(body));
const digest = async (body: ArrayBuffer) =>
  Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', body)), (part) =>
    part.toString(16).padStart(2, '0'),
  ).join('');
async function download(location: string, signal?: AbortSignal) {
  studyNeed(allowed.has(location));
  const response = await fetch(publicAssetPath(location), {
    method: 'GET',
    signal,
    credentials: 'omit',
    cache: 'no-store',
    redirect: 'error',
  });
  studyNeed(response.ok);
  const body = await response.arrayBuffer();
  studyNeed(body.byteLength > 0 && body.byteLength <= 2000000);
  return body;
}
async function asset(group: keyof typeof locations, entry: OutputEntry, signal?: AbortSignal) {
  const body = await download(locations[group] + entry.file, signal);
  studyNeed(body.byteLength === entry.bytes && (await digest(body)) === entry.sha256);
  return parse(body);
}
async function readStaticStudyPort(signal?: AbortSignal): Promise<StudyPort> {
  try {
    const [glossary, learning] = await Promise.all([
      download(locations.glossary + 'manifest.json', signal)
        .then(parse)
        .then(glossaryManifest),
      download(locations.learning + 'manifest.json', signal)
        .then(parse)
        .then(learningManifest),
    ]);
    const glossaryBodies = await Promise.all(
      glossary.map(async (entry) => ({ file: entry.file, body: await asset('glossary', entry, signal) })),
    );
    const terms = glossaryBodies.find((item) => item.file === 'terms_v1.json'),
      sources = glossaryBodies.find((item) => item.file === 'sources_v1.json');
    studyNeed(terms && sources);
    const catalog = readGlossary(terms.body, sources.body);
    const samples = await Promise.all(
      learning.map(async (entry) => {
        const sample = readLearning(await asset('learning', entry, signal), entry.system);
        studyNeed(
          sample.cards.length === entry.cards &&
            sample.evidence.length === entry.evidence &&
            sample.sample_id === entry.sample_id,
        );
        return sample;
      }),
    );
    signal?.throwIfAborted();
    return createStudyPort({ ...catalog, learning: samples });
  } catch (error) {
    if (signal?.aborted) throw new DOMException('Study load cancelled', 'AbortError');
    if (error instanceof StudyDataError) throw error;
    throw new StudyDataError();
  }
}
export type StudyLoadSession = { reload(signal?: AbortSignal): Promise<StudyPort>; reset(): void; dispose(): void };
/** Reload revokes the old catalog before I/O; stale completions cannot reactivate it. */
export function createStudyLoadSession(): StudyLoadSession {
  let generation = 0,
    closed = false,
    controller: AbortController | undefined,
    active: StudyPort | undefined;
  const reset = () => {
    generation++;
    controller?.abort();
    controller = undefined;
    active?.dispose();
    active = undefined;
  };
  return {
    reset,
    dispose() {
      reset();
      closed = true;
    },
    async reload(signal) {
      if (closed) throw new StudyDataError('DISPOSED');
      reset();
      const id = generation,
        current = new AbortController();
      controller = current;
      const forwardAbort = () => current.abort(signal?.reason);
      if (signal?.aborted) forwardAbort();
      else signal?.addEventListener('abort', forwardAbort, { once: true });
      try {
        const port = await readStaticStudyPort(current.signal);
        if (closed || id !== generation || current.signal.aborted) {
          port.dispose();
          throw new DOMException('Study load superseded', 'AbortError');
        }
        active = port;
        return port;
      } catch (error) {
        current.abort();
        throw error;
      } finally {
        signal?.removeEventListener('abort', forwardAbort);
        if (controller === current) controller = undefined;
      }
    },
  };
}
