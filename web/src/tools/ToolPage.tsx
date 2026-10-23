import { useEffect, useMemo, useSyncExternalStore } from 'react';
import { Tag } from '../components/ui/Controls';
import type { ToolPort } from './types';
import WindowSearchPage from './WindowSearchPage';
import SynastryPage from './SynastryPage';
import './tools.css';
const subscribe = (changed: () => void) => {
  window.addEventListener('hashchange', changed);
  return () => window.removeEventListener('hashchange', changed);
};
const toolName = () =>
  new URLSearchParams(location.hash.split('?')[1] ?? '').get('tool') === 'synastry' ? 'synastry' : 'window_search';
export default function ToolPage({ port }: { port: ToolPort }) {
  const tool = useSyncExternalStore(subscribe, toolName);
  // Sibling viewers, including viewers of one document, never share activation.
  const context = useMemo(() => ({ tool, scope: port.createScope() }), [port, tool]);
  useEffect(() => {
    document.getElementById(tool === 'synastry' ? 'synastry-title' : 'window-title')?.focus({ preventScroll: true });
  }, [tool]);
  return (
    <div className="page tool-page" data-page="chart" data-runtime="tool-demo" data-tool={context.tool}>
      <aside className="tool-notice stack small">
        <Tag>固定合成样例</Tag>
        <p>只读浏览 · API 尚未接入。不会重新计算、写入资料、调用模型或发送消息。</p>
      </aside>
      <nav className="row wrap" aria-label="命理工具">
        <a
          className="button ghost"
          href="?tools=demo#/chart?tool=window_search"
          aria-current={tool === 'window_search' ? 'page' : undefined}>
          择日
        </a>
        <a
          className="button ghost"
          href="?tools=demo#/chart?tool=synastry"
          aria-current={tool === 'synastry' ? 'page' : undefined}>
          合盘
        </a>
      </nav>
      {tool === 'synastry' ? (
        <SynastryPage key="synastry" port={context.scope} />
      ) : (
        <WindowSearchPage key="window-search" port={context.scope} />
      )}
    </div>
  );
}
