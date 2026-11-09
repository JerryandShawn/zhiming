import { act, fireEvent, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { Layout } from '../src/Layout';
import { PrivateChat, PrivacyToggle, usePrivacySession } from '../src/night/privacy';
import type { PrivacyOptions } from '../src/night/privacy/session';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function Harness({ options }: { options?: PrivacyOptions }) {
  const privacy = usePrivacySession(options);
  const [normal, setNormal] = useState('普通合成草稿');
  return (
    <>
      <PrivacyToggle active={privacy.active} onChange={privacy.setActive} />
      {privacy.active ? (
        <PrivateChat privacy={privacy} />
      ) : (
        <input aria-label="普通草稿" value={normal} onChange={(event) => setNormal(event.target.value)} />
      )}
    </>
  );
}

describe('local privacy control and session UI', () => {
  it('keeps ordinary and incognito drafts separate and shows a persistent, accessible exit', async () => {
    render(<Harness />);
    const toggle = screen.getByRole('switch', { name: '无痕模式' });
    await userEvent.click(toggle);
    const region = screen.getByRole('region', { name: '无痕对话提示' });
    expect(region).toHaveTextContent('这段不会被记住');
    expect(screen.getByRole('heading', { name: '无痕对话' })).toBeInTheDocument();
    const privateInput = screen.getByRole('textbox', { name: '和明镜说说' });
    expect(privateInput).toHaveValue('');
    await userEvent.type(privateInput, 'PRIVATE_SYNTHETIC_DRAFT');
    const first = document.querySelector('[data-thread-id]')?.getAttribute('data-thread-id');
    await userEvent.click(screen.getByRole('button', { name: '退出无痕' }));
    expect(screen.getByRole('textbox', { name: '普通草稿' })).toHaveValue('普通合成草稿');
    expect(screen.queryByDisplayValue('PRIVATE_SYNTHETIC_DRAFT')).not.toBeInTheDocument();
    await userEvent.click(toggle);
    expect(screen.getByRole('textbox', { name: '和明镜说说' })).toHaveValue('');
    expect(document.querySelector('[data-thread-id]')?.getAttribute('data-thread-id')).not.toBe(first);
    expect(screen.queryByRole('region', { name: '待确认记忆' })).not.toBeInTheDocument();
  });

  it('rejects a FileReader result that completes after exit and a new private session starts', async () => {
    const readers: { result: string; onload?: () => void }[] = [];
    class DeferredReader {
      result = 'data:image/png;base64,UFJJVkFURV9JTUFHRQ==';
      onload?: () => void;
      onerror?: () => void;
      readAsDataURL() {
        readers.push(this);
      }
    }
    vi.stubGlobal('FileReader', DeferredReader);
    render(<Harness />);
    await userEvent.click(screen.getByRole('switch', { name: '无痕模式' }));
    fireEvent.change(screen.getByLabelText('选择本轮图片'), {
      target: { files: [new File(['synthetic'], 'synthetic.png', { type: 'image/png' })] },
    });
    expect(readers).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: '退出无痕' }));
    await userEvent.click(screen.getByRole('switch', { name: '无痕模式' }));
    await act(async () => {
      readers[0].onload?.();
    });
    expect(screen.queryByRole('list', { name: '本轮附图' })).not.toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain('UFJJVkFURV9JTUFHRQ==');
  });

  it('retains input focus until pointer-up completes exit or mode switching', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const toggle = screen.getByRole('switch', { name: '无痕模式' });
    await user.click(toggle);
    const input = screen.getByRole('textbox', { name: '和明镜说说' });
    input.focus();
    const exit = screen.getByRole('button', { name: '退出无痕' });
    await user.pointer({ target: exit, keys: '[MouseLeft>]' });
    expect(input).toHaveFocus();
    expect(screen.getByRole('region', { name: '无痕对话提示' })).toBeInTheDocument();
    await user.pointer({ target: exit, keys: '[/MouseLeft]' });
    const normal = screen.getByRole('textbox', { name: '普通草稿' });
    expect(normal).toHaveValue('普通合成草稿');
    normal.focus();
    await user.pointer({ target: toggle, keys: '[MouseLeft>]' });
    expect(normal).toHaveFocus();
    expect(screen.queryByRole('region', { name: '无痕对话提示' })).not.toBeInTheDocument();
    await user.pointer({ target: toggle, keys: '[/MouseLeft]' });
    expect(screen.getByRole('region', { name: '无痕对话提示' })).toBeInTheDocument();
  });

  it('keeps keyboard exit available and leaves pointer events on descriptive text uncancelled', async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole('switch', { name: '无痕模式' }));
    screen.getByRole('textbox', { name: '和明镜说说' }).focus();
    expect(fireEvent.pointerDown(screen.getAllByText('这段不会被记住')[0])).toBe(true);
    const exit = screen.getByRole('button', { name: '退出无痕' });
    exit.focus();
    await userEvent.keyboard('{Enter}');
    expect(screen.getByRole('textbox', { name: '普通草稿' })).toHaveValue('普通合成草稿');
  });

  it('clears private content when the idle timer expires and when its owner unmounts', () => {
    vi.useFakeTimers();
    const { result, unmount } = renderHook(() => usePrivacySession({ idleMs: 1000 }));
    act(() => result.current.enter());
    const oldSetter = result.current.setImages;
    act(() => result.current.setDraft('PRIVATE_IDLE_DRAFT'));
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current).toMatchObject({ active: false, session: null, endedBy: 'idle' });
    act(() => result.current.enter());
    act(() => oldSetter(['PRIVATE_LATE_IMAGE']));
    expect(result.current.session?.images).toEqual([]);
    const old = result.current;
    unmount();
    old.setDraft('PRIVATE_AFTER_UNMOUNT');
    expect(old.session?.draft).toBe('');
  });

  it('adds a controlled Layout switch without enabling ordinary v3 or spaces switches', async () => {
    const normal = render(
      <Layout page="chat">
        <p>普通入口</p>
      </Layout>,
    );
    expect(screen.getByRole('switch', { name: '侧栏无痕模式' })).toBeDisabled();
    expect(screen.getByText('无痕对话正在准备，暂不可用。')).toBeVisible();
    normal.unmount();
    const spaces = render(
      <Layout page="me" preview spacesPreview>
        <p>功能区预览</p>
      </Layout>,
    );
    expect(screen.getByRole('switch', { name: '侧栏无痕模式' })).toBeDisabled();
    spaces.unmount();
    const change = vi.fn();
    render(
      <Layout page="chat" privacy={{ active: true, onChange: change, description: '本地无痕预览' }}>
        <p>无痕入口</p>
      </Layout>,
    );
    const toggle = screen.getByRole('switch', { name: '侧栏无痕模式' });
    expect(toggle).toBeChecked();
    expect(toggle).toBeEnabled();
    expect(screen.queryByText('无痕对话正在准备，暂不可用。')).not.toBeInTheDocument();
    await userEvent.click(toggle);
    expect(change).toHaveBeenCalledWith(false);
    expect(screen.getByText('本地无痕预览')).toBeVisible();
  });
});
