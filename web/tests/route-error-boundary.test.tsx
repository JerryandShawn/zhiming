import { lazy, Suspense, type ReactNode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RouteErrorBoundary } from '../src/components/RouteErrorBoundary';
import App from '../src/App';
import NightApp from '../src/night/NightApp';
import type { NormalConversation } from '../src/night/useNormalConversation';

const failures = vi.hoisted(() => ({ chart: true, nightChart: true, boot: false, guide: true }));
vi.mock('../src/Layout', () => ({
  Layout: ({
    children,
    privacy,
  }: {
    children: ReactNode;
    privacy?: { active: boolean; onChange: (active: boolean) => void };
  }) => (
    <div data-testid="navigation-shell">
      <nav aria-label="主导航">
        <a href="#/today">今日</a>
        <a href="#/chart">命盘</a>
      </nav>
      {privacy && <button onClick={() => privacy.onChange(!privacy.active)}>切换隐私模式</button>}
      <input aria-label="壳层草稿" defaultValue="保留壳层草稿" />
      <main id="main">{children}</main>
    </div>
  ),
}));
vi.mock('../src/api/AuthGate', () => ({ AuthGate: ({ children }: { children: ReactNode }) => children }));
vi.mock('../src/live/Today', () => ({ default: () => <h1>真实今日读取入口</h1> }));
vi.mock('../src/pages/Today', () => ({ default: () => <h1>独立今日预览</h1> }));
vi.mock('../src/pages/Chart', () => ({
  default: () => {
    if (failures.chart) throw new Error('PRIVATE_CHART_PAYLOAD');
    return <h1>命盘已展开</h1>;
  },
}));
vi.mock('../src/tools/ToolsDemo', () => ({ default: () => <h1>择日合盘入口</h1> }));
vi.mock('../src/night/charts/SampleChartPage', () => ({
  default: () => {
    if (failures.nightChart) throw new Error('PRIVATE_NIGHT_CHART_PAYLOAD');
    return <h1>夜间命盘已展开</h1>;
  },
}));
vi.mock('../src/night/today/TodayPage', () => ({ default: () => <h1>夜间今日已展开</h1> }));
vi.mock('../src/night/onboarding/OnboardingChat', () => ({
  default: () => {
    if (failures.guide) throw new Error('PRIVATE_GUIDE_PAYLOAD');
    return <h1>相识引导已展开</h1>;
  },
}));
vi.mock('../src/night/ChatPreview', () => ({
  default: ({ chat, guideControls }: { chat: NormalConversation; guideControls: ReactNode }) => (
    <div>
      <textarea aria-label="普通会话草稿" value={chat.draft} onChange={(event) => chat.setDraft(event.target.value)} />
      {guideControls}
    </div>
  ),
}));
vi.mock('../src/night/events', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/night/events')>()),
  playDemo: async () => {},
}));
vi.mock('../src/night/port', async (importOriginal) => {
  const original = await importOriginal<typeof import('../src/night/port')>();
  return {
    ...original,
    createNightPort: (...args: Parameters<typeof original.createNightPort>) => {
      if (failures.boot) throw new Error('PRIVATE_BOOT_PAYLOAD');
      return original.createNightPort(...args);
    },
  };
});

