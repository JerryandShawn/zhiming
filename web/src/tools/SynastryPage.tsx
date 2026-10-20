import { useEffect, useState } from 'react';
import { Button, Checkbox, Input } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import { Skeleton } from '../components/ui/Feedback';
import { kindLabels, sampleNames, synastryKey } from './port';
import { useToolRead, type ToolViewOwnership } from './useToolRead';
import SynastryResults from './SynastryResults';
import type { FreshConsent, RelationKind, SynastryQuery, SynastrySample, ToolPort } from './types';
const initial: SynastryQuery = { a: 'ayuan', b: 'xiaohe', kind: 'romantic', asOfDate: '2026-10-21', orbDegrees: 6 };
type ConsentState = { owner: ToolViewOwnership; queryKey: string; a: boolean; b: boolean };
export default function SynastryPage({ port }: { port: ToolPort }) {
  const [query, setQuery] = useState(initial);
  const { view, reset, run, ownership } = useToolRead<SynastrySample>(port);
  const [consent, setConsent] = useState<ConsentState>({
    owner: ownership,
    queryKey: synastryKey(initial),
    a: false,
    b: false,
  });
  const key = synastryKey(query),
    authorized = consent.owner === ownership && consent.queryKey === key && consent.a && consent.b;
  useEffect(() => {
    reset();
    setConsent((old) => ({ ...old, owner: ownership, a: false, b: false }));
  }, [ownership, reset]);
  function revoke(next = query) {
    reset();
    setConsent({ owner: ownership, queryKey: synastryKey(next), a: false, b: false });
  }
  function change(next: SynastryQuery) {
    revoke(next);
    setQuery(next);
  }
  function read() {
    if (!authorized) return;
    const confirmed: FreshConsent = { queryKey: key, a: true, b: true };
    void run((signal) => port.synastry(query, confirmed, signal));
  }
  return (
    <section className="stack tool-synastry" aria-labelledby="synastry-title">
      <h1 id="synastry-title" tabIndex={-1}>
        合盘 · 先确认，再看结构
      </h1>
      <p>当前只有阿远与小禾的亲密关系、2026-10-21、容许度 6° 固定合成样例。没有接入真实资料或计算 API。</p>
      <form
        className="tool-form"
        onSubmit={(event) => {
          event.preventDefault();
          read();
        }}>
        {(['a', 'b'] as const).map((side) => (
          <Select
            key={side}
            label={`${side.toUpperCase()} 方合成对象`}
            value={query[side]}
            options={Object.entries(sampleNames).map(([value, label]) => ({ value, label }))}
            onChange={(value) => change({ ...query, [side]: value })}
          />
        ))}
        <Select
          label="本次比较用途"
          value={query.kind}
          options={Object.entries(kindLabels).map(([value, label]) => ({ value, label }))}
          onChange={(value) => change({ ...query, kind: value as RelationKind })}
        />
        <label className="field">
          核对日期（北京时间）
          <Input
            type="date"
            value={query.asOfDate}
            onChange={(event) => change({ ...query, asOfDate: event.target.value })}
            required
          />
        </label>
        <label className="field">
          统一相位容许度（度）
          <Input
            type="number"
            min={0}
            max={10}
            step="0.1"
            value={Number.isFinite(query.orbDegrees) ? query.orbDegrees : ''}
            onChange={(event) => change({ ...query, orbDegrees: event.target.valueAsNumber })}
            required
          />
        </label>
        <fieldset className="stack tool-consent">
          <legend>分别确认本次展示</legend>
          <p className="meta">
            样例中的历史确认不能替代本次选择。任一条件改变后需重新确认；只在本页内有效，不涵盖保存、分享或发送。
          </p>
          {(['a', 'b'] as const).map((side) => (
            <label className="row" key={side}>
              <Checkbox
                label={`允许本次展示${side.toUpperCase()}方合成盘面`}
                checked={consent.owner === ownership && consent.queryKey === key && consent[side]}
                onChange={(event) => {
                  reset();
                  const checked = event.target.checked;
                  setConsent((old) => ({
                    ...(old.owner === ownership && old.queryKey === key ? old : { a: false, b: false }),
                    owner: ownership,
                    queryKey: key,
                    [side]: checked,
                  }));
                }}
              />
              允许本次展示 {side.toUpperCase()} 方 {sampleNames[query[side]]} 的合成盘面
            </label>
          ))}
        </fieldset>
        <div className="row wrap">
          <Button type="submit" variant="primary" disabled={!authorized} loading={view.status === 'loading'}>
            查看已确认的样例
          </Button>
          <Button variant="ghost" onClick={() => revoke()}>
            撤回本次展示
          </Button>
          <Button variant="ghost" onClick={() => change(initial)}>
            恢复样例条件
          </Button>
        </div>
      </form>
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
      {authorized && view.status === 'unavailable' && <p role="status">{view.message}</p>}
      {authorized && view.status === 'ready' && (
        <SynastryResults key={view.sample.document_id} sample={view.sample} port={port} />
      )}
    </section>
  );
}
