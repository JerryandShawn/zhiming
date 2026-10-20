import { useEffect, useState, type ComponentProps } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Button } from '../src/components/ui/Controls';
import { DeferredPanel } from '../src/components/ui/DeferredPanel';
import DialogContent from '../src/components/ui/DialogContent';
import { AuthGate } from '../src/api/AuthGate';
import { useAuth } from '../src/api/client';
import { useResource } from '../src/api/useResource';

type Loader = NonNullable<ComponentProps<typeof DeferredPanel>['loadContent']>;
type ContentModule = Awaited<ReturnType<Loader>>;
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
const module = { default: DialogContent };
const originalAuth = useAuth.getState();

beforeEach(() => {
  history.replaceState({ page: 'previous' }, '', '/#/today');
  history.pushState({ page: 'chart' }, '', '/#/chart');
  useAuth.setState({ token: 'synthetic-owner', loginRequired: false });
});
afterEach(() => {
  useAuth.setState(originalAuth);
  vi.unstubAllGlobals();
});

function Example({ load }: { load: Loader }) {
  const [selected, setSelected] = useState('今天');
  return (
    <>
      <textarea aria-label="页面草稿" />
      <DeferredPanel
        title="依据说明"
        description="只读合成数据"
        sheet
        loadContent={load}
        renderTrigger={(props) => <Button {...props}>查看依据</Button>}>
        <input aria-label="面板输入" />
        <p>已选：{selected}</p>
        <Button onClick={() => setSelected('明天')}>选择明天</Button>
      </DeferredPanel>
    </>
  );
}
const settled = () => waitFor(() => expect(history.state).toEqual({ page: 'chart' }));

function enableExitAnimations() {
  const compute = window.getComputedStyle.bind(window);
  vi.stubGlobal('CSS', { escape: (value: string) => value });
  // Browsers return live computed styles; jsdom otherwise snapshots the open
  // selector. Supply that platform behavior while exercising real Radix Presence.
  vi.spyOn(window, 'getComputedStyle').mockImplementation((element, pseudo) => {
    const styles = compute(element, pseudo);
    return new Proxy(styles, {
      get(target, key) {
        if (key === 'animationName' && element.classList.contains('dialog'))
          return element.getAttribute('data-state') === 'closed' ? 'q8-exit' : 'q8-enter';
        const value = Reflect.get(target, key, target);
        return typeof value === 'function' ? value.bind(target) : value;
      },
    });
  });
}
function animation(node: HTMLElement, kind: 'animationstart' | 'animationend', name: string) {
  const event = new Event(kind, { bubbles: true });
  Object.defineProperty(event, 'animationName', { value: name });
  fireEvent(node, event);
}

