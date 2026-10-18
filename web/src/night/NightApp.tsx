import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Layout } from '../Layout';
import { Skeleton } from '../components/ui/Overlays';
import { createNightPort } from './port';
import { createMemoryReceiptRegistry } from '../chat/interactions/memoryProjection';
import ChatPreview from './ChatPreview';
import { useNormalConversation } from './useNormalConversation';
import { useAboutMeReceipts } from './useAboutMeReceipts';
import { usePrivacySession, PrivateChat } from './privacy';
import { Button } from '../components/ui/Controls';
import { EyeOff } from 'lucide-react';
import './night.css';

const otherPages = {
  today: lazy(() => import('../pages/Today')),
  chart: lazy(() => import('../charts/ChartDemo')),
  tarot: lazy(() => import('../pages/Tarot')),
  cases: lazy(() => import('../pages/Cases')),
  me: lazy(() => import('../pages/Me')),
  settings: lazy(() => import('../pages/Settings')),
};
const AboutMePage = lazy(() => import('./me/AboutMePage'));

export default function NightApp({ page }: { page: string }) {
  const [port] = useState(createNightPort);
  const receiptRegistry = useRef(createMemoryReceiptRegistry()).current;
  useAboutMeReceipts(port.aboutMe, receiptRegistry);
  const privacy = usePrivacySession();
  const chat = useNormalConversation(port, page === 'chat' && !privacy.active);
  const previousMode = useRef(privacy.active);
  const focusRequested = useRef(false);
  useEffect(() => {
    if (previousMode.current !== privacy.active) focusRequested.current = true;
    previousMode.current = privacy.active;
    if (page !== 'chat' || !focusRequested.current) return;
    const frame = requestAnimationFrame(() => {
      const composer = document.querySelector<HTMLTextAreaElement>('#composer-input');
      if (composer && !composer.disabled) {
        composer.focus();
        focusRequested.current = false;
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [page, privacy.active, chat.busy]);
  function setPrivacy(active: boolean) {
    if (active) chat.pause();
    privacy.setActive(active);
    if (active && page !== 'chat') location.hash = '/chat';
  }
  const Other = otherPages[page as keyof typeof otherPages] || otherPages.today;
  return (
    <Layout
      page={page}
      privacy={{ active: privacy.active, onChange: setPrivacy, description: '本地无痕演示不会进入记忆，退出后清空。' }}>
      <aside className="night-notice" aria-label="本地演示说明" data-runtime="night-demo">
        <p>合成预览 · 操作仅本页，刷新重置。</p>
        <a href={`/#/${page}`}>真实入口</a>
      </aside>
      {privacy.endedBy && (
        <p className="night-ended meta" role="status">
          {privacy.endedBy === 'idle'
            ? '连续24小时未使用，无痕对话已结束，临时内容已清空。'
            : '已退出无痕，临时内容已清空。'}
        </p>
      )}
      {privacy.active && page !== 'chat' && (
        <div className="night-private-away row wrap" role="status">
          <EyeOff className="icon" aria-hidden="true" />
          <span>无痕对话已暂停。</span>
          <a className="button secondary" href="#/chat">
            返回无痕对话
          </a>
          <Button onClick={() => setPrivacy(false)}>退出无痕</Button>
        </div>
      )}
      <Suspense
        fallback={
          <div className="page">
            <Skeleton label="正在展开页面" />
          </div>
        }>
        {page === 'chat' ? (
          privacy.active ? (
            <PrivateChat privacy={privacy} />
          ) : (
            <ChatPreview port={port} receiptRegistry={receiptRegistry} chat={chat} onPrivacyChange={setPrivacy} />
          )
        ) : page === 'me' ? (
          <AboutMePage port={port.aboutMe} />
        ) : (
          <Other />
        )}
      </Suspense>
    </Layout>
  );
}
