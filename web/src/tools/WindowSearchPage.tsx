import { useEffect, useId, useMemo, useState } from 'react';
import { Button } from '../components/ui/Controls';
import { Skeleton } from '../components/ui/Feedback';
import { useToolRead, type ToolViewOwnership } from './useToolRead';
import { validateWindowInput } from './inputValidation';
import { ToolInputErrors, ToolQuerySummary, windowInputLabels, type InputTargets } from './ToolInputFeedback';
import { WindowSearchForm } from './WindowSearchForm';
import WindowResults from './WindowResults';
import type { InputValidation, WindowField } from './inputValidationTypes';
import type { ToolPort, WindowQuery, WindowSample } from './types';
import './tool-input.css';
export { windowChoiceLabel } from './WindowSearchForm';

const initial: WindowQuery = { purpose: '签约', startDate: '2026-10-21', endDate: '2026-10-27', offset: 0, limit: 31 };
const noIssues = [] as const;
export default function WindowSearchPage({ port }: { port: ToolPort }) {
  const [selection, setSelection] = useState<{ owner: ToolPort; query: WindowQuery }>(() => ({
    owner: port,
    query: port.windows[0] ?? initial,
  }));
  const query = selection.owner === port ? selection.query : (port.windows[0] ?? initial);
  const { view, reset, run, ownership } = useToolRead<WindowSample>(port);
  const [snapshot, setSnapshot] = useState<{
    owner: ToolViewOwnership;
    value: InputValidation<WindowQuery, WindowField>;
  }>();
  const checked = snapshot?.owner === ownership ? snapshot.value : undefined;
  const issues = checked?.status === 'invalid' ? checked.issues : noIssues;
  const prefix = `window-input-${useId()}`;
  const targets = useMemo<InputTargets<WindowField>>(
    () => ({
      purpose: `${prefix}-purpose`,
      startDate: `${prefix}-startDate`,
      endDate: `${prefix}-endDate`,
      offset: `${prefix}-pagination`,
      limit: `${prefix}-pagination`,
      query: `${prefix}-errors`,
    }),
    [prefix],
  );
  useEffect(reset, [port, reset]);
  function change(next: WindowQuery) {
    reset();
    setSelection({ owner: port, query: next });
    setSnapshot(undefined);
  }
  function read() {
    reset();
    const value = validateWindowInput(query);
    setSnapshot({ owner: ownership, value });
    if (value.status === 'valid') void run((signal) => port.windowSearch(value.query, signal));
  }
  const compatible = port.windows.filter(
    (item) => item.purpose === query.purpose && item.startDate === query.startDate && item.endDate === query.endDate,
  );
  return (
    <section
      className="stack tool-window"
      aria-labelledby="window-title"
      data-input-status={checked?.status ?? 'unchecked'}>
      <h1 id="window-title" tabIndex={-1}>
        择日 · 看一段时间的条件
      </h1>
      <p>当前只有签约 10 月 21–27 日的固定合成样例。换条件不会借用旧结果，也不会发起实时计算。</p>
      <form
        className="tool-form"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          read();
        }}>
        <ToolInputErrors issues={issues} targets={targets} prefix={prefix} labels={windowInputLabels} />
        <WindowSearchForm
          query={query}
          compatible={compatible}
          issues={issues}
          prefix={prefix}
          targets={targets}
          change={change}
        />
        <div className="row wrap">
          <Button type="submit" variant="primary" loading={view.status === 'loading'}>
            查看当前样例条件
          </Button>
          <Button variant="ghost" onClick={() => change(port.windows[0] ?? initial)}>
            恢复已发布条件
          </Button>
        </div>
      </form>
      {checked?.status === 'valid' && <ToolQuerySummary summary={checked.summary} />}
      {view.status === 'idle' && <p className="meta">先核对用途、区间和样例页，再查看结果。</p>}
      {view.status === 'loading' && <Skeleton label="正在载入择日样例" />}
      {view.status === 'error' && (
        <div role="alert">
          <p>{view.message}</p>
          <Button onClick={read}>用当前条件重试</Button>
        </div>
      )}
      {view.status === 'unavailable' && (
        <p role="status" data-published-state="unavailable">
          字段格式已核对；暂无对应已发布样例。{view.message}
        </p>
      )}
      {view.status === 'ready' && <WindowResults key={view.sample.document_id} sample={view.sample} port={port} />}
    </section>
  );
}
