import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Settings2 } from 'lucide-react';
import { Segmented, Seal } from '../../components/ui/Controls';
import { usePanelHistory } from '../../usePanelHistory';
import { MeDialogBody, viewTitles } from './MeDialogBody';
import { MePanel } from './MePanel';
import { MemoryList } from './MemoryList';
import { OtherTabs } from './OtherTabs';
import { ProfileSections } from './ProfileSections';
import { ProposalList } from './ProposalList';
import type { AboutMePort } from './types';
import type { MeView } from './views';
import './me.css';

const sections = [
  { value: 'profile', label: '画像' },
  { value: 'memory', label: '记忆' },
  { value: 'pending', label: '待确认' },
  { value: 'people', label: '重要的人' },
  { value: 'timeline', label: '时间线' },
  { value: 'dictionary', label: '符号词典' },
];
function initialTab(hash: string) {
  const value = new URLSearchParams(hash.split('?')[1]).get('section') || 'profile';
  return sections.some((item) => item.value === value) ? value : 'profile';
}
const subscribeHash = (listener: () => void) => {
  window.addEventListener('hashchange', listener);
  return () => window.removeEventListener('hashchange', listener);
};
export default function AboutMePage({ port }: { port: AboutMePort }) {
  const snapshot = useSyncExternalStore(port.subscribe, port.getSnapshot);
  const hash = useSyncExternalStore(subscribeHash, () => location.hash);
  const [tab, setTab] = useState(() => initialTab(hash));
  const [view, setView] = useState<MeView>(),
    [feedback, setFeedback] = useState('');
  const returnTo = useRef<HTMLElement>();
  const panel = usePanelHistory();
  useEffect(() => {
    setTab(initialTab(hash));
  }, [hash]);
  const open = (next: MeView, origin: HTMLElement) => {
    returnTo.current = origin;
    setView(next);
    setFeedback('');
    panel.onOpenChange(true);
  };
  const close = () => panel.onOpenChange(false);
  const activeCount = snapshot.memories.filter((item) => item.status === 'active').length;
  const pendingCount = snapshot.proposals.filter((item) => item.status === 'pending').length;
  return (
    <div className="page night-me" data-page="me" data-runtime="night-me" data-revision={snapshot.revision}>
      <header className="row night-me-heading">
        <Seal size="large" />
        <div className="grow">
          <h1>明镜记得你的 {activeCount} 件事</h1>
          <p className="meta">
            {pendingCount} 件待你确认 · 上次整理 {snapshot.lastOrganizedAt.slice(0, 16).replace('T', ' ')}
          </p>
        </div>
        <a className="icon-button" href="#/settings" aria-label="设置">
          <Settings2 className="icon" aria-hidden="true" />
        </a>
      </header>
      <div className="night-me-tabs route-tabs">
        <Segmented
          label="关于我的分区"
          options={sections}
          value={tab}
          onChange={(next) => {
            setTab(next);
            setFeedback('');
          }}
        />
      </div>
      {feedback && (
        <p role="status" className="night-me-feedback">
          {feedback}
        </p>
      )}
      {tab === 'profile' ? (
        <ProfileSections items={snapshot.profileItems} port={port} open={open} />
      ) : tab === 'memory' ? (
        <MemoryList items={snapshot.memories} port={port} open={open} />
      ) : tab === 'pending' ? (
        <ProposalList items={snapshot.proposals} port={port} />
      ) : (
        <OtherTabs tab={tab} snapshot={snapshot} port={port} open={open} />
      )}
      <footer className="section meta">
        删除整段来源会连带清除由它整理出的画像与摘要；只删条目会保留原始来源。已经发到飞书的消息无法撤回。
      </footer>
      <MePanel
        open={panel.open}
        onOpenChange={panel.onOpenChange}
        title={view ? viewTitles[view.kind] : '查看条目'}
        description="请先核对你要查看或修改的内容，操作只在收到确认后生效。"
        returnTo={returnTo}>
        {view && (
          <MeDialogBody
            key={`${view.kind}-${view.item.id}`}
            view={view}
            snapshot={snapshot}
            port={port}
            close={close}
            confirmed={setFeedback}
            edit={setView}
          />
        )}
      </MePanel>
    </div>
  );
}
