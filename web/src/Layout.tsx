import type { CSSProperties, ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import {
  EyeOff,
  Layers,
  ListChecks,
  MessageCircle,
  MoreHorizontal,
  Orbit,
  Settings2,
  SunMedium,
  UserRound,
} from 'lucide-react';
import { useState } from 'react';
import { IconButton, Seal, Switch } from './components/ui/Controls';
import { Panel, Toast } from './components/ui/Overlays';
import { useKeyboardViewport } from './useKeyboardViewport';

const navigation: { key: string; label: string; icon: LucideIcon }[] = [
  { key: 'today', label: '今日', icon: SunMedium },
  { key: 'chat', label: '对话', icon: MessageCircle },
  { key: 'chart', label: '命盘', icon: Orbit },
  { key: 'tarot', label: '塔罗', icon: Layers },
  { key: 'cases', label: '事项', icon: ListChecks },
  { key: 'me', label: '关于我', icon: UserRound },
];

function Links({ current }: { current: string }) {
  return (
    <>
      {navigation.map(({ key, label, icon: Icon }) => (
        <a className="nav-link" href={`#/${key}`} key={key} aria-current={current === key ? 'page' : undefined}>
          <Icon className="icon" aria-hidden />
          {label}
        </a>
      ))}
    </>
  );
}

export function Layout({ page, children, preview = false }: { page: string; children: ReactNode; preview?: boolean }) {
  const [privateMode, setPrivate] = useState(false);
  const viewport = useKeyboardViewport();
  const label =
    page === 'chat'
      ? '明镜'
      : page === 'settings'
        ? '设置'
        : page === '__design'
          ? '组件一览'
          : (navigation.find((item) => item.key === page)?.label ?? '明镜');
  const mobileSelected = page === 'settings' ? 'me' : page === 'cases' ? 'today' : page;
  return (
    <div
      className="shell"
      data-keyboard={!preview && viewport.keyboard ? 'open' : undefined}
      style={viewport.height ? ({ '--keyboard-height': `${viewport.height}px` } as CSSProperties) : undefined}>
      <a
        className="skip"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById('main')?.focus();
        }}>
        跳到主要内容
      </a>
      <aside className="rail" aria-label="主导航">
        <a href="#/today" className="brand row">
          <Seal />
          <span>明镜</span>
        </a>
        <p className="rail-date meta">
          {preview
            ? '10月17日 周六 · 九月初八'
            : new Intl.DateTimeFormat('zh-CN', {
                timeZone: 'Asia/Shanghai',
                month: 'long',
                day: 'numeric',
                weekday: 'short',
              }).format(new Date())}
        </p>
        <nav>
          <Links current={page} />
        </nav>
        <div className="rail-bottom">
          <div className="row between small-text">
            <span className="row">
              <EyeOff className="icon" />
              无痕模式
            </span>
            <Switch label="侧栏无痕模式" checked={privateMode} onChange={setPrivate} disabled={!preview} />
          </div>
          {!preview && <p className="meta">无痕对话正在准备，暂不可用。</p>}
          <a className="nav-link" href="#/settings" aria-current={page === 'settings' ? 'page' : undefined}>
            <Settings2 className="icon" />
            设置
          </a>
        </div>
      </aside>
      <header className="topbar">
        <h1>{label}</h1>
        {page === 'today' ? (
          <a className="icon-button" href="#/settings" aria-label="设置">
            <Settings2 className="icon" />
          </a>
        ) : (
          <Panel
            sheet
            title="去哪里看看"
            description="选择想看的页面。"
            trigger={
              <IconButton label="更多页面">
                <MoreHorizontal className="icon" />
              </IconButton>
            }>
            <Links current={page} />
            <a className="nav-link" href="#/settings">
              <Settings2 className="icon" />
              设置
            </a>
          </Panel>
        )}
      </header>
      <main id="main" tabIndex={-1}>
        {children}
      </main>
      <nav className="tabbar" aria-label="底部导航">
        {navigation
          .filter((item) => item.key !== 'cases')
          .map(({ key, label, icon: Icon }) => (
            <a href={`#/${key}`} key={key} aria-current={mobileSelected === key ? 'page' : undefined}>
              <Icon className="icon" aria-hidden />
              {key === 'me' ? '我' : label}
            </a>
          ))}
      </nav>
      <Toast />
    </div>
  );
}
