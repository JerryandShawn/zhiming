import { lazy, Suspense, useEffect, useSyncExternalStore } from 'react';
import { Layout } from './Layout';
import { Skeleton } from './components/ui/Overlays';

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
  const pageName = route.split(/[/?]/)[0] === 'reports' ? 'settings' : route.split(/[/?]/)[0];
  const page = pageName in pages ? (pageName as keyof typeof pages) : 'today';
  const Component = pages[page];
  useEffect(() => {
    if (aliases[name]) location.replace(`#/${route}`);
    window.scrollTo(0, 0);
  }, [name, route]);
  return (
    <Layout page={page}>
      <Suspense
        fallback={
          <div className="page">
            <Skeleton label="正在展开页面" />
          </div>
        }>
        <Component key={route} />
      </Suspense>
    </Layout>
  );
}
