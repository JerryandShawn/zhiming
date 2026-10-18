import { lazy, Suspense, useRef, useState } from 'react';
import { Layout } from '../Layout';
import { Skeleton } from '../components/ui/Overlays';
import { createNightPort } from './port';
import { createMemoryReceiptRegistry } from '../chat/interactions/memoryProjection';
import ChatPreview from './ChatPreview';
import './night.css';

const otherPages = {
  today: lazy(() => import('../pages/Today')),
  chart: lazy(() => import('../charts/ChartDemo')),
  tarot: lazy(() => import('../pages/Tarot')),
  cases: lazy(() => import('../pages/Cases')),
  me: lazy(() => import('../pages/Me')),
  settings: lazy(() => import('../pages/Settings')),
};

export default function NightApp({ page }: { page: string }) {
  const [port] = useState(createNightPort);
  const receiptRegistry = useRef(createMemoryReceiptRegistry()).current;
  const Other = otherPages[page as keyof typeof otherPages] || otherPages.today;
  return (
    <Layout page={page}>
      <aside className="night-notice" aria-label="本地演示说明" data-runtime="night-demo">
        <p>本地交互预览 · 所有资料均为合成示例，操作只在本页演示；刷新后重置。</p>
        <a href={`/#/${page}`}>返回真实入口</a>
      </aside>
      <Suspense
        fallback={
          <div className="page">
            <Skeleton label="正在展开页面" />
          </div>
        }>
        {page === 'chat' ? <ChatPreview port={port} receiptRegistry={receiptRegistry} /> : <Other />}
      </Suspense>
    </Layout>
  );
}
