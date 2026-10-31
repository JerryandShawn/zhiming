import { useEffect, useRef, useState } from 'react';
import { Button, Seal } from '../components/ui/Controls';
import { createDemoSignIn, type DemoSignInState } from './demoSignIn';
import { fakeSignInPort, type DemoScenario } from './fakeSignInPort';
import { detectContainer } from './feishu';
import { useKeyboardViewport } from '../useKeyboardViewport';
import { useViewportPortalStyles } from '../useViewportPortalStyles';
import './h5-demo.css';

const labels: Record<DemoSignInState['phase'], string> = {
  idle: '还没有开始登录',
  authorizing: '等待授权确认…',
  exchanging: '正在确认会话…',
  ready: '模拟会话已确认',
  denied: '你没有同意授权，可以稍后再来',
  failed: '暂时没有连上，请重新开始',
  expired: '模拟会话已失效，请重新登录',
  'signed-out': '已在本页退出模拟会话',
};

export default function H5Demo() {
  const [scenario, setScenario] = useState<DemoScenario>('success');
  const [state, setState] = useState<DemoSignInState>({ phase: 'idle' });
  const [draft, setDraft] = useState('');
  const model = useRef<ReturnType<typeof createDemoSignIn>>();
  const offset = useRef(0);
  const input = useRef<HTMLTextAreaElement>(null);
  const start = useRef<HTMLButtonElement>(null);
  const previousPhase = useRef<DemoSignInState['phase']>('idle');
  const viewport = useKeyboardViewport();
  useViewportPortalStyles(viewport);
  const host = detectContainer(navigator.userAgent).host;
  const busy = state.phase === 'authorizing' || state.phase === 'exchanging';
  useEffect(() => {
    offset.current = 0;
    const clock = () => Date.now() + offset.current;
    const session = createDemoSignIn(fakeSignInPort(scenario, clock), clock);
    model.current = session;
    setState(session.getSnapshot());
    const unsubscribe = session.subscribe(() => setState(session.getSnapshot()));
    const check = () => session.checkExpiry();
    const timer = setInterval(check, 1000);
    document.addEventListener('visibilitychange', check);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', check);
      unsubscribe();
      session.dispose();
      if (model.current === session) model.current = undefined;
    };
  }, [scenario]);
  useEffect(() => {
    if (state.phase === 'ready') input.current?.focus();
    if (state.phase === 'idle' && ['authorizing', 'exchanging'].includes(previousPhase.current)) start.current?.focus();
    if (['denied', 'failed', 'expired', 'signed-out'].includes(state.phase)) start.current?.focus();
    previousPhase.current = state.phase;
  }, [state.phase]);
  return (
    <main className="h5-demo" data-demo="h5" data-host={host} data-keyboard={viewport.keyboard ? 'open' : undefined}>
      <p className="meta">飞书内嵌预览 · 合成会话，未连接飞书</p>
      <div className="row">
        <Seal />
        <h1>和明镜继续聊</h1>
      </div>
      <p>从授权确认到返回对话，先把每一步走稳。</p>
      <section className="h5-demo-card" aria-labelledby="h5-sign-in-title">
        <h2 id="h5-sign-in-title">登录与会话</h2>
        <label className="stack">
          预览情形
          <select
            className="input"
            value={scenario}
            disabled={busy}
            onChange={(event) => setScenario(event.target.value as DemoScenario)}>
            <option value="success">正常登录</option>
            <option value="denied">未同意授权</option>
            <option value="unavailable">暂时无法连接</option>
            <option value="timeout">等待超时</option>
            <option value="expired">收到过期会话</option>
          </select>
        </label>
        <p role="status" aria-live="polite">
          {labels[state.phase]}
          {state.reason === 'timeout' ? '（等待已超时）' : ''}
        </p>
        {state.reason === 'revoke-unconfirmed' && <p>远端退出尚未确认；本页已清除会话。</p>}
        {state.phase === 'ready' && <p>你好，{state.session?.name}。这是一次仅在本页有效的模拟登录。</p>}
        <div className="row wrap">
          {state.phase !== 'ready' && (
            <Button ref={start} variant="primary" disabled={busy} onClick={() => void model.current?.signIn()}>
              {busy ? '正在登录…' : '开始模拟登录'}
            </Button>
          )}
          {busy && (
            <Button
              onClick={() => {
                model.current?.cancel();
                start.current?.focus();
              }}>
              取消登录
            </Button>
          )}
          {state.phase === 'ready' && (
            <>
              <Button onClick={() => void model.current?.signOut()}>退出模拟会话</Button>
              <Button
                variant="ghost"
                onClick={() => {
                  offset.current += 60000;
                  model.current?.checkExpiry();
                }}>
                模拟会话失效
              </Button>
            </>
          )}
        </div>
      </section>
      <section className="h5-demo-card" aria-labelledby="h5-draft-title">
        <h2 id="h5-draft-title">先留下想说的话</h2>
        <label className="stack">
          本地草稿
          <textarea className="textarea" ref={input} value={draft} onChange={(event) => setDraft(event.target.value)} />
        </label>
        <p className="meta">草稿不会发送。登录取消、失败或过期后仍在，重新载入本页会清空。</p>
      </section>
      <p className="meta">{host === 'feishu' ? '已识别容器外观，这不代表已登录。' : '当前按浏览器外观展示。'}</p>
      <a href="?preview=1#/today">查看界面预览（无需登录）</a>
    </main>
  );
}
