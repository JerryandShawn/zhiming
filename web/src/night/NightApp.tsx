import { lazy, Suspense, useEffect, useRef, useState, useSyncExternalStore } from 'react';
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
import { createBirthPort } from './onboarding/birth';
import { createOnboardingController } from './onboarding/controller';
import { createSettingsPort } from './settings/port';
import { createTodayPort } from './today/port';
import './night.css';

const otherPages = {
  today: lazy(() => import('./today/TodayPage')),
  chart: lazy(() => import('../charts/ChartDemo')),
  tarot: lazy(() => import('../pages/Tarot')),
  cases: lazy(() => import('../pages/Cases')),
  me: lazy(() => import('../pages/Me')),
  settings: lazy(() => import('../pages/Settings')),
};
const AboutMePage = lazy(() => import('./me/AboutMePage'));
const OnboardingChat = lazy(() => import('./onboarding/OnboardingChat'));
const SettingsPage = lazy(() => import('./settings/SettingsPage'));
const SampleChartPage = lazy(() => import('./charts/SampleChartPage'));
const TodayPage = otherPages.today;
const RecoveryPreview = lazy(() => import('./recovery/RecoveryPreview'));

export default function NightApp({ page }: { page: string }) {
  const [port] = useState(createNightPort);
  const receiptRegistry = useRef(createMemoryReceiptRegistry()).current;
  useAboutMeReceipts(port.aboutMe, receiptRegistry);
  const privacy = usePrivacySession();
  const [birth] = useState(createBirthPort);
  const [settings] = useState(createSettingsPort);
  const [today] = useState(createTodayPort);
  const [guide] = useState(() =>
    createOnboardingController({
      aboutMe: port.aboutMe,
      birth,
      onContactPreference: settings.applyContactPreference,
      readContactPreference: settings.readContactPreference,
    }),
  );
  const guideState = useSyncExternalStore(guide.subscribe, guide.getSnapshot);
  const [showGuide, setShowGuide] = useState(false);
  const chat = useNormalConversation(port, page === 'chat' && !privacy.active && !showGuide);
  useEffect(() => {
    if (page !== 'chat') guide.pause();
  }, [page, guide]);
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
    if (active) {
      chat.clearQueueForPrivacy();
      chat.pause();
      guide.pause();
    }
    privacy.setActive(active);
    if (active && page !== 'chat') location.hash = '/chat';
  }
  function startGuide(mode: 'new' | 'known') {
    chat.pause();
    guide.start(mode);
    setShowGuide(true);
  }
  const Other = otherPages[page as keyof typeof otherPages] || otherPages.today;
  return (
    <Layout
      page={page === 'recovery' ? 'chat' : page}
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
        key={page === 'chat' ? (privacy.active ? 'private-chat' : showGuide ? 'guide-chat' : 'normal-chat') : page}
        fallback={
          <div className="page">
            <Skeleton label="正在展开页面" />
          </div>
        }>
        {page === 'recovery' ? (
          <RecoveryPreview
            onBack={() => {
              location.hash = '/chat';
            }}
          />
        ) : page === 'chat' ? (
          privacy.active ? (
            <PrivateChat privacy={privacy} />
          ) : showGuide ? (
            <OnboardingChat
              controller={guide}
              birth={birth}
              onLeave={() => {
                guide.pause();
                setShowGuide(false);
              }}
            />
          ) : (
            <ChatPreview
              port={port}
              receiptRegistry={receiptRegistry}
              chat={chat}
              onPrivacyChange={setPrivacy}
              guideControls={
                <div className="row wrap" role="group" aria-label="初次相识演示入口">
                  {guideState.status === 'idle' ? (
                    <>
                      <Button onClick={() => startGuide('new')}>初次相识演示</Button>
                      <Button onClick={() => startGuide('known')}>已有资料继续演示</Button>
                    </>
                  ) : (
                    <Button onClick={() => setShowGuide(true)}>
                      {guideState.status === 'complete' ? '回看相识小结' : '继续初次相识'}
                    </Button>
                  )}
                </div>
              }
            />
          )
        ) : page === 'today' ? (
          <TodayPage
            port={today}
            settings={settings}
            onChat={() => {
              location.hash = '/chat';
            }}
          />
        ) : page === 'chart' ? (
          <SampleChartPage />
        ) : page === 'me' ? (
          <AboutMePage port={port.aboutMe} />
        ) : page === 'settings' ? (
          <SettingsPage port={settings} />
        ) : (
          <Other port={today} settings={settings} />
        )}
      </Suspense>
    </Layout>
  );
}
