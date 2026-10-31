import { lazy, Suspense, useEffect, useSyncExternalStore } from 'react';
import { Layout } from './Layout';
import { RouteErrorBoundary } from './components/RouteErrorBoundary';
import { Skeleton } from './components/ui/Feedback';
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
  spaces: lazy(() => import('./spaces/LiveSpaces').then((module) => ({ default: () => <module.default preview /> }))),
  'organize-draft': lazy(() =>
    import('./organize/DraftOrganizePage').then((module) => ({ default: () => <module.default preview /> })),
  ),
};
const livePages = {
  today: LiveToday,
  chat: lazy(() => import('./live/Chat').then((module) => ({ default: () => <module.default transport="v4" /> }))),
  chart: lazy(() => import('./live/Chart')),
  tarot: lazy(() => import('./live/Tarot')),
  cases: lazy(() => import('./live/Cases')),
  me: lazy(() => import('./live/Me')),
  settings: lazy(() => import('./live/Settings')),
  spaces: lazy(() => import('./spaces/LiveSpaces')),
  'organize-draft': lazy(() => import('./organize/DraftOrganizePage')),
};
const SpacesChat = lazy(() => import('./spaces/ChatPreview'));
const SpacesMe = lazy(() => import('./spaces/MemoryPreview'));
const OrganizePage = lazy(() => import('./spaces/OrganizePage'));
const OrganizeReviewPage = lazy(() => import('./organize/OrganizeReviewPage'));
const DraftOrganizePage = lazy(() =>
  import('./organize/DraftOrganizePage').then((module) => ({ default: () => <module.default preview /> })),
);
const PreviewNotice = lazy(() => import('./spaces/PreviewNotice'));
const ComponentNotice = lazy(() => import('./demos/ComponentNotice'));
const ChartDemo = lazy(() => import('./charts/ChartDemo'));
const NightApp = lazy(() => import('./night/NightApp'));
const ToolsDemo = lazy(() => import('./tools/ToolsDemo'));
const H5Demo = lazy(() => import('./embed/H5Demo'));
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
  const toolsPreview = new URLSearchParams(location.search).get('tools') === 'demo';
  const routeName = route.split(/[/?]/)[0];
  const pageName =
    routeName === 'reports'
      ? 'settings'
      : spacesPreview && ['organize', 'organize-review', 'organize-draft'].includes(routeName)
        ? 'me'
        : routeName;
  const page = pageName in pages ? (pageName as keyof typeof pages) : 'today';
  const preview =
    spacesPreview ||
    componentsPreview ||
    toolsPreview ||
    new URLSearchParams(location.search).get('preview') === '1' ||
    page === '__design';
  const Component =
    toolsPreview && page === 'chart'
      ? ToolsDemo
      : spacesPreview && routeName === 'organize-draft'
        ? DraftOrganizePage
        : spacesPreview && routeName === 'organize-review'
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
  if (new URLSearchParams(location.search).get('embed') === 'demo')
    return (
      <RouteErrorBoundary resetKey="h5-demo" homeHref="?preview=1#/today">
        <Suspense fallback={<Skeleton label="正在展开内嵌预览" />}>
          <H5Demo />
        </Suspense>
      </RouteErrorBoundary>
    );
  if (new URLSearchParams(location.search).get('night') === 'demo')
    return (
      <RouteErrorBoundary
        resetKey={`night-entry:${hash}`}
        homeHref="?preview=1#/today"
        reloadNotice="交互演示资源尚未展开。回到今日将打开独立预览；重新载入会重置本地演示。"
        wrapFallback={(recovery) => <Layout page={page}>{recovery}</Layout>}>
        <Suspense fallback={<Skeleton label="正在展开交互预览" />}>
          <NightApp page={routeName === 'recovery' ? 'recovery' : page} />
        </Suspense>
      </RouteErrorBoundary>
    );
  const content = (
    <Layout page={page} preview={preview && !componentsPreview && !toolsPreview} spacesPreview={spacesPreview}>
      <RouteErrorBoundary
        atHome={page === 'today'}
        resetKey={JSON.stringify([preview, spacesPreview, componentsPreview, toolsPreview, hash])}>
        <Suspense
          key={spacesPreview && page === 'chat' ? 'spaces-chat' : page === 'spaces' ? 'spaces' : route}
          fallback={
            <div className="page">
              <Skeleton label="正在展开页面" />
            </div>
          }>
          {spacesPreview && <PreviewNotice />}
          {componentsPreview && <ComponentNotice page={page} />}
          <Component key={spacesPreview && page === 'chat' ? 'spaces-chat' : page === 'spaces' ? 'spaces' : route} />
        </Suspense>
      </RouteErrorBoundary>
    </Layout>
  );
  return preview ? content : <AuthGate>{content}</AuthGate>;
}
