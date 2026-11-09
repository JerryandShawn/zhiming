import { useEffect, useId, useMemo, useState } from 'react';
import { Button } from '../components/ui/Controls';
import { Skeleton } from '../components/ui/Feedback';
import { synastryKey } from './port';
import { useToolRead, type ToolViewOwnership } from './useToolRead';
import { validateSynastryInput } from './inputValidation';
import { ToolInputErrors, ToolQuerySummary, synastryInputLabels, type InputTargets } from './ToolInputFeedback';
import { SynastryForm, synastryCandidate, synastryDraftKey, type SynastryDraft } from './SynastryForm';
import { SynastryConsent } from './SynastryConsent';
import SynastryResults from './SynastryResults';
import type { InputValidation, SynastryField } from './inputValidationTypes';
import type { FreshConsent, SynastryQuery, SynastrySample, ToolPort } from './types';
import './tool-input.css';

const initial: SynastryDraft = { a: 'ayuan', b: 'xiaohe', kind: 'romantic', asOfDate: '2026-10-21', orbDegrees: '6' };
type ConsentState = { owner: ToolViewOwnership; draftKey: string; a: boolean; b: boolean };
const noIssues = [] as const;
export default function SynastryPage({ port }: { port: ToolPort }) {
  const [draft, setDraft] = useState(initial);
  const { view, reset, run, ownership } = useToolRead<SynastrySample>(port);
  const key = synastryDraftKey(draft);
  const [consent, setConsent] = useState<ConsentState>({ owner: ownership, draftKey: key, a: false, b: false });
  const confirmed = consent.owner === ownership && consent.draftKey === key;
  const authorized = confirmed && consent.a && consent.b;
  const [snapshot, setSnapshot] = useState<{
    owner: ToolViewOwnership;
    value: InputValidation<SynastryQuery, SynastryField>;
  }>();
  const checked = snapshot?.owner === ownership ? snapshot.value : undefined;
  const issues = checked?.status === 'invalid' ? checked.issues : noIssues;
  const prefix = `synastry-input-${useId()}`;
  const targets = useMemo<InputTargets<SynastryField>>(
    () => ({
      a: `${prefix}-a`,
      b: `${prefix}-b`,
      kind: `${prefix}-kind`,
      asOfDate: `${prefix}-asOfDate`,
      orbDegrees: `${prefix}-orbDegrees`,
      query: `${prefix}-errors`,
    }),
    [prefix],
  );
  useEffect(() => {
    reset();
    setConsent((old) => ({ ...old, owner: ownership, a: false, b: false }));
  }, [ownership, reset]);
  function revoke(next = draft) {
    reset();
    setConsent({ owner: ownership, draftKey: synastryDraftKey(next), a: false, b: false });
  }
  function change(next: SynastryDraft) {
    revoke(next);
    setDraft(next);
    setSnapshot(undefined);
  }
  function check() {
    reset();
    const value = validateSynastryInput(synastryCandidate(draft));
    setSnapshot({ owner: ownership, value });
    return value;
  }
  function read() {
    const value = check();
    if (value.status !== 'valid' || !authorized) return;
    const fresh: FreshConsent = { queryKey: synastryKey(value.query), a: true, b: true };
    void run((signal) => port.synastry(value.query, fresh, signal));
  }
  return (
    <section
      className="stack tool-synastry"
      aria-labelledby="synastry-title"
      data-input-status={checked?.status ?? 'unchecked'}>
      <h1 id="synastry-title" tabIndex={-1}>
        合盘 · 先确认，再看结构
      </h1>
      <p>当前只有阿远与小禾的亲密关系、2026-10-21、容许度 6° 固定合成样例。没有接入真实资料或计算 API。</p>
      <form
        className="tool-form"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          read();
        }}>
        <ToolInputErrors issues={issues} targets={targets} prefix={prefix} labels={synastryInputLabels} />
        <SynastryForm draft={draft} issues={issues} prefix={prefix} targets={targets} change={change} />
        <SynastryConsent
          draft={draft}
          checked={{ a: confirmed && consent.a, b: confirmed && consent.b }}
          onChange={(side, value) => {
            reset();
            setConsent((old) => ({
              ...(old.owner === ownership && old.draftKey === key ? old : { a: false, b: false }),
              owner: ownership,
              draftKey: key,
              [side]: value,
            }));
          }}
        />
        <div className="row wrap">
          <Button onClick={check}>核对查询条件</Button>
          <Button type="submit" variant="primary" disabled={!authorized} loading={view.status === 'loading'}>
            查看已确认的样例
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              revoke();
              setSnapshot(undefined);
            }}>
            撤回本次展示
          </Button>
          <Button variant="ghost" onClick={() => change(initial)}>
            恢复样例条件
          </Button>
        </div>
      </form>
      {checked?.status === 'valid' && <ToolQuerySummary summary={checked.summary} />}
      {!authorized && (
        <p role="status">尚未分别确认双方本次展示，盘面结果尚未展开。公开合成样例的预载不代表本次确认。</p>
      )}
      {authorized && view.status === 'idle' && <p className="meta">本次条件已确认，点击查看后展开固定样例。</p>}
      {authorized && view.status === 'loading' && <Skeleton label="正在载入合盘样例" />}
      {authorized && view.status === 'error' && (
        <div role="alert">
          <p>{view.message}</p>
          <Button onClick={read}>用本次确认重试</Button>
        </div>
      )}
      {authorized && view.status === 'unavailable' && (
        <p role="status" data-published-state="unavailable">
          字段格式已核对；暂无对应已发布样例。{view.message}
        </p>
      )}
      {authorized && view.status === 'ready' && (
        <SynastryResults key={view.sample.document_id} sample={view.sample} port={port} />
      )}
    </section>
  );
}
