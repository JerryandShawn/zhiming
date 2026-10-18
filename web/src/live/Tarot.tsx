import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '../components/ui/Controls';
import { api, ApiError, operationNamespace, useAuth } from '../api/client';
import { createDraw, loadDraw, mutateDraw } from '../tarot/draws';
import { loadReadings } from '../tarot/readings';
import { deck as projectDeck, draw as projectDraw, list, type Deck, type Draw, type Reading } from '../tarot/public';
import { QuestionForm } from '../tarot/QuestionForm';
import { DrawPanel } from '../tarot/DrawPanel';

export default function Tarot() {
  const available = useAuth((state) => Boolean(state.token && !state.loginRequired));
  const [deck, setDeck] = useState<Deck>();
  const [history, setHistory] = useState<Draw[]>([]);
  const [current, setCurrent] = useState<Draw>();
  const [previous, setPrevious] = useState<Draw>();
  const [versions, setVersions] = useState<Reading[]>([]);
  const [status, setStatus] = useState('正在读取牌库与抽牌记录…');
  const [busy, setBusy] = useState(false);
  const [readingBusy, setReadingBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const generation = useRef(0);
  const loaded = useRef(true);
  const invalidate = useCallback(() => {
    loaded.current = false;
    generation.current++;
  }, []);
  const remember = useCallback((value: Draw) => {
    setCurrent(value);
    setHistory((old) => [value, ...old.filter((d) => d.id !== value.id)]);
  }, []);
  const open = useCallback(
    async (id: string) => {
      const version = ++generation.current;
      setStatus('正在恢复这次固定牌阵…');
      setBusy(true);
      try {
        const value = await loadDraw(id);
        if (version !== generation.current || !loaded.current) return;
        remember(value);
        setPrevious(undefined);
        setVersions([]);
        setStatus('');
        setConflict(false);
        try {
          const values = await loadReadings(id);
          if (version === generation.current && loaded.current) setVersions(values);
        } catch {
          if (version === generation.current && loaded.current) setStatus('解读版本暂时无法读取，固定牌阵仍可查看。');
        }
      } catch {
        if (version === generation.current && loaded.current)
          setStatus('恢复未完成，请刷新核对。已保存的抽牌不会因此改变。');
      } finally {
        if (version === generation.current && loaded.current) setBusy(false);
      }
    },
    [remember],
  );
  useEffect(() => {
    if (!available) {
      invalidate();
      return;
    }
    loaded.current = true;
    const version = ++generation.current;
    void Promise.allSettled([api<unknown>('/api/tarot/deck'), api<unknown>('/api/tarot/draws')]).then((results) => {
      if (!loaded.current || version !== generation.current) return;
      if (results[0].status === 'fulfilled') {
        setDeck(projectDeck(results[0].value));
        setStatus('');
      } else setStatus('牌库暂时无法读取，请稍后刷新。');
      if (results[1].status === 'fulfilled') setHistory(list(results[1].value).map(projectDraw));
      else setStatus('历史记录暂时无法读取，已保存的抽牌不会改变。');
      const id = new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('draw');
      if (id) void open(id);
    });
    return invalidate;
  }, [open, invalidate, available]);
  async function create(payload: Record<string, unknown>) {
    const namespace = operationNamespace();
    setBusy(true);
    setStatus('正在保存问题与抽牌记录…');
    try {
      const result = await createDraw(payload);
      if (!loaded.current || namespace !== operationNamespace()) return;
      remember(result.draw);
      setPrevious(undefined);
      setVersions([]);
      setStatus(result.reused ? '已恢复这件事原来的固定牌阵。' : '抽牌已保存，牌面已固定。');
      window.history.replaceState(null, '', `#/tarot?draw=${encodeURIComponent(result.draw.id)}`);
      try {
        setVersions(await loadReadings(result.draw.id));
      } catch {
        setStatus('抽牌已保存，解读版本暂时无法读取；请刷新解读记录。');
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '保存未确认，请保留原内容重试。');
    } finally {
      setBusy(false);
    }
  }
  async function mutate(action: 'select' | 'reveal' | 'cancel' | 'manual', payload: Record<string, unknown>) {
    if (!current || busy || readingBusy) return;
    setBusy(true);
    setStatus('正在确认操作回执…');
    const namespace = operationNamespace();
    try {
      const value = await mutateDraw(current, action, payload);
      if (!loaded.current || namespace !== operationNamespace()) return;
      remember(value);
      if (action === 'manual') {
        setVersions([]);
        window.history.replaceState(null, '', `#/tarot?draw=${encodeURIComponent(value.id)}`);
      }
      setStatus(
        action === 'select'
          ? '选牌已保存。'
          : action === 'cancel'
            ? '本次选牌已结束。'
            : action === 'manual'
              ? '实体牌录入已更正，旧版本保留。'
              : '揭牌已保存，原牌阵保持不变。',
      );
      if (action === 'select')
        window.requestAnimationFrame(() =>
          document.querySelector<HTMLButtonElement>('.tarot-picker button:not(:disabled)')?.focus(),
        );
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) setConflict(true);
      setStatus(error instanceof Error ? error.message : '操作未确认，请用原内容重试。');
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page" data-page="tarot">
      <header className="page-heading row between">
        <h1>塔罗</h1>
        <Button
          variant="ghost"
          disabled={busy || readingBusy}
          onClick={() => {
            setCurrent(undefined);
            setPrevious(undefined);
            setVersions([]);
            setStatus('');
            window.history.replaceState(null, '', '#/tarot');
          }}>
          新问题
        </Button>
      </header>
      <p role="status" aria-live="polite">
        {status}
      </p>
      {conflict && current && (
        <Button disabled={busy || readingBusy} onClick={() => void open(current.id)}>
          刷新牌阵后核对
        </Button>
      )}
      {!deck && <Button onClick={() => window.location.reload()}>重新读取牌库</Button>}
      {deck && (
        <div className="page-grid">
          <div>
            {current ? (
              <DrawPanel
                key={current.id}
                draw={current}
                deck={deck}
                busy={busy || readingBusy || conflict}
                versions={versions}
                onChangeVersions={setVersions}
                onReadingBusy={setReadingBusy}
                mutate={(action, payload) => void mutate(action, payload)}
                newRound={() => {
                  setPrevious(current);
                  setCurrent(undefined);
                  setVersions([]);
                  setStatus('');
                  window.history.replaceState(null, '', '#/tarot');
                }}
              />
            ) : (
              <QuestionForm
                key={previous?.id ?? 'new'}
                deck={deck}
                previous={previous}
                busy={busy}
                onSubmit={(value) => void create(value)}
              />
            )}
          </div>
          <aside className="tarot-history">
            <h2>以前问过的</h2>
            {!history.length && <p className="meta">还没有记录。从眼前的一个问题开始。</p>}
            {history.map((value) => (
              <Button
                key={value.id}
                variant="ghost"
                disabled={busy || readingBusy}
                onClick={() => {
                  window.history.replaceState(null, '', `#/tarot?draw=${encodeURIComponent(value.id)}`);
                  void open(value.id);
                }}>
                <span>
                  {value.question}
                  <span className="meta">
                    {' '}
                    · {value.created_at.slice(0, 10)} · {value.status === 'cancelled' ? '已结束' : '查看固定牌阵'}
                  </span>
                </span>
              </Button>
            ))}
          </aside>
        </div>
      )}
    </div>
  );
}
