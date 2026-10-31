import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { webcrypto } from 'node:crypto';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadCourse, COURSE_BYTES, COURSE_SHA, COURSE_URL } from '../src/study/courses/loader';
import { readCourse, COURSE_COMMIT } from '../src/study/courses/readCourse';

const body = readFileSync(resolve('public/data/study/courses-v5/course.json'));
const raw = () => JSON.parse(body.toString('utf8')) as Record<string, unknown>;
const object = (value: unknown) => value as Record<string, unknown>;
const list = (value: unknown) => value as Record<string, unknown>[];
const first = (value: Record<string, unknown>) => list(value.lessons)[0];
const signal = () => new AbortController().signal;
beforeEach(() => vi.stubGlobal('crypto', webcrypto));
afterEach(() => vi.unstubAllGlobals());

describe('independent pinned course asset', () => {
  it('loads one public asset without identity, persistence, API or source URL access', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(body));
    vi.stubGlobal('fetch', fetcher);
    const writes = vi.spyOn(Storage.prototype, 'setItem');
    const data = await loadCourse(signal());
    expect(data.lessons).toHaveLength(20);
    expect(data.lessons.flatMap((row) => row.quiz)).toHaveLength(40);
    expect(fetcher).toHaveBeenCalledExactlyOnceWith(COURSE_URL, {
      method: 'GET',
      signal: expect.any(AbortSignal),
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
    });
    expect(writes).not.toHaveBeenCalled();
    expect(body.length).toBe(COURSE_BYTES);
    const digest = Buffer.from(await webcrypto.subtle.digest('SHA-256', body)).toString('hex');
    expect(digest).toBe(COURSE_SHA);
    expect(object(raw().provenance).source_commit).toBe(COURSE_COMMIT);
    expect(data.evidence.filter((row) => row.case_id === 'ayuan-astro').map((row) => row.c_alias)).toEqual(['c7']);
    expect(data).not.toHaveProperty('cases');
  });

  it.each(['length', 'same-length-change', 'redirect', 'http', 'private-error'])(
    'rejects %s with a fixed public error',
    async (mode) => {
      const changed = Buffer.from(body);
      changed[changed.length - 2] = 32;
      const response =
        mode === 'http'
          ? new Response('', { status: 403 })
          : mode === 'redirect'
            ? new Response('', { status: 302 })
            : new Response(mode === 'length' ? body.subarray(1) : changed);
      const fetcher = vi.fn<typeof fetch>();
      if (mode === 'private-error') fetcher.mockRejectedValue(new Error('SECRET_INTERNAL_DETAIL'));
      else fetcher.mockResolvedValue(response);
      vi.stubGlobal('fetch', fetcher);
      await expect(loadCourse(signal())).rejects.toThrow('样例依据已更新，待重新复核。');
    },
  );

  it('does not send a read for an already aborted request', async () => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetcher);
    const controller = new AbortController();
    controller.abort();
    await expect(loadCourse(controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetcher).not.toHaveBeenCalled();
  });

  const mutations: [string, (value: Record<string, unknown>) => void][] = [
    [
      'private root field',
      (value) => {
        value.owner_user_id = 'SECRET';
      },
    ],
    [
      'old commit',
      (value) => {
        object(value.provenance).source_commit = '0'.repeat(40);
      },
    ],
    [
      'business write',
      (value) => {
        object(value.effects).user_writes = 1;
      },
    ],
    [
      'future prerequisite',
      (value) => {
        first(value).prerequisite_ids = ['lesson-20'];
      },
    ],
    [
      'unknown source',
      (value) => {
        first(value).source_ids = ['unknown'];
      },
    ],
    [
      'duplicate evidence',
      (value) => {
        list(value.evidence)[1] = list(value.evidence)[0];
      },
    ],
    [
      'cross-case example',
      (value) => {
        list(first(value).worked_examples)[0].case_id = 'ayuan-astro';
      },
    ],
    [
      'foreign context',
      (value) => {
        list(value.evidence)[0].context_sha256 = '0'.repeat(64);
      },
    ],
    [
      'unknown answer',
      (value) => {
        list(first(value).quiz)[0].correct_option_id = 'unknown';
      },
    ],
    [
      'raw expected value',
      (value) => {
        object(list(first(value).quiz)[0].basis).expected = 'SECRET';
      },
    ],
    [
      'duplicate option',
      (value) => {
        const options = list(list(first(value).quiz)[0].options);
        options[1] = options[0];
      },
    ],
    [
      'fake concept c reference',
      (value) => {
        list(first(value).quiz)[1].evidence_ids = ['year'];
      },
    ],
  ];
  it.each(mutations)('refuses %s even when invoked without the transport', (_name, change) => {
    const value = raw();
    change(value);
    expect(() => readCourse(value)).toThrow();
  });

  it('preserves the right answer after option display order is changed', () => {
    const value = raw(),
      quiz = list(first(value).quiz)[0];
    list(quiz.options).reverse();
    const projected = readCourse(value).lessons[0].quiz[0];
    expect(projected.options[2].option_id).toBe(projected.correct_option_id);
  });
});
