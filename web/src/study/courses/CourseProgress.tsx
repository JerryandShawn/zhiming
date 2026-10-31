import { useEffect, useRef, useState } from 'react';
import { DraftApiError, writeIntent } from '../../modules/draftApi';
import { Button, Input } from '../../components/ui/Controls';
import type { StudyProgressHttpPort, StudyProgressStatus, StudyProgressView } from '../progressHttp';

type Props = { port: StudyProgressHttpPort; lessonId: string; lessonVersion: string };

export function CourseProgress({ port, lessonId, lessonVersion }: Props) {
  const [view, setView] = useState<StudyProgressView>();
  const [bookmark, setBookmark] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [conflict, setConflict] = useState(false);
  const owner = useRef({ signal: new AbortController().signal, isCurrent: () => true, headers: () => ({}) }).current;

  useEffect(() => {
    let current = true;
    setView(undefined);
    setError('');
    setConflict(false);
    void port.read(lessonId, owner).then(
      (value) => {
        if (!current) return;
        setView(value);
        setBookmark(value.progress?.bookmark ?? '');
      },
      (reason: unknown) => {
        if (current) setError(reason instanceof DraftApiError ? reason.message : '本课进度暂未读取成功。');
      },
    );
    return () => {
      current = false;
    };
  }, [port, lessonId, attempt, owner]);

  async function save(status: StudyProgressStatus) {
    if (!view || busy || conflict) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const intent = writeIntent(view.revision, {
        lesson_version: lessonVersion,
        status,
        bookmark: bookmark.trim() || null,
      });
      await port.put(lessonId, intent, owner);
      const confirmed = await port.read(lessonId, owner);
      setView(confirmed);
      setBookmark(confirmed.progress?.bookmark ?? '');
      setNotice(status === 'completed' ? '已按你的标记记录完成；不代表理解或评测通过。' : '已按你的标记改为继续学习。');
    } catch (reason) {
      if (reason instanceof DraftApiError) {
        setError(reason.message);
        setConflict(['REVISION_CONFLICT', 'IDEMPOTENCY_CONFLICT'].includes(reason.code));
      } else setError('本课进度尚未确认保存，书签草稿仍在。');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="stack small course-progress" aria-label="本课研习进度">
      <h4>本课进度</h4>
      <p className="meta">仅本页合成服务，刷新重置；完成只表示你的标记，不证明理解或评测通过。</p>
      {!view && !error && <p role="status">正在读取本课进度…</p>}
      {view && (
        <>
          <p className="meta">
            {view.progress?.status === 'completed' ? '你已标记完成。' : '继续学习。'}
            {view.progress?.bookmark ? ` 当前书签：${view.progress.bookmark}` : ''}
          </p>
          <Input
            aria-label="本课书签"
            value={bookmark}
            maxLength={200}
            disabled={busy || conflict}
            onChange={(event) => setBookmark(event.target.value)}
          />
          <div className="row wrap">
            <Button disabled={busy || conflict} onClick={() => void save('completed')}>
              标记本课完成
            </Button>
            <Button variant="ghost" disabled={busy || conflict} onClick={() => void save('in_progress')}>
              继续学习
            </Button>
          </div>
        </>
      )}
      {error && (
        <div role="alert" className="stack small">
          <p>{error}</p>
          <Button onClick={() => setAttempt((value) => value + 1)}>重新核对进度</Button>
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
    </section>
  );
}