describe('a lightweight panel owns navigation before its deferred dialog arrives', () => {
  it('does not load or mount closed dialog content', () => {
    const load = vi.fn<Loader>().mockResolvedValue(module);
    render(<Example load={load} />);
    expect(load).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '查看依据' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('textbox', { name: '面板输入' })).not.toBeInTheDocument();
  });

  it.each(['Escape', '取消展开'])(
    'cancels a pending import with %s and never reopens on late completion',
    async (command) => {
      const pending = deferred<ContentModule>();
      const load = vi.fn<Loader>().mockReturnValue(pending.promise);
      render(<Example load={load} />);
      const trigger = screen.getByRole('button', { name: '查看依据' });
      await userEvent.click(trigger);
      expect(screen.getByRole('status', { name: '正在展开依据说明' })).toBeVisible();
      expect(trigger).toHaveAttribute('aria-expanded', 'true');
      if (command === 'Escape') await userEvent.keyboard('{Escape}');
      else await userEvent.click(screen.getByRole('button', { name: '取消展开' }));
      await settled();
      await act(async () => {
        pending.resolve(module);
        await pending.promise;
      });
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: '查看依据' })).toBe(trigger);
      expect(trigger).toHaveFocus();
      expect(load).toHaveBeenCalledTimes(1);
    },
  );

  it('consumes Back during an import and keeps the old Forward marker inert', async () => {
    const pending = deferred<ContentModule>();
    const load = vi.fn<Loader>().mockReturnValue(pending.promise);
    render(<Example load={load} />);
    await userEvent.type(screen.getByRole('textbox', { name: '页面草稿' }), '合成草稿留在页面');
    await userEvent.click(screen.getByRole('button', { name: '查看依据' }));
    const marker = history.state.__mingjing_panel;
    act(() => history.back());
    await settled();
    await act(async () => {
      pending.resolve(module);
      await pending.promise;
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '页面草稿' })).toHaveValue('合成草稿留在页面');
    act(() => history.forward());
    await waitFor(() => expect(history.state.__mingjing_panel).toBe(marker));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('closes on a route change while importing without navigating Back', async () => {
    const pending = deferred<ContentModule>();
    render(<Example load={() => pending.promise} />);
    await userEvent.click(screen.getByRole('button', { name: '查看依据' }));
    const back = vi.spyOn(history, 'back');
    act(() => {
      history.pushState({}, '', '/#/me');
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    await act(async () => {
      pending.resolve(module);
      await pending.promise;
    });
    expect(location.hash).toBe('#/me');
    expect(back).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('retains the actual trigger, parent selection and loaded module across close and reopen', async () => {
    const load = vi.fn<Loader>().mockResolvedValue(module);
    render(<Example load={load} />);
    const trigger = screen.getByRole('button', { name: '查看依据' });
    await userEvent.click(trigger);
    await screen.findByRole('dialog', { name: '依据说明' });
    await userEvent.click(screen.getByRole('button', { name: '选择明天' }));
    await userEvent.keyboard('{Escape}');
    await settled();
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(screen.getByRole('button', { name: '查看依据' })).toBe(trigger);
    await userEvent.click(trigger);
    expect(await screen.findByRole('dialog', { name: '依据说明' })).toBeVisible();
    expect(screen.getByText('已选：明天')).toBeVisible();
    expect(load).toHaveBeenCalledTimes(1);
  });

  it('keeps a rejected import recoverable with an explicit retry', async () => {
    const load = vi
      .fn<Loader>()
      .mockRejectedValueOnce(new Error('synthetic chunk unavailable'))
      .mockResolvedValue(module);
    render(<Example load={load} />);
    await userEvent.click(screen.getByRole('button', { name: '查看依据' }));
    expect(await screen.findByRole('alert', { name: '无法展开依据说明' })).toBeVisible();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '再试一次' }));
    expect(await screen.findByRole('dialog', { name: '依据说明' })).toBeVisible();
    expect(load).toHaveBeenCalledTimes(2);
  });
});

