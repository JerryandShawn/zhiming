import {
  DraftApiError,
  draftRequest,
  exactKeys,
  isId,
  isRevision,
  isText,
  record,
  writeResult,
  type Receipt,
  type WriteIdentity,
} from '../modules/draftApi';
import type { RequestOwner } from '../threads/request';

// mod api_study_draft 0.1.0 @ daccd26c. Personal progress is separate from public course content.
export type StudyProgressStatus = 'not_started' | 'in_progress' | 'completed';
export type StudyProgress = Readonly<{
  lesson_id: string;
  lesson_version: string;
  revision: number;
  status: StudyProgressStatus;
  bookmark: string | null;
}>;
export type StudyProgressView = Readonly<{ progress: StudyProgress | null; revision: number }>;
export type StudyProgressUpdate = WriteIdentity & {
  lesson_version: string;
  status: StudyProgressStatus;
  bookmark: string | null;
};

const bad = () => new DraftApiError('BAD_RESPONSE');
const status = (value: unknown): value is StudyProgressStatus =>
  ['not_started', 'in_progress', 'completed'].includes(value as string);
const version = (value: unknown): value is string => isText(value, 1, 64);
const bookmark = (value: unknown) => value === null || isText(value, 0, 200);
const segment = (value: string) => {
  if (!isId(value)) throw new DraftApiError('VALIDATION_ERROR');
  return encodeURIComponent(value);
};
function progressView(value: unknown, lessonId: string): StudyProgressView {
  const item = record(value);
  if (
    !exactKeys(item, ['progress', 'revision']) ||
    !Number.isSafeInteger(item.revision) ||
    (item.revision as number) < 0
  )
    throw bad();
  if (item.progress === null) {
    if (item.revision !== 0) throw bad();
    return Object.freeze({ progress: null, revision: 0 });
  }
  const progress = record(item.progress);
  if (
    !exactKeys(progress, ['lesson_id', 'lesson_version', 'revision', 'status', 'bookmark']) ||
    progress.lesson_id !== lessonId ||
    !version(progress.lesson_version) ||
    !isRevision(progress.revision) ||
    progress.revision !== item.revision ||
    !status(progress.status) ||
    !bookmark(progress.bookmark)
  )
    throw bad();
  return Object.freeze({ progress: Object.freeze(progress as StudyProgress), revision: item.revision as number });
}

export type StudyProgressHttpPort = ReturnType<typeof studyProgressHttpPort>;
export function studyProgressHttpPort(fetcher: typeof fetch = fetch) {
  return {
    async read(lessonId: string, owner: RequestOwner): Promise<StudyProgressView> {
      return progressView(
        await draftRequest(fetcher, { method: 'GET', path: `/api/study/progress/${segment(lessonId)}` }, owner),
        lessonId,
      );
    },
    async put(lessonId: string, body: StudyProgressUpdate, owner: RequestOwner): Promise<Receipt> {
      if (
        !exactKeys(record(body), ['request_id', 'expected_revision', 'lesson_version', 'status', 'bookmark']) ||
        !Number.isSafeInteger(body.expected_revision) ||
        body.expected_revision < 0 ||
        !version(body.lesson_version) ||
        !status(body.status) ||
        !bookmark(body.bookmark)
      )
        throw new DraftApiError('VALIDATION_ERROR');
      return writeResult(
        await draftRequest(fetcher, { method: 'PUT', path: `/api/study/progress/${segment(lessonId)}`, body }, owner),
        body.request_id,
      );
    },
  };
}