beforeEach(() => {
  history.replaceState({}, '', '/#/chart');
  failures.chart = failures.nightChart = failures.guide = true;
  failures.boot = false;
  // React/jsdom report expected render failures to the developer console. The
  // product fallback must never copy these error messages into the document.
  vi.spyOn(console, 'error').mockImplementation(() => {});
});
function Broken(): never {
  throw new Error('PRIVATE_DRAFT_URL_AND_ERROR_BODY');
}
function route(url: string) {
  act(() => {
    history.pushState({}, '', url);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
}

const recovery = () => screen.findByRole('alert', { name: '这页暂时没有展开' });

describe('route failure recovery', () => {
  it('sanitizes error content, focuses the fallback and keeps the navigation owner mounted', async () => {
    render(
      <div>
        <nav aria-label="保留导航">
          <a href="#/today">今日</a>
        </nav>
        <input aria-label="边界外草稿" defaultValue="普通合成草稿" />
        <RouteErrorBoundary resetKey="chart">
          <Broken />
        </RouteErrorBoundary>
      </div>,
    );
    const alert = await recovery();
    expect(alert).not.toHaveTextContent(/PRIVATE_|Error|stack|\.js/);
    expect(screen.getByRole('heading', { name: '这页暂时没有展开', level: 1 })).toHaveFocus();
    expect(screen.getByRole('navigation', { name: '保留导航' })).toBeVisible();
    expect(screen.getByRole('textbox', { name: '边界外草稿' })).toHaveValue('普通合成草稿');
  });

  it('clears old failures on route or mode changes without remounting the owner', async () => {
    const shell = (key: string, child: ReactNode) => (
      <div>
        <input aria-label="持续草稿" defaultValue="原稿" />
        <RouteErrorBoundary resetKey={key}>{child}</RouteErrorBoundary>
      </div>
    );
    const view = render(shell('chart:normal', <Broken />));
    await recovery();
    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: '后来写的草稿' } });
    view.rerender(shell('today:normal', <h1>今日已展开</h1>));
    expect(screen.getByRole('heading', { name: '今日已展开' })).toBeVisible();
    view.rerender(shell('chat:normal', <Broken />));
    await recovery();
    view.rerender(shell('chat:private', <h1>无痕视图已展开</h1>));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox')).toBe(input);
    expect(input).toHaveValue('后来写的草稿');
  });

  it('offers document reload instead of pretending a cached lazy rejection can retry in place', async () => {
    const load = vi.fn(async (): Promise<{ default: () => ReactNode }> => {
      throw new Error('PRIVATE_IMPORT_URL');
    });
    const Rejected = lazy(load),
      reload = vi.fn();
    const view = render(
      <RouteErrorBoundary resetKey="chart" onReload={reload}>
        <Suspense fallback={<p>等待分包</p>}>
          <Rejected />
        </Suspense>
      </RouteErrorBoundary>,
    );
    await recovery();
    expect(load).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '重新载入页面' }));
    expect(reload).toHaveBeenCalledTimes(1);
    view.rerender(
      <RouteErrorBoundary resetKey="chart" onReload={reload}>
        <Suspense fallback={<p>等待分包</p>}>
          <Rejected />
        </Suspense>
      </RouteErrorBoundary>,
    );
    expect(load).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: /重试|再试/ })).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent('PRIVATE_IMPORT_URL');
  });

  it.each(['', '#/', '#today', '#/today', '#/today?x=1', '#/today/extra', '#/unknown'])(
    'reloads an already resolved home view for URL %s',
    async (hash) => {
      history.replaceState({}, '', `/${hash}`);
      const reload = vi.fn();
      render(
        <RouteErrorBoundary resetKey="today" atHome onReload={reload}>
          <Broken />
        </RouteErrorBoundary>,
      );
      await recovery();
      fireEvent.click(screen.getByRole('link', { name: '回到今日' }));
      expect(reload).toHaveBeenCalledTimes(1);
    },
  );

  it('does not reload a non-home view merely because a link targets home', async () => {
    history.replaceState({}, '', '/#/chart');
    const reload = vi.fn();
    render(
      <RouteErrorBoundary resetKey="chart" atHome={false} onReload={reload}>
        <Broken />
      </RouteErrorBoundary>,
    );
    await recovery();
    fireEvent.click(screen.getByRole('link', { name: '回到今日' }));
    expect(reload).not.toHaveBeenCalled();
  });
  it('does not write, clear or duplicate drafts and confirmation tickets', async () => {
    sessionStorage.setItem('synthetic-draft', '普通合成草稿');
    const clear = vi.spyOn(Storage.prototype, 'clear'),
      remove = vi.spyOn(Storage.prototype, 'removeItem'),
      write = vi.spyOn(Storage.prototype, 'setItem');
    render(
      <RouteErrorBoundary resetKey="chart">
        <Broken />
      </RouteErrorBoundary>,
    );
    await recovery();
    expect(sessionStorage.getItem('synthetic-draft')).toBe('普通合成草稿');
    expect(clear).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
    expect(write).not.toHaveBeenCalled();
  });
});

