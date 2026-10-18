import { useEffect, useRef, useState } from 'react';
import { Button, Textarea } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import { Markdown } from '../components/Markdown';
import { api } from '../api/client';
import { pendingPayload, write } from '../api/operations';
import {
  clearReading,
  loadReadings,
  markReadingStop,
  pendingReading,
  ReadingStopped,
  requestReading,
} from './readings';
import { object, text, type Reading } from './public';

export function ReadingPanel({
  drawId,
  versions,
  onChange,
  onBusy,
}: {
  drawId: string;
  versions: Reading[];
  onChange: (versions: Reading[]) => void;
  onBusy: (value: boolean) => void;
}) {
  const [selected, setSelected] = useState('');
  const [supplement, setSupplement] = useState(pendingReading(drawId)?.supplement ?? '');
  const [busy, setBusy] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [stopRequested, setStopRequested] = useState(pendingReading(drawId)?.cancel_requested === true);
  const [status, setStatus] = useState('');
  const [cancelled, setCancelled] = useState(false);
  const runId = useRef(pendingReading(drawId)?.run_id ?? '');
  const controller = useRef<AbortController>();
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    onBusy(busy || cancelling);
  }, [busy, cancelling, onBusy]);
  const completed = versions.filter((v) => v.status === 'success' && v.answer);
  const current = completed.find((v) => v.id === selected) ?? completed.at(-1);
  async function generate() {
    setBusy(true);
    setCancelled(false);
    controller.current = new AbortController();
    setStatus('正在确认原解读请求…');
    try {
      const next = await requestReading(drawId, supplement.trim(), controller.current.signal, (message, id) => {
        setStatus(message);
        if (id) runId.current = id;
      });
      onChange(next);
      setSelected(next.at(-1)?.id ?? '');
      setStatus('解读已保存，固定牌阵没有变化。');
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      if (error instanceof ReadingStopped) setCancelled(true);
      setStatus(error instanceof Error ? error.message : '解释未确认，牌阵保持不变。');
      try {
        onChange(await loadReadings(drawId));
      } catch {
        /* Preserve previously confirmed versions. */
      }
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    const ident = runId.current;
    setCancelling(true);
    setStopRequested(true);
    markReadingStop(drawId, true);
    try {
      await write<unknown>(
        `tarot:run:${ident}:cancel`,
        'POST',
        `/api/runs/${encodeURIComponent(ident)}/cancel`,
        {},
        {
          receipt: (value) => object(value).ok === true && text(object(value).run_id) === ident,
        },
      );
      const run = object(await api<unknown>(`/api/runs/${encodeURIComponent(ident)}`));
      if (run.status !== 'cancelled' && run.status !== 'succeeded') throw new Error('停止尚未确认');
      setStopRequested(false);
      markReadingStop(drawId, false);
      controller.current?.abort();
      setBusy(false);
      if (run.status === 'succeeded') {
        onChange(await loadReadings(drawId));
        clearReading(drawId);
        setStatus('解读已完成，请查看已保存版本；牌阵保持不变。');
      } else {
        setCancelled(true);
        setStatus('这次解读已停止，牌阵保持不变。');
      }
    } catch {
      setStatus('停止未确认，请重试停止或刷新记录；牌阵保持不变。');
    } finally {
      setCancelling(false);
    }
  }
  return (
    <section className="stack" aria-label="固定牌阵解读">
      <h2>把牌面放回现实</h2>
      <p className="meta">可以补充真实背景再解读，每个已保存版本都可查看。</p>
      {completed.length > 1 && (
        <Select
          label="查看解读版本"
          value={current?.id ?? ''}
          options={completed.map((v) => ({ value: v.id, label: `第${v.version}版` }))}
          onChange={setSelected}
        />
      )}
      {current && (
        <article aria-label={`第${current.version}版解读`}>
          <Markdown text={current.answer} />
          {current.appendix && (
            <details className="disclosure">
              <summary>专业附录</summary>
              <Markdown text={current.appendix} />
            </details>
          )}
        </article>
      )}
      {!current && <p className="meta">先读静态牌意也可以。解释失败不会更换已经固定的牌。</p>}
      <label className="field">
        补充现实背景
        <Textarea
          value={supplement}
          maxLength={4000}
          disabled={busy || cancelling}
          onChange={(e) => setSupplement(e.target.value)}
        />
      </label>
      <div className="row wrap">
        <Button
          loading={busy}
          variant="primary"
          disabled={cancelled || cancelling || stopRequested}
          onClick={() => void generate()}>
          {pendingReading(drawId) ? '重试原解读 · 不换牌' : completed.length ? '重新解读 · 不换牌' : '生成 AI 解读'}
        </Button>
        {(busy || stopRequested || (runId.current && pendingPayload(`tarot:run:${runId.current}:cancel`))) && (
          <Button loading={cancelling} disabled={!runId.current} onClick={() => void cancel()}>
            {stopRequested || pendingPayload(`tarot:run:${runId.current}:cancel`) ? '重试停止解读' : '停止解读'}
          </Button>
        )}
        {cancelled && (
          <Button
            onClick={() => {
              clearReading(drawId);
              setCancelled(false);
              setStatus('可明确开始另一版解读，牌阵保持不变。');
            }}>
            明确开始另一版解读
          </Button>
        )}
        <Button
          disabled={busy}
          onClick={() => {
            void loadReadings(drawId)
              .then(onChange)
              .catch(() => setStatus('解读记录暂时无法读取。'));
          }}>
          刷新解读记录
        </Button>
      </div>
      <p role="status" aria-live="polite">
        {status}
      </p>
    </section>
  );
}
