import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Pencil, ShieldCheck } from 'lucide-react';
import { authHeaders, operationNamespace } from '../api/client';
import { Button, Input, Tag } from '../components/ui/Controls';
import { Skeleton } from '../components/ui/Feedback';
import { DraftApiError, receiptSaved, writeIntent } from '../modules/draftApi';
import { createOrganizeFakeFetch } from './fakeServer';
import { organizeHttpPort, type OrganizeProposal, type ReviewGrant } from './http';

type Outcome = { kind: 'idle' | 'busy' | 'done' | 'error'; text: string };

export default function DraftOrganizePage({ preview = false }: { preview?: boolean }) {
  const fetcher = useMemo(() => (preview ? createOrganizeFakeFetch() : fetch), [preview]);
  const port = useMemo(() => organizeHttpPort(fetcher), [fetcher]);
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
  const [proposal, setProposal] = useState<OrganizeProposal>();
  const [review, setReview] = useState<ReviewGrant>();
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [outcome, setOutcome] = useState<Outcome>({ kind: 'idle', text: '' });

  const load = useCallback(async () => {
    setError('');
    try {
      const page = await port.listProposals({ limit: 1 }, owner());
      const current = page.items[0];
      setProposal(current);
      setTitle(current?.topics[0]?.title ?? '');
    } catch (reason) {
      setError(reason instanceof DraftApiError ? reason.message : '整理建议暂未读取成功。');
    }
  }, [owner, port]);
  useEffect(() => {
    void load();
  }, [load]);

  async function rename(event: FormEvent) {
    event.preventDefault();
    const current = proposal,
      topic = current?.topics[0];
    if (!current || !topic || !title.trim() || title.trim() === topic.title || busy) return;
    setBusy(true);
    setOutcome({ kind: 'busy', text: '正在保存改名…' });
    try {
      const intent = writeIntent(current.revision, {
        edits: [{ kind: 'rename' as const, target_id: topic.id, title: title.trim() }],
      });
      const receipt = await port.edit(current.batch_id, intent, owner());
      if (!receiptSaved(receipt)) throw new DraftApiError('UNKNOWN_RESULT');
      setOutcome({ kind: 'done', text: '改名已保存，旧审阅已失效，请重新核对计划。' });
      setReview(undefined);
      await load();
    } catch (reason) {
      setOutcome({ kind: 'error', text: reason instanceof DraftApiError ? reason.message : '改名尚未确认保存。' });
    } finally {
      setBusy(false);
    }
  }

  async function reviewPlan() {
    const current = proposal;
    if (!current || busy) return;
    setBusy(true);
    setOutcome({ kind: 'busy', text: '正在核对当前精确计划…' });
    try {
      const intent = writeIntent(current.revision, {
        plan_fingerprint: current.plan_fingerprint,
        accepted: true as const,
      });
      const result = await port.review(current.batch_id, intent, owner());
      setReview(result.review);
      setOutcome({ kind: 'done', text: `审阅凭证已签发，有效期至 ${result.review.expires_at}。` });
      await load();
    } catch (reason) {
      setOutcome({ kind: 'error', text: reason instanceof DraftApiError ? reason.message : '当前计划尚未审阅成功。' });
    } finally {
      setBusy(false);
    }
  }

  async function applyPlan() {
    const current = proposal;
    if (!current || !review || busy) return;
    setBusy(true);
    setOutcome({ kind: 'busy', text: '正在核对应用资格…' });
    try {
      const intent = writeIntent(current.revision, {
        plan_fingerprint: current.plan_fingerprint,
        review_receipt_id: review.receipt_id,
      });
      await port.apply(current.batch_id, intent, owner());
      setOutcome({ kind: 'done', text: '应用已由程序回执确认。' });
    } catch (reason) {
      setOutcome({ kind: 'error', text: reason instanceof DraftApiError ? reason.message : '整理尚未应用。' });
    } finally {
      setBusy(false);
    }
  }

  if (error?.includes('服务端尚未开放'))
    return (
      <div className="page" data-page="organize-review">
        <h1>旧对话审阅</h1>
        <p role="status">{error}</p>
        <a className="text-link" href="?spaces=demo#/organize-review">
          查看合成审阅
        </a>
      </div>
    );

  const topic = proposal?.topics[0];
  return (
    <div
      className="page stack"
      data-page="organize-review"
      data-runtime={preview ? 'organize-draft-fake' : 'organize-draft-live'}>
      <header className="stack small">
        <h1>旧对话审阅</h1>
        <p className="secondary-text">先核对区、话题和精确计划，再决定能否应用。原消息不改写。</p>
        {preview && <p className="meta">合成服务：只在本页内存，刷新重置；质量门仍为 record_only。</p>}
      </header>
      {error && (
        <div className="error-banner" role="alert">
          <p>{error}</p>
          <Button onClick={() => void load()}>重新读取</Button>
        </div>
      )}
      {!proposal && !error && <Skeleton label="正在读取整理建议" />}
      {proposal && topic && (
        <>
          <section className="section stack small" aria-labelledby="draft-proposal-title">
            <div className="row between wrap">
              <h2 id="draft-proposal-title">{topic.title}</h2>
              <Tag>仅建议与人工审阅</Tag>
            </div>
            <p className="secondary-text">{topic.sample}</p>
            <p className="meta">
              {topic.message_ids.length} 条消息 · 把握 {Math.round(topic.confidence * 100)}% · 当前第{' '}
              {proposal.revision} 版
            </p>
            <form className="row wrap" onSubmit={rename}>
              <Input
                aria-label="话题名称"
                value={title}
                maxLength={80}
                disabled={busy}
                onChange={(event) => setTitle(event.target.value)}
              />
              <Button type="submit" disabled={busy || !title.trim() || title.trim() === topic.title}>
                <Pencil className="icon small" aria-hidden="true" />
                保存改名
              </Button>
            </form>
          </section>
          <section className="section stack small" aria-labelledby="draft-review-title">
            <h2 id="draft-review-title">精确计划审阅</h2>
            <p className="meta">
              计划指纹：{proposal.plan_fingerprint.slice(0, 12)}… · 质量门：{proposal.quality_gate}
            </p>
            <div className="row wrap">
              <Button disabled={busy} onClick={() => void reviewPlan()}>
                <ShieldCheck className="icon small" aria-hidden="true" />
                审阅当前计划
              </Button>
              <Button variant="primary" disabled={busy || !review} onClick={() => void applyPlan()}>
                核对应用资格
              </Button>
            </div>
            {review && <p className="meta">已绑定当前批次与精确计划，审阅凭证不代表质量门已开放。</p>}
          </section>
        </>
      )}
      <div aria-live="polite" className="stack small">
        {outcome.kind !== 'idle' && <p className={outcome.kind === 'error' ? 'error-text' : 'meta'}>{outcome.text}</p>}
      </div>
    </div>
  );
}
