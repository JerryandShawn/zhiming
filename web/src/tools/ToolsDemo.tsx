import { useEffect, useState } from 'react';
import { Button } from '../components/ui/Controls';
import { Skeleton } from '../components/ui/Feedback';
import { loadPublishedToolPort } from './loadPublishedSamples';
import ToolPage from './ToolPage';
import type { ToolPort } from './types';

type State = { status: 'loading' } | { status: 'error' } | { status: 'ready'; port: ToolPort };
export default function ToolsDemo() {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<State>({ status: 'loading' });
  useEffect(() => {
    const controller = new AbortController();
    let port: ToolPort | undefined;
    setState({ status: 'loading' });
    void loadPublishedToolPort(controller.signal).then(
      (loaded) => {
        if (controller.signal.aborted) {
          loaded.reset();
          return;
        }
        port = loaded;
        setState({ status: 'ready', port: loaded });
      },
      () => {
        if (!controller.signal.aborted) setState({ status: 'error' });
      },
    );
    return () => {
      controller.abort();
      port?.reset();
    };
  }, [attempt]);
  if (state.status === 'loading')
    return (
      <div className="page" data-runtime="tool-demo-loading">
        <Skeleton label="正在核对公开工具样例" />
      </div>
    );
  if (state.status === 'error')
    return (
      <section className="page stack" role="alert" aria-labelledby="tool-load-title">
        <h1 id="tool-load-title">这次样例没有展开</h1>
        <p>请确认本机连接后重试。当前不会读取真实资料、保存、发送或发起计算。</p>
        <Button onClick={() => setAttempt((value) => value + 1)}>重新载入公开样例</Button>
      </section>
    );
  return <ToolPage port={state.port} />;
}
