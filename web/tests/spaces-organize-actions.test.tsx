import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrganizePage from '../src/spaces/OrganizePage';
import { useSpacesDemo } from '../src/spaces/store';

const title = '跳槽 · 面试';
const group = () => screen.getByRole('group', { name: `${title}操作` });
const more = () => within(group()).getByRole('button', { name: '更多' });
const originalMessages = () => structuredClone(useSpacesDemo.getState().data.messages);

describe('mobile organize topic actions', () => {
  beforeEach(() => {
    useSpacesDemo.getState().reset();
    vi.mocked(window.matchMedia).mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  it('shows exactly rename, move and more; keeps the other three actions inside more', async () => {
    render(<OrganizePage />);
    expect(
      within(group())
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['改名', '移动', '更多']);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    await userEvent.click(more());
    const menu = await screen.findByRole('menu', { name: `${title}更多操作` });
    expect(
      within(menu)
        .getAllByRole('menuitem')
        .map((item) => item.textContent),
    ).toEqual(['合并', '拆分', '忽略本批']);
    expect(more()).toHaveAttribute('aria-expanded', 'true');
  });

  it('opens by keyboard, supports arrow/home/end navigation and returns focus with Escape', async () => {
    render(<OrganizePage />);
    more().focus();
    await userEvent.keyboard('{ArrowDown}');
    const menu = await screen.findByRole('menu', { name: `${title}更多操作` });
    const merge = within(menu).getByRole('menuitem', { name: '合并' });
    const split = within(menu).getByRole('menuitem', { name: '拆分' });
    const ignore = within(menu).getByRole('menuitem', { name: '忽略本批' });
    await waitFor(() => expect(merge).toHaveFocus());
    await userEvent.keyboard('{ArrowDown}');
    expect(split).toHaveFocus();
    await userEvent.keyboard('{End}');
    expect(ignore).toHaveFocus();
    await userEvent.keyboard('{ArrowDown}');
    expect(merge).toHaveFocus();
    await userEvent.keyboard('{Home}{ArrowUp}');
    expect(ignore).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
    expect(more()).toHaveFocus();
    await userEvent.keyboard('{ArrowUp}');
    await waitFor(() => expect(screen.getByRole('menuitem', { name: '忽略本批' })).toHaveFocus());
  });

  it('keeps focus on an outside button when a pointer click dismisses more', async () => {
    render(<OrganizePage />);
    await userEvent.click(more());
    expect(await screen.findByRole('menu')).toBeVisible();
    const outside = screen.getByRole('button', { name: '重置草稿' });
    await userEvent.click(outside);
    await waitFor(() => expect(outside).toHaveFocus());
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('lets Shift+Tab leave the menu and keeps focus at the preceding page control', async () => {
    render(
      <>
        <OrganizePage />
        <button>菜单之前的控件</button>
      </>,
    );
    await userEvent.click(more());
    const menu = await screen.findByRole('menu');
    within(menu).getByRole('menuitem', { name: '合并' }).focus();
    await userEvent.tab({ shift: true });
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
    expect(more()).not.toHaveFocus();
    expect(screen.getByRole('button', { name: '菜单之前的控件' })).toHaveFocus();
  });

  it.each([
    ['合并', '合并话题'],
    ['拆分', '拆分话题'],
  ])('closes more before opening the %s editor, then returns focus after cancel', async (command, heading) => {
    const before = originalMessages();
    render(<OrganizePage />);
    await userEvent.click(more());
    await userEvent.click(await screen.findByRole('menuitem', { name: command }));
    expect(await screen.findByRole('dialog', { name: heading })).toBeVisible();
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '取消' }));
    await waitFor(() => expect(more()).toHaveFocus());
    expect(originalMessages()).toEqual(before);
  });

  it('ignores from more, closes the menu and keeps every original message', async () => {
    const before = originalMessages();
    render(<OrganizePage />);
    await userEvent.click(more());
    await userEvent.click(await screen.findByRole('menuitem', { name: '忽略本批' }));
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
    expect(useSpacesDemo.getState().draft.ignoredTopicIds).toContain('interview');
    expect(screen.getByRole('region', { name: '本批忽略的话题' })).toHaveTextContent(title);
    expect(originalMessages()).toEqual(before);
  });

  it('disables all three topic entry points after applying', async () => {
    render(<OrganizePage />);
    act(() => {
      useSpacesDemo.getState().apply();
    });
    expect(within(group()).getAllByRole('button')).toHaveLength(3);
    within(group())
      .getAllByRole('button')
      .forEach((button) => expect(button).toBeDisabled());
    await userEvent.click(more());
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('restores the original five direct desktop actions when crossing the desktop breakpoint', async () => {
    const changes = vi.fn();
    let desktop = false;
    vi.mocked(window.matchMedia).mockImplementation((query) => ({
      get matches() {
        return desktop;
      },
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: changes,
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    render(<OrganizePage />);
    await userEvent.click(more());
    expect(await screen.findByRole('menu')).toBeVisible();
    act(() => {
      desktop = true;
      changes.mock.calls.forEach(([, listener]) => listener());
    });
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
    expect(
      within(group())
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['改名', '合并', '拆分', '移动', '忽略本批']);
  });
});
