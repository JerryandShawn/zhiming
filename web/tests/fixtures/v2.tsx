import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Answer } from '../../src/chat/Answers';
import { followV2 } from '../../src/chat/v2';
import { reduceChat } from '../../src/chat/reducer';
import { initialStream } from '../../src/chat/types';
import '../../src/styles/base.css';

function Harness() {
  const [state, setState] = useState(initialStream),
    [error, setError] = useState(''),
    [reply, setReply] = useState('');
  useEffect(() => {
    const abort = new AbortController();
    void followV2('synthetic', {
      basePath: '/__test__/v2/runs',
      signal: abort.signal,
      restore: setState,
      accept: (event) => setState((current) => reduceChat(current, event)),
    }).catch((reason) => {
      if (!abort.signal.aborted) setError(reason instanceof Error ? reason.message : '测试失败');
    });
    return () => abort.abort();
  }, []);
  return (
    <main className="page">
      <h1>SSE v2 模拟契约</h1>
      <p>仅测试夹具，不执行真实模型或用户写操作。</p>
      <Answer state={state} onReply={setReply} />
      {reply && <p role="status">测试选择：{reply}</p>}
      {state.complete && <p role="status">模拟流已完成</p>}
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
createRoot(document.getElementById('root')!).render(<Harness />);