describe('controlled dialog exit Presence', () => {
  it('finishes its exit before removing all portal content without writing back controlled state', async () => {
    enableExitAnimations();
    const onOpenChange = vi.fn(),
      onReturnFocus = vi.fn();
    const props = {
      title: '退出说明',
      description: '合成过渡',
      sheet: true,
      contentId: 'exit-dialog',
      onOpenChange,
      onReturnFocus,
    };
    const view = render(
      <DialogContent {...props} open>
        临时内容应随退出移除
      </DialogContent>,
    );
    const dialog = await screen.findByRole('dialog', { name: '退出说明' });
    animation(dialog, 'animationstart', 'q8-enter');
    view.rerender(
      <DialogContent {...props} open={false}>
        临时内容应随退出移除
      </DialogContent>,
    );
    expect(dialog).toHaveAttribute('data-state', 'closed');
    expect(dialog).toBeInTheDocument();
    expect(onReturnFocus).not.toHaveBeenCalled();
    animation(dialog, 'animationend', 'q8-enter');
    expect(dialog).toBeInTheDocument();
    animation(dialog, 'animationend', 'q8-exit');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.queryByText('临时内容应随退出移除')).not.toBeInTheDocument();
    await waitFor(() => expect(onReturnFocus).toHaveBeenCalledTimes(1));
    expect(onOpenChange).not.toHaveBeenCalled();
    view.rerender(
      <DialogContent {...props} open>
        新的临时内容
      </DialogContent>,
    );
    expect(await screen.findByRole('dialog', { name: '退出说明' })).not.toBe(dialog);
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('keeps only the loaded control mounted after close and reuses it on the next open', async () => {
    enableExitAnimations();
    const mounted = vi.fn(),
      unmounted = vi.fn();
    function TrackedContent(props: ComponentProps<typeof DialogContent>) {
      useEffect(() => {
        mounted();
        return () => {
          unmounted();
        };
      }, []);
      return <DialogContent {...props} />;
    }
    const load = vi.fn<Loader>().mockResolvedValue({ default: TrackedContent });
    const view = render(<Example load={load} />);
    const trigger = screen.getByRole('button', { name: '查看依据' });
    await userEvent.click(trigger);
    const dialog = await screen.findByRole('dialog', { name: '依据说明' });
    animation(dialog, 'animationstart', 'q8-enter');
    const back = vi.spyOn(history, 'back');
    await userEvent.keyboard('{Escape}');
    await settled();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(dialog).toHaveAttribute('data-state', 'closed');
    fireEvent.click(screen.getByRole('button', { name: '关闭' }));
    expect(back).toHaveBeenCalledTimes(1);
    animation(dialog, 'animationend', 'q8-exit');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.queryByRole('textbox', { name: '面板输入' })).not.toBeInTheDocument();
    expect(mounted).toHaveBeenCalledTimes(1);
    expect(unmounted).not.toHaveBeenCalled();
    await waitFor(() => expect(trigger).toHaveFocus());
    await userEvent.click(trigger);
    expect(await screen.findByRole('dialog', { name: '依据说明' })).not.toBe(dialog);
    expect(load).toHaveBeenCalledTimes(1);
    expect(mounted).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(unmounted).toHaveBeenCalledTimes(1);
  });

  it('ignores an old exit event after rapid reopen and leaves focus inside the current dialog', async () => {
    enableExitAnimations();
    const load = vi.fn<Loader>().mockResolvedValue(module);
    render(<Example load={load} />);
    const trigger = screen.getByRole('button', { name: '查看依据' });
    await userEvent.click(trigger);
    const dialog = await screen.findByRole('dialog', { name: '依据说明' });
    const input = screen.getByRole('textbox', { name: '面板输入' });
    animation(dialog, 'animationstart', 'q8-enter');
    act(() => input.focus());
    expect(input).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    await settled();
    expect(dialog).toHaveAttribute('data-state', 'closed');
    fireEvent.click(trigger);
    expect(dialog).toHaveAttribute('data-state', 'open');
    animation(dialog, 'animationend', 'q8-exit');
    expect(dialog).toBeInTheDocument();
    expect(input).toHaveFocus();
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(history.state).toMatchObject({ page: 'chart', __mingjing_panel: expect.any(String) });
    expect(load).toHaveBeenCalledTimes(1);
  });
});

function PrivateResource() {
  const result = useResource<{ ok: boolean }>('/api/profile');
  return <p>{result.data?.ok ? '已显示合成资料' : '等候资料'}</p>;
}
function renderAuthenticatedBoundary() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuthGate>
        <PrivateResource />
      </AuthGate>
    </QueryClientProvider>,
  );
}

describe('deferred login view preserves the existing authentication boundary', () => {
  it('starts populated authenticated data immediately with no login view', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })));
    vi.stubGlobal('fetch', fetcher);
    renderAuthenticatedBoundary();
    expect(await screen.findByText('已显示合成资料')).toBeVisible();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe('/api/profile');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps data hidden and disabled until an explicit valid login acknowledgement', async () => {
    useAuth.setState({ token: '', loginRequired: true });
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: false })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true })))
      .mockImplementation(async () => new Response(JSON.stringify({ ok: true })));
    vi.stubGlobal('fetch', fetcher);
    const view = renderAuthenticatedBoundary();
    expect(view.container.querySelector('.auth-hidden')).toBeInTheDocument();
    expect(fetcher).not.toHaveBeenCalled();
    await screen.findByRole('dialog', { name: '登录明镜台' });
    await userEvent.type(screen.getByLabelText('网站口令'), ' synthetic-new-owner ');
    await userEvent.click(screen.getByRole('button', { name: '登录' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('没有收到登录确认');
    expect(useAuth.getState().loginRequired).toBe(true);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0]).toEqual([
      '/api/health',
      { headers: { 'X-Token': 'synthetic-new-owner' }, credentials: 'same-origin' },
    ]);
    await userEvent.click(screen.getByRole('button', { name: '登录' }));
    expect(await screen.findByText('已显示合成资料')).toBeVisible();
    expect(useAuth.getState().token).toBe('synthetic-new-owner');
    expect(useAuth.getState().loginRequired).toBe(false);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual(['/api/health', '/api/health', '/api/profile']);
  });
});
