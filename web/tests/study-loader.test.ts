import { webcrypto } from 'node:crypto';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createStudyLoadSession } from '../src/study/staticLoader';
import {
  bodies,
  bundle,
  evidenceRef,
  fixtureFetch,
  gate,
  glossaryManifestUrl,
  jsonArray,
  jsonObject,
  learningManifestUrl,
  parseBody,
  rewriteAsset,
  studyFiles,
} from './study-test-fixtures';

beforeEach(() => vi.stubGlobal('crypto', webcrypto));
afterEach(() => vi.unstubAllGlobals());

describe('study static loading and catalog replacement', () => {
  it('uses exactly seven fixed same-origin GETs without identity, browser cache, API or source URL fetches', async () => {
    const fetcher = fixtureFetch(),
      session = createStudyLoadSession();
    const writes = vi.spyOn(Storage.prototype, 'setItem'),
      removes = vi.spyOn(Storage.prototype, 'removeItem');
    const port = await session.reload();
    expect(new Set(fetcher.mock.calls.map(([url]) => String(url)))).toEqual(new Set(studyFiles));
    expect(fetcher).toHaveBeenCalledTimes(7);
    for (const [, options] of fetcher.mock.calls) {
      expect(options).toMatchObject({ method: 'GET', credentials: 'omit', cache: 'no-store', redirect: 'error' });
      expect(new Headers(options?.headers).get('X-Token')).toBeNull();
      expect(new Headers(options?.headers).get('Authorization')).toBeNull();
      expect(options?.body).toBeUndefined();
    }
    expect(port.metadata()).toMatchObject({
      glossary: { entry_count: 212, source_count: 39 },
      effects: { model_calls: 0, business_writes: 0 },
    });
    expect(writes).not.toHaveBeenCalled();
    expect(removes).not.toHaveBeenCalled();
    session.dispose();
  });

  for (const mode of ['bytes', 'sha', 'missing'] as const)
    it(`refuses ${mode} mismatch without accepting a partial learning catalog`, async () => {
      const data = bodies(),
        url = studyFiles[4],
        body = data.get(url)!;
      if (mode === 'bytes') data.set(url, body + ' ');
      else if (mode === 'sha') {
        data.set(url, body + ' ');
        const manifest = jsonObject(parseBody(data, learningManifestUrl));
        const entry = jsonArray(manifest.entries)
          .map(jsonObject)
          .find((row) => row.file === 'learning-ayuan-bazi.json')!;
        entry.bytes = Buffer.byteLength(body + ' ', 'utf8');
        data.set(learningManifestUrl, JSON.stringify(manifest));
      } else data.delete(url);
      fixtureFetch(data);
      await expect(createStudyLoadSession().reload()).rejects.toThrow('样例依据已更新，待重新复核。');
    });

  it('checks closed projection semantics even when the altered asset has matching size and SHA metadata', async () => {
    for (const change of [
      (root: Record<string, unknown>) => {
        root.owner_user_id = 'SYNTHETIC_PRIVATE_SENTINEL';
      },
      (root: Record<string, unknown>) => {
        jsonObject(root.effects).writes = 1;
      },
      (root: Record<string, unknown>) => {
        const card = jsonObject(jsonArray(root.cards)[0]);
        jsonObject(jsonArray(card.evidence_refs)[0]).claim_id = 'demo-claim-' + '0'.repeat(64);
      },
    ]) {
      const data = bodies(),
        url = studyFiles[4],
        root = jsonObject(parseBody(data, url));
      change(root);
      rewriteAsset(data, url, JSON.stringify(root), true);
      fixtureFetch(data);
      await expect(createStudyLoadSession().reload()).rejects.toThrow('样例依据已更新，待重新复核。');
    }
  });

  it('refuses duplicate, escaped or changed-commit manifest entries before reading any data assets', async () => {
    for (const change of [
      (root: Record<string, unknown>) => {
        root.source_commit = 'f'.repeat(40);
      },
      (root: Record<string, unknown>) => {
        jsonObject(jsonArray(root.entries)[0]).file = '../private.json';
      },
      (root: Record<string, unknown>) => {
        const entries = jsonArray(root.entries);
        entries[1] = structuredClone(entries[0]);
      },
    ]) {
      const data = bodies(),
        root = jsonObject(parseBody(data, glossaryManifestUrl));
      change(root);
      data.set(glossaryManifestUrl, JSON.stringify(root));
      const fetcher = fixtureFetch(data);
      await expect(createStudyLoadSession().reload()).rejects.toThrow();
      expect(
        fetcher.mock.calls.every(([url]) =>
          [glossaryManifestUrl, learningManifestUrl].some((file) => file === String(url)),
        ),
      ).toBe(true);
    }
  });

  it('does not follow a redirect or return low-level fetch failure details', async () => {
    for (const mode of ['redirect', 'throw'] as const) {
      const fetcher = fixtureFetch(bodies(), async (url) => {
        if (url !== glossaryManifestUrl) return undefined;
        if (mode === 'throw') throw new TypeError('SYNTHETIC_PRIVATE_FETCH_DETAIL');
        return new Response('', { status: 302, headers: { Location: 'https://untrusted.invalid/study' } });
      });
      const failure = await createStudyLoadSession()
        .reload()
        .catch((reason: unknown) => reason);
      expect(failure).toMatchObject({ code: 'INVALID_DATA', message: '样例依据已更新，待重新复核。' });
      expect(fetcher.mock.calls.every(([url]) => studyFiles.some((file) => file === String(url)))).toBe(true);
    }
  });

  it('accepts verified UTF-8 JSON bytes from a normal Response with empty mock URL, without treating MIME as authority', async () => {
    const data = bodies();
    fixtureFetch(
      data,
      async (url) => new Response(data.get(url), { status: 200, headers: { 'Content-Type': 'text/plain' } }),
    );
    const session = createStudyLoadSession();
    expect((await session.reload()).metadata().glossary.entry_count).toBe(212);
    session.dispose();
  });

  it('revokes a loaded scope immediately when reload begins, and a failed reload cannot leave it active', async () => {
    const data = bodies();
    let broken = false;
    fixtureFetch(data, async (url) =>
      broken && url === glossaryManifestUrl ? new Response('{', { status: 200 }) : undefined,
    );
    const session = createStudyLoadSession(),
      oldPort = await session.reload(),
      oldScope = oldPort.createScope();
    const ref = evidenceRef(bundle().learning[0]);
    await oldScope.readLearning(ref.sample_id);
    expect(oldScope.resolveEvidence(ref)).toBeDefined();
    broken = true;
    const pending = session.reload(),
      rejected = expect(pending).rejects.toThrow();
    expect(oldScope.resolveEvidence(ref)).toBeUndefined();
    expect(() => oldPort.createScope()).toThrow();
    await rejected;
    broken = false;
    const freshPort = await session.reload(),
      freshScope = freshPort.createScope();
    expect(freshScope.resolveEvidence(ref)).toBeUndefined();
    await freshScope.readLearning(ref.sample_id);
    expect(freshScope.resolveEvidence(ref)).toBeDefined();
    session.dispose();
  });

  it('ignores an older successful network completion after a newer reload has returned a valid port', async () => {
    const data = bodies(),
      held = gate<void>();
    let delay = 2;
    fixtureFetch(data, async (url) => {
      if (url.endsWith('/manifest.json') && delay > 0) {
        delay--;
        await held.promise;
      }
      return undefined;
    });
    const session = createStudyLoadSession();
    const old = session.reload(),
      rejected = expect(old).rejects.toMatchObject({ name: 'AbortError' });
    const freshPort = await session.reload(),
      scope = freshPort.createScope();
    const ref = evidenceRef(bundle().learning[0]);
    await scope.readLearning(ref.sample_id);
    held.resolve();
    await rejected;
    expect(scope.resolveEvidence(ref)).toBeDefined();
    session.dispose();
  });

  for (const action of ['reset', 'dispose', 'abort'] as const)
    it(`${action} while loading prevents a late catalog from becoming usable`, async () => {
      const held = gate<void>(),
        controller = new AbortController();
      const fetcher = fixtureFetch(bodies(), async (url) => {
        if (url.endsWith('/manifest.json')) await held.promise;
        return undefined;
      });
      const session = createStudyLoadSession();
      const pending = session.reload(controller.signal),
        rejected = expect(pending).rejects.toMatchObject({ name: 'AbortError' });
      if (action === 'abort') controller.abort();
      else session[action]();
      held.resolve();
      await rejected;
      if (action === 'dispose') {
        const previousCalls = fetcher.mock.calls.length;
        await expect(session.reload()).rejects.toMatchObject({ code: 'DISPOSED' });
        expect(fetcher).toHaveBeenCalledTimes(previousCalls);
      }
      session.dispose();
    });
});
