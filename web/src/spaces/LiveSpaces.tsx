import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type FormEvent } from 'react';
import { Archive, ArchiveRestore, Lock, Pencil } from 'lucide-react';
import { authHeaders, operationNamespace } from '../api/client';
import { Button, Disclosure, Input, Tag } from '../components/ui/Controls';
import { Skeleton } from '../components/ui/Feedback';
import { DraftApiError, receiptSaved, writeIntent, type Receipt } from '../modules/draftApi';
import { formatSpaceTime } from './SpaceNavigation';
import { createSpacesFakeFetch } from './fakeServer';
import { spacesTopicsHttpPort, type ApiSpace, type ApiTopic, type TopicPatch } from './http';
import './live-spaces.css';

type Pending = { key: string; run: () => Promise<Receipt>; label: string };
type Outcome = { kind: 'idle' | 'busy' | 'done' | 'queued' | 'error'; text: string; error?: DraftApiError };
const subscribe = (listener: () => void) => {
  window.addEventListener('hashchange', listener);
  return () => window.removeEventListener('hashchange', listener);
};
const errorOf = (error: unknown) => (error instanceof DraftApiError ? error : new DraftApiError('BAD_RESPONSE'));

export default function LiveSpaces({ preview = false }: { preview?: boolean }) {
  const fetcher = useMemo(() => (preview ? createSpacesFakeFetch({ delayMs: 120 }) : fetch), [preview]);
  const port = useMemo(() => spacesTopicsHttpPort(fetcher), [fetcher]);
  const lifetime = useRef(new AbortController());
  const namespace = useRef(operationNamespace());
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, []);
  const owner = useCallback(
    () => ({
      signal: lifetime.current.signal,
      isCurrent: () => namespace.current === operationNamespace(),
      headers: () => (preview ? {} : authHeaders()),
    }),
    [preview],
  );
  const hash = useSyncExternalStore(subscribe, () => location.hash);
  const requested = new URLSearchParams(hash.split('?')[1]).get('space');
  const [spaces, setSpaces] = useState<readonly ApiSpace[]>();
  const [topics, setTopics] = useState<readonly ApiTopic[]>();
  const [loadError, setLoadError] = useState<DraftApiError>();
  const [outcome, setOutcome] = useState<Outcome>({ kind: 'idle', text: '' });
  const [pending, setPending] = useState<Pending>();
  const [title, setTitle] = useState('');
  const [editing, setEditing] = useState<{ id: string; title: string }>();
  const current = spaces?.find((item) => item.id === requested) ?? spaces?.[0];

  const loadSpaces = useCallback(async () => {
    setLoadError(undefined);
    try {
      setSpaces((await port.listSpaces({}, owner())).items);
    } catch (error) {
      const failure = errorOf(error);
      if (failure.code !== 'OBSOLETE') setLoadError(failure);
    }
  }, [owner, port]);
  const loadTopics = useCallback(
    async (spaceId: string) => {
      setTopics(undefined);
      try {
        setTopics((await port.listTopics(spaceId, { limit: 100 }, owner())).items);
      } catch (error) {
        const failure = errorOf(error);
        if (failure.code !== 'OBSOLETE') setLoadError(failure);
      }
    },
    [owner, port],
  );
  useEffect(() => {
    void loadSpaces();
  }, [loadSpaces]);
  useEffect(() => {
    if (current) void loadTopics(current.id);
  }, [current, loadTopics]);

  // One intent per business action; a resend after an unknown outcome reuses it verbatim.
  async function perform(action: Pending, after?: () => void) {
    setPending(action);
    setOutcome({ kind: 'busy', text: `${action.label}…` });
    try {
      const receipt = await action.run();
      setPending(undefined);
      after?.();
      setOutcome(
        receiptSaved(receipt)
          ? { kind: 'done', text: `${action.label}已保存。` }
          : { kind: 'queued', text: `${action.label}已排队，尚未确认保存。` },
      );
      if (current) void loadTopics(current.id);
    } catch (error) {
      const failure = errorOf(error);
      if (failure.code === 'OBSOLETE') return;
      if (!failure.resendSame) setPending(undefined);
      setOutcome({ kind: 'error', text: failure.message, error: failure });
    }
  }
  function create(event: FormEvent) {
    event.preventDefault();
    if (!current || !title.trim()) return;
    const intent = writeIntent(0, { title: title.trim() });
    const spaceId = current.id;
    void perform({ key: 'create', label: '新建话题', run: () => port.createTopic(spaceId, intent, owner()) }, () =>
      setTitle(''),
    );
  }
  function change(topic: ApiTopic, patch: TopicPatch, label: string, after?: () => void) {
    const intent = writeIntent(topic.revision, { patch });
    void perform({ key: topic.id, label, run: () => port.patchTopic(topic.id, intent, owner()) }, after);
  }

  if (loadError?.code === 'DRAFT_NOT_IMPLEMENTED')
    return (
      <div className="page live-spaces" data-page="spaces">
        <header className="page-heading">
          <h1>区与话题</h1>
        </header>
        <div className="section" role="status">
          <p>服务端尚未开放区与话题接口。对话和记忆不受影响。</p>
          <a className="text-link" href="?spaces=demo#/chat">
            先看合成预览
          </a>
        </div>
      </div>
    );
  const busy = outcome.kind === 'busy';
  const conflict = ['REVISION_CONFLICT', 'IDEMPOTENCY_CONFLICT', 'REVIEW_PLAN_CHANGED'].includes(
    outcome.error?.code ?? '',
  );
  const open = topics?.filter((item) => item.status !== 'archived') ?? [];
  const archived = topics?.filter((item) => item.status === 'archived') ?? [];
  const row = (topic: ApiTopic) => (
    <li key={topic.id} className="live-topic">
      {editing?.id === topic.id ? (
        <form
          className="row wrap"
          onSubmit={(event) => {
            event.preventDefault();
            if (editing.title.trim() && editing.title.trim() !== topic.title)
              change(topic, { title: editing.title.trim() }, '改名', () => setEditing(undefined));
          }}>
          <Input
            aria-label={`新的话题名：${topic.title}`}
            value={editing.title}
            maxLength={80}
            onChange={(event) => setEditing({ id: topic.id, title: event.target.value })}
          />
          <Button type="submit" variant="primary" disabled={busy || conflict}>
            保存
          </Button>
          <Button onClick={() => setEditing(undefined)}>取消</Button>
        </form>
      ) : (
        <div className="row between wrap">
          <div>
            <h3>{topic.title}</h3>
            <p className="meta">
              {topic.status === 'case' && <Tag>已关联事项</Tag>} 最近 {formatSpaceTime(topic.last_at)}
            </p>
            {topic.summary && <p className="secondary-text">{topic.summary}</p>}
          </div>
          <div className="row wrap live-topic-actions">
            <Button
              disabled={busy || conflict}
              aria-label={`改名：${topic.title}`}
              onClick={() => setEditing({ id: topic.id, title: topic.title })}>
              <Pencil className="icon small" aria-hidden="true" />
              改名
            </Button>
            <Button
              disabled={busy || conflict}
              aria-label={`${topic.status === 'archived' ? '恢复' : '归档'}：${topic.title}`}
              onClick={() =>
                change(
                  topic,
                  { status: topic.status === 'archived' ? 'open' : 'archived' },
                  topic.status === 'archived' ? '恢复' : '归档',
                )
              }>
              {topic.status === 'archived' ? (
                <ArchiveRestore className="icon small" aria-hidden="true" />
              ) : (
                <Archive className="icon small" aria-hidden="true" />
              )}
              {topic.status === 'archived' ? '恢复' : '归档'}
            </Button>
            <label className="live-topic-move">
              <span className="sr-only">移动「{topic.title}」到</span>
              <select
                className="input"
                value={topic.space_id}
                disabled={busy || conflict}
                onChange={(event) => change(topic, { space_id: event.target.value }, '移动')}>
                {spaces?.map((space) => (
                  <option key={space.id} value={space.id}>
                    {space.id === topic.space_id ? `在「${space.name}」` : `移到「${space.name}」`}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
      )}
    </li>
  );
  return (
    <div className="page live-spaces" data-page="spaces" data-runtime={preview ? 'spaces-fake' : 'spaces-live'}>
      <header className="page-heading">
        <h1>区与话题</h1>
        <p className="secondary-text">
          {preview ? '合成服务预览：数据只在本页内存里，刷新即还原。' : '移动、归档都不会删除原来的对话和记忆。'}
        </p>
      </header>
      {loadError && (
        <div className="error-banner" role="alert">
          <p>{loadError.message}</p>
          <Button onClick={() => void (current ? loadTopics(current.id) : loadSpaces())}>重新读取</Button>
        </div>
      )}
      {!spaces && !loadError && <Skeleton label="正在读取区" />}
      {spaces && (
        <div className="live-spaces-layout">
          <nav aria-label="区" className="live-space-list">
            {spaces.map((space) => (
              <a
                key={space.id}
                className="spaces-link"
                href={`#/spaces?space=${encodeURIComponent(space.id)}`}
                aria-current={current?.id === space.id ? 'page' : undefined}>
                <Tag tone={current?.id === space.id ? 'accent' : 'neutral'}>
                  {space.sensitive && <Lock className="icon small" role="img" aria-label="敏感区" />}
                  {space.name}
                </Tag>
              </a>
            ))}
          </nav>
          <section className="section live-topics" aria-labelledby="live-topics-title">
            <h2 id="live-topics-title">{current?.name ?? '区'}的话题</h2>
            {current?.sensitive && <p className="meta">敏感区 · 读取和写入都按当前用途授权核对。</p>}
            <form className="row wrap live-topic-create" onSubmit={create}>
              <Input
                aria-label="新话题名称"
                placeholder="新话题名称"
                value={title}
                maxLength={80}
                onChange={(event) => setTitle(event.target.value)}
              />
              <Button type="submit" variant="primary" disabled={!title.trim() || busy || conflict}>
                新建话题
              </Button>
            </form>
            <div aria-live="polite" className="live-spaces-status">
              {outcome.kind !== 'idle' && (
                <p className={outcome.kind === 'error' ? 'error-text' : 'meta'}>{outcome.text}</p>
              )}
              {outcome.kind === 'error' && pending && outcome.error?.resendSame && (
                <Button onClick={() => void perform(pending)}>用原请求再核对</Button>
              )}
              {conflict && current && (
                <Button
                  onClick={() => {
                    setOutcome({ kind: 'idle', text: '' });
                    void loadTopics(current.id);
                  }}>
                  刷新后核对
                </Button>
              )}
            </div>
            {!topics && !loadError && <Skeleton label="正在读取话题" />}
            {topics && !open.length && <p className="meta">这个区还没有话题。</p>}
            {open.length > 0 && <ul className="live-topic-list">{open.map(row)}</ul>}
            {archived.length > 0 && (
              <Disclosure title={`已归档 ${archived.length} 个`}>
                <ul className="live-topic-list">{archived.map(row)}</ul>
              </Disclosure>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