describe('application route boundary placement', () => {
  it('keeps the regular navigation shell after a lazy page failure and recovers on today navigation', async () => {
    history.replaceState({}, '', '/?preview=1#/chart');
    render(<App />);
    await recovery();
    const shell = screen.getByTestId('navigation-shell'),
      draft = screen.getByRole('textbox', { name: '壳层草稿' });
    fireEvent.change(draft, { target: { value: '切页前的草稿' } });
    expect(screen.getByRole('navigation', { name: '主导航' })).toBeVisible();
    route('/?preview=1#/today');
    expect(await screen.findByRole('heading', { name: '独立今日预览' })).toBeVisible();
    expect(screen.getByTestId('navigation-shell')).toBe(shell);
    expect(screen.getByRole('textbox', { name: '壳层草稿' })).toBe(draft);
    expect(draft).toHaveValue('切页前的草稿');
  });

  it('retains the explicit tool demo chart entry', async () => {
    history.replaceState({}, '', '/?tools=demo#/chart?tool=synastry');
    render(<App />);
    expect(await screen.findByRole('heading', { name: '择日合盘入口' })).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('keeps the real ordinary draft controller across a failed night route and return', async () => {
    history.replaceState({}, '', '/?night=demo#/chat');
    const view = render(<NightApp page="chat" />);
    const input = await screen.findByRole('textbox', { name: '普通会话草稿' });
    fireEvent.change(input, { target: { value: '夜间未发送的普通草稿' } });
    view.rerender(<NightApp page="chart" />);
    await recovery();
    expect(document.body).not.toHaveTextContent('PRIVATE_NIGHT_CHART_PAYLOAD');
    view.rerender(<NightApp page="today" />);
    expect(await screen.findByRole('heading', { name: '夜间今日已展开' })).toBeVisible();
    view.rerender(<NightApp page="chat" />);
    expect(await screen.findByRole('textbox', { name: '普通会话草稿' })).toHaveValue('夜间未发送的普通草稿');
  });

  it('clears a failed guide view when chat mode changes while keeping ordinary draft ownership', async () => {
    history.replaceState({}, '', '/?night=demo#/chat');
    render(<NightApp page="chat" />);
    fireEvent.change(await screen.findByRole('textbox', { name: '普通会话草稿' }), {
      target: { value: '引导前的普通草稿' },
    });
    fireEvent.click(screen.getByRole('button', { name: '初次相识演示' }));
    await recovery();
    fireEvent.click(screen.getByRole('button', { name: '切换隐私模式' }));
    expect(await screen.findByRole('heading', { name: '无痕对话' })).toBeVisible();
    expect(screen.queryByRole('alert', { name: '这页暂时没有展开' })).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent('PRIVATE_GUIDE_PAYLOAD');
  });

  it('provides a navigation shell and independent home escape when the night entry itself fails', async () => {
    failures.boot = true;
    history.replaceState({}, '', '/?night=demo#/chat');
    render(<App />);
    await recovery();
    expect(screen.getByRole('navigation', { name: '主导航' })).toBeVisible();
    expect(screen.getByRole('link', { name: '回到今日' })).toHaveAttribute('href', '?preview=1#/today');
    expect(document.body).not.toHaveTextContent('PRIVATE_BOOT_PAYLOAD');
    await waitFor(() => expect(screen.getByRole('button', { name: '重新载入页面' })).toBeEnabled());
  });
});
