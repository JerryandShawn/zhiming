import { lazy, Suspense, useEffect, useSyncExternalStore } from 'react';
import { Layout } from './Layout';
import { Skeleton } from './components/ui/Overlays';
import { AuthGate } from './api/AuthGate';
import LiveToday from './live/Today';

const pages = {
  today: lazy(() => import('./pages/Today')),
  chat: lazy(() => import('./pages/Chat')),
  chart: lazy(() => import('./pages/Chart')),
  tarot: lazy(() => import('./pages/Tarot')),
  cases: lazy(() => import('./pages/Cases')),
  me: lazy(() => import('./pages/Me')),
  settings: lazy(() => import('./pages/Settings')),
  __design: lazy(() => import('./pages/Design')),
};
const livePages = {
  today: LiveToday,
  chat: lazy(() => import('./live/Chat')),
  chart: lazy(() => import('./live/Chart')),
  tarot: lazy(() => import('./live/Tarot')),
  cases: lazy(() => import('./live/Cases')),
  me: lazy(() => import('./live/Me')),
  settings: lazy(() => import('./live/Settings')),
};
const SpacesChat = lazy(() => import('./spaces/ChatPreview'));
const SpacesMe = lazy(() => import('./spaces/MemoryPreview'));
const OrganizePage = lazy(() => import('./spaces/OrganizePage'));
const OrganizeReviewPage = lazy(() => import('./organize/OrganizeReviewPage'));
const PreviewNotice = lazy(() => import('./spaces/PreviewNotice'));
const ComponentNotice = lazy(() => import('./demos/ComponentNotice'));
const ChartDemo = lazy(() => import('./charts/ChartDemo'));
const NightApp = lazy(() => import('./night/NightApp'));
const aliases: Record<string, string> = {
  memory: 'me?section=memory',
  timeline: 'me?section=timeline',
  graph: 'me?section=people',
  dict: 'me?section=dictionary',
  reportsettings: 'settings/reports',
};
function subscribe(callback: () => void) {
  window.addEventListener('hashchange', callback);
  return () => window.removeEventListener('hashchange', callback);
}

export default function App() {
  const hash = useSyncExternalStore(subscribe, () => location.hash);
  let route = hash.replace(/^#\/?/, '') || 'today';
  const name = route.split(/[/?]/)[0];
  if (aliases[name]) route = aliases[name];
  const spacesPreview = new URLSearchParams(location.search).get('spaces') === 'demo';
  const componentsPreview = new URLSearchParams(location.search).get('components') === 'demo';
  const routeName = route.split(/[/?]/)[0];
  const pageName =
    routeName === 'reports'
      ? 'settings'
      : spacesPreview && ['organize', 'organize-review'].includes(routeName)
        ? 'me'
        : routeName;
  const page = pageName in pages ? (pageName as keyof typeof pages) : 'today';
  const preview =
    spacesPreview ||
    componentsPreview ||
    new URLSearchParams(location.search).get('preview') === '1' ||
    page === '__design';
  const Component =
    spacesPreview && routeName === 'organize-review'
      ? OrganizeReviewPage
      : spacesPreview && routeName === 'organize'
        ? OrganizePage
        : spacesPreview && page === 'chat'
          ? SpacesChat
          : spacesPreview && page === 'me'
            ? SpacesMe
            : componentsPreview && page === 'chart'
              ? ChartDemo
              : preview
                ? pages[page]
                : livePages[page as keyof typeof livePages];
  useEffect(() => {
    if (aliases[name]) location.replace(`#/${route}`);
    window.scrollTo(0, 0);
  }, [name, route]);
  if (new URLSearchParams(location.search).get('night') === 'demo')
    return (
      <Suspense fallback={<Skeleton label="正在展开交互预览" />}>
        <NightApp page={page} />
      </Suspense>
    );
  const content = (
    <Layout page={page} preview={preview && !componentsPreview} spacesPreview={spacesPreview}>
      <Suspense
        fallback={
          <div className="page">
            <Skeleton label="正在展开页面" />
          </div>
        }>
        {spacesPreview && <PreviewNotice />}
        {componentsPreview && <ComponentNotice page={page} />}
        <Component key={spacesPreview && page === 'chat' ? 'spaces-chat' : route} />
      </Suspense>
    </Layout>
  );
  return preview ? content : <AuthGate>{content}</AuthGate>;
}
