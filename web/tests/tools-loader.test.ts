import { createHash, webcrypto } from 'node:crypto';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadPublishedToolPort, readManifest, sampleFiles } from '../src/tools/loadPublishedSamples';
import { synastryFixture, windowFixture } from './tools-test-fixtures';
import type { PublishedSample } from '../src/tools/types';

const commit = '1'.repeat(40);
const digest = (value: string) => createHash('sha256').update(value).digest('hex');
function catalog() {
  const samples: PublishedSample[] = [
    windowFixture('a'),
    windowFixture('b', 1),
    windowFixture('c', 2),
    synastryFixture('d'),
  ];
  const bodies = new Map<string, string>();
  const entries = sampleFiles.map((file, index) => {
    const sample = structuredClone(samples[index]);
    sample.provenance = {
      ...sample.provenance,
      source_ref: 'origin/v4/p8-calc',
      source_commit: commit,
      source_path: `docs/v4/contracts/samples/${file}`,
    };
    const body = JSON.stringify(sample);
    bodies.set(file, body);
    return { file, tool: sample.tool, document_id: sample.document_id, sha256: digest(body) };
  });
  return {
    manifest: {
      schema: 'frontend-tools-export-v1',
      source_ref: 'origin/v4/p8-calc',
      source_commit: commit,
      synthetic_only: true,
      model_calls: 0,
      entries,
    },
    bodies,
  };
}
function fixtureFetch(data = catalog()) {
  const fetcher = vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
    if (options?.credentials !== 'omit') throw new Error('Unexpected credentials');
    const name = String(input).replace('/data/tools/', '');
    return new Response(name === 'manifest.json' ? JSON.stringify(data.manifest) : data.bodies.get(name), {
      status: 200,
    });
  });
  vi.stubGlobal('crypto', webcrypto);
  vi.stubGlobal('fetch', fetcher);
  return fetcher;
}
afterEach(() => vi.unstubAllGlobals());

describe('fixed public tool sample loader', () => {
  it('reads only fixed static files without credentials or browser caches', async () => {
    const fetcher = fixtureFetch();
    const port = await loadPublishedToolPort();
    expect(fetcher).toHaveBeenCalledTimes(5);
    expect(fetcher.mock.calls.map(([url]) => String(url))).toEqual([
      '/data/tools/manifest.json',
      ...sampleFiles.map((name) => `/data/tools/${name}`),
    ]);
    for (const [, options] of fetcher.mock.calls)
      expect(options).toMatchObject({ cache: 'no-store', credentials: 'omit', redirect: 'error' });
    const result = await port.windowSearch(port.windows[0]);
    expect(result.status).toBe('ready');
  });

  it('refuses stale or modified bytes even when the projection shape looks correct', async () => {
    const data = catalog();
    data.bodies.set(sampleFiles[0], `${data.bodies.get(sampleFiles[0])} `);
    fixtureFetch(data);
    await expect(loadPublishedToolPort()).rejects.toMatchObject({ code: 'INVALID_PUBLIC_SAMPLE' });
  });

  it('rejects duplicate entries, path traversal, source or effect changes before sample reads', () => {
    const { manifest } = catalog();
    for (const change of [
      { ...manifest, source_ref: 'unknown' },
      { ...manifest, model_calls: 1 },
      { ...manifest, entries: manifest.entries.map((entry) => ({ ...entry, file: '../private.json' })) },
      { ...manifest, entries: manifest.entries.map(() => manifest.entries[0]) },
    ])
      expect(() => readManifest(change)).toThrow();
  });

  it('refuses mismatched source commits and extra private root fields', async () => {
    for (const change of [
      (sample: Record<string, unknown>) => {
        sample.provenance = { ...(sample.provenance as object), source_commit: '2'.repeat(40) };
      },
      (sample: Record<string, unknown>) => {
        sample.birth = 'PRIVATE_SENTINEL';
      },
      (sample: Record<string, unknown>) => {
        sample.effects = { model_calls: 0, writes: 1, alias_registry: 'ephemeral_only' };
      },
    ]) {
      const data = catalog(),
        sample: Record<string, unknown> = JSON.parse(data.bodies.get(sampleFiles[0])!);
      change(sample);
      const body = JSON.stringify(sample);
      data.bodies.set(sampleFiles[0], body);
      data.manifest.entries[0].sha256 = digest(body);
      fixtureFetch(data);
      await expect(loadPublishedToolPort()).rejects.toMatchObject({ code: 'INVALID_PUBLIC_SAMPLE' });
    }
  });

  it('honors cancellation instead of exposing a catalog after the viewer has left', async () => {
    fixtureFetch();
    const controller = new AbortController();
    controller.abort();
    await expect(loadPublishedToolPort(controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
  });
});
