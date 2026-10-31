import { publicAssetPath } from '../../publicAsset';
import { StudyDataError, studyNeed } from '../validation';
import { readCourse } from './readCourse';
import type { CourseData } from './types';

export const COURSE_URL = '/data/study/courses-v5/course.json';
export const COURSE_SHA = '016e6e3707c2f9e71ba61cc5663127d93e51f4a811029b2040f1f4d5db492500';
export const COURSE_BYTES = 146197;
export type CourseLoader = (signal: AbortSignal) => Promise<CourseData>;
/** One pinned, same-origin public asset. No identities, cookies, progress writes or source URLs. */
export const loadCourse: CourseLoader = async (signal) => {
  try {
    signal.throwIfAborted();
    const response = await fetch(publicAssetPath(COURSE_URL), {
      method: 'GET',
      signal,
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
    });
    studyNeed(response.ok && !response.redirected);
    const body = await response.arrayBuffer();
    studyNeed(body.byteLength === COURSE_BYTES);
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', body)), (byte) =>
      byte.toString(16).padStart(2, '0'),
    ).join('');
    studyNeed(hash === COURSE_SHA);
    const data = readCourse(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(body)));
    signal.throwIfAborted();
    return data;
  } catch {
    if (signal.aborted) throw new DOMException('Course read cancelled', 'AbortError');
    throw new StudyDataError();
  }
};
