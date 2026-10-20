import { useEffect, useState } from 'react';
import { Button, Input } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import { Skeleton } from '../components/ui/Feedback';
import { purposes, windowKey } from './port';
import { useToolRead } from './useToolRead';
import WindowResults from './WindowResults';
import type { Purpose, ToolPort, WindowChoice, WindowQuery, WindowSample } from './types';

const initial: WindowQuery = { purpose: '签约', startDate: '2026-10-21', endDate: '2026-10-27', offset: 0, limit: 31 };
export const windowChoiceLabel = ({ summary }: WindowChoice) =>
  !summary.returned
    ? '末尾空页'
    : summary.returned === summary.total
      ? `全部 ${summary.total} 天`
      : summary.first_rank === summary.last_rank
        ? `第 ${summary.first_rank} 名`
        : `第 ${summary.first_rank}–${summary.last_rank} 名`;
export default function WindowSearchPage({ port }: { port: ToolPort }) {
  const [selection, setSelection] = useState<{ owner: ToolPort; query: WindowQuery }>(() => ({
    owner: port,
    query: port.windows[0] ?? initial,
  }));
  const query = selection.owner === port ? selection.query : (port.windows[0] ?? initial);
  const { view, reset, run } = useToolRead<WindowSample>(port);
  useEffect(reset, [port, reset]);
  function change(next: WindowQuery) {
    reset();
    setSelection({ owner: port, query: next });
  }
  const compatible = port.windows.filter(
    (item) => item.purpose === query.purpose && item.startDate === query.startDate && item.endDate === query.endDate,
  );
  return (
    <section className="stack tool-window" aria-labelledby="window-title">
      <h1 id="window-title" tabIndex={-1}>
        择日 · 看一段时间的条件
      </h1>
      <p>当前只有签约 10 月 21–27 日的固定合成样例。换条件不会借用旧结果，也不会发起实时计算。</p>
      <form
        className="tool-form"
        onSubmit={(event) => {
          event.preventDefault();
          void run((signal) => port.windowSearch(query, signal));
        }}>
        <Select
          label="用途"
          value={query.purpose}
          options={purposes.map((value) => ({ value, label: value }))}
          onChange={(purpose) => change({ ...query, purpose: purpose as Purpose })}
        />
        <label className="field">
          起始日期（北京时间）
          <Input
            type="date"
            value={query.startDate}
            onChange={(event) => change({ ...query, startDate: event.target.value })}
            required
          />
        </label>
        <label className="field">
          结束日期（含当日）
          <Input
            type="date"
            value={query.endDate}
            onChange={(event) => change({ ...query, endDate: event.target.value })}
            required
          />
        </label>
        {!!compatible.length && (
          <Select
            label="查看范围"
            value={windowKey(query)}
            options={compatible.map((item) => ({ value: windowKey(item), label: windowChoiceLabel(item) }))}
            onChange={(value) => {
              const next = compatible.find((item) => windowKey(item) === value);
              if (next) change(next);
            }}
          />
        )}
        <div className="row wrap">
          <Button type="submit" variant="primary" loading={view.status === 'loading'}>
            查看当前样例条件
          </Button>
          <Button variant="ghost" onClick={() => change(port.windows[0] ?? initial)}>
            恢复已发布条件
          </Button>
        </div>
      </form>
      {view.status === 'idle' && <p className="meta">先核对用途、区间和样例页，再查看结果。</p>}
      {view.status === 'loading' && <Skeleton label="正在载入择日样例" />}
      {view.status === 'error' && (
        <div role="alert">
          <p>{view.message}</p>
          <Button onClick={() => void run((signal) => port.windowSearch(query, signal))}>用当前条件重试</Button>
        </div>
      )}
      {view.status === 'unavailable' && <p role="status">{view.message}</p>}
      {view.status === 'ready' && <WindowResults key={view.sample.document_id} sample={view.sample} port={port} />}
    </section>
  );
}
