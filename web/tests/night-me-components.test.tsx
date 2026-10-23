import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrictMode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AboutMePage from '../src/night/me/AboutMePage';
import { createAboutMeStore } from '../src/night/me/port';
import {
  AboutMeError,
  PROFILE_SECTIONS,
  type AboutMeCommand,
  type AboutMePort,
  type AboutMeReceipt,
} from '../src/night/me/types';

beforeEach(() => {
  history.replaceState(null, '', '/#/me');
});
const article = (id: string) =>
  document.querySelector<HTMLElement>(`[data-profile-id="${id}"], [data-memory-id="${id}"]`)!;
const tab = (label: string) =>
  userEvent.click(within(screen.getByRole('group', { name: '关于我的分区' })).getByRole('button', { name: label }));
const editBasic = () => userEvent.click(screen.getByRole('button', { name: '编辑画像条目：称呼与基本情况' }));
async function changeDraft(text: string) {
  const field = screen.getByRole('textbox', { name: '你的说法' });
  await userEvent.clear(field);
  await userEvent.type(field, text);
}
function gate() {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { promise, release };
}

describe('About Me injected-port UI', () => {
  it('renders six tabs and exactly eight profile sections with no speculative user-edited labels', () => {
    const port = createAboutMeStore();
    const fetch = vi.spyOn(globalThis, 'fetch');
    render(<AboutMePage port={port} />);
    const tabs = within(screen.getByRole('group', { name: '关于我的分区' })).getAllByRole('button');
    expect(tabs.map((button) => button.textContent)).toEqual([
      '画像',
      '记忆',
      '待确认',
      '重要的人',
      '时间线',
      '符号词典',
    ]);
    for (const section of PROFILE_SECTIONS)
      expect(screen.getByRole('region', { name: section.label })).toBeInTheDocument();
    expect(document.querySelectorAll('[data-profile-id]')).toHaveLength(8);
    expect(screen.queryByText('你改过', { exact: true })).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('does not mark a draft edited or close the panel before a valid receipt, including StrictMode', async () => {
    const base = createAboutMeStore(),
      deferred = gate();
    const execute = vi.fn(async (command: AboutMeCommand) => {
      await deferred.promise;
      return base.execute(command);
    });
    render(
      <StrictMode>
        <AboutMePage port={{ ...base, execute }} />
      </StrictMode>,
    );
    await editBasic();
    await changeDraft('我希望被称作小远（合成编辑）');
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    expect(execute).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('dialog', { name: '修改画像条目' })).toBeInTheDocument();
    expect(screen.queryByText('你改过', { exact: true })).not.toBeInTheDocument();
    expect(portRevision()).toBe('1');
    await act(async () => deferred.release());
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(article('profile-basic')).toHaveTextContent('我希望被称作小远（合成编辑）');
    expect(within(article('profile-basic')).getByText('你改过')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('修改已确认。');
  });

  it('keeps the immutable edit payload and request ID through rate-limit and network retries', async () => {
    const base = createAboutMeStore();
    const execute = vi
      .fn<AboutMePort['execute']>()
      .mockRejectedValueOnce(new AboutMeError('RATE_LIMIT', 429, 'private body must not render'))
      .mockRejectedValueOnce(new AboutMeError('NETWORK', 0, 'private body must not render'))
      .mockImplementation((command) => base.execute(command));
    render(<AboutMePage port={{ ...base, execute }} />);
    await editBasic();
    await changeDraft('合成重试草稿');
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    expect(screen.getByRole('textbox', { name: '你的说法' })).toHaveValue('合成重试草稿');
    expect(screen.getByRole('textbox', { name: '你的说法' })).toBeDisabled();
    expect(portRevision()).toBe('1');
    expect(screen.queryByText('private body must not render')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '用原操作重试' }));
    expect(portRevision()).toBe('1');
    await userEvent.click(screen.getByRole('button', { name: '用原操作重试' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(execute).toHaveBeenCalledTimes(3);
    expect(execute.mock.calls[1][0]).toBe(execute.mock.calls[0][0]);
    expect(execute.mock.calls[2][0]).toBe(execute.mock.calls[0][0]);
    expect(portRevision()).toBe('2');
  });

  it('preserves a conflicting draft and forbids writes until the latest version is explicitly checked', async () => {
    const base = createAboutMeStore();
    let first = true;
    const execute = vi.fn(async (command: AboutMeCommand) => {
      if (first) {
        first = false;
        await base.execute({
          type: 'profile-edit',
          id: 'profile-basic',
          text: '另一份已保存的合成内容',
          expectedRevision: 1,
          requestId: 'external-edit',
        });
        throw new AboutMeError('CONFLICT', 409, 'do not render private original');
      }
      return base.execute(command);
    });
    render(<AboutMePage port={{ ...base, execute }} />);
    await editBasic();
    await changeDraft('我还要保留的合成草稿');
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    expect(screen.getByRole('textbox', { name: '你的说法' })).toHaveValue('我还要保留的合成草稿');
    expect(screen.getByRole('button', { name: '保存修改' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    expect(execute).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('button', { name: '核对当前版本' }));
    expect(within(screen.getByRole('dialog')).getByText('另一份已保存的合成内容')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '已核对，继续编辑' }));
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(execute.mock.calls[1][0]).toMatchObject({ expectedRevision: 2, text: '我还要保留的合成草稿' });
    expect(execute.mock.calls[1][0].requestId).not.toBe(execute.mock.calls[0][0].requestId);
  });

  it('does not accept an unrelated or malformed confirmation as a successful edit', async () => {
    const base = createAboutMeStore();
    const execute = vi.fn(async (command: AboutMeCommand): Promise<AboutMeReceipt> => ({
      id: command.id,
      requestId: 'wrong-request',
      kind: command.type,
      revision: 2,
      snapshotRevision: 2,
      write_status: 'saved',
      affectedIds: [command.id],
    }));
    render(<AboutMePage port={{ ...base, execute }} />);
    await editBasic();
    await changeDraft('不能提前确认的草稿');
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    expect(screen.getByRole('alert')).toHaveTextContent('尚未收到有效确认');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.queryByText('你改过', { exact: true })).not.toBeInTheDocument();
    expect(portRevision()).toBe('1');
  });

  it('shows authorized source quotes only and keeps feature-space labels separate from profile sections', async () => {
    render(<AboutMePage port={createAboutMeStore()} />);
    await tab('记忆');
    expect(document.querySelectorAll('[data-memory-id]')).toHaveLength(8);
    expect(within(article('memory-basic')).getByText('功能区归属：事业学业')).toBeInTheDocument();
    const sourceButton = within(article('memory-basic')).getByRole('button', { name: '查看来源' });
    expect(sourceButton).toHaveTextContent('查看来源');
    expect(sourceButton.textContent).toBe(sourceButton.getAttribute('aria-label'));
    await userEvent.click(sourceButton);
    const source = screen.getByRole('dialog', { name: '来源原话' });
    expect(source).toHaveTextContent('请叫我阿远，目前在学习产品设计。');
    expect(document.body).not.toHaveTextContent('这句未授权节选不应整段展示');
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('clearly limits chart-summary text edits to the profile, without changing chart data', async () => {
    const port = createAboutMeStore();
    render(<AboutMePage port={port} />);
    await userEvent.click(screen.getByRole('button', { name: '编辑画像条目：命理档案摘要' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('这里只修改画像文字，不会改变盘面或出生资料。');
    expect(screen.queryByLabelText('出生日期')).not.toBeInTheDocument();
  });

  it('previews both deletion scopes without writes, and cancelling preserves the complete snapshot', async () => {
    const base = createAboutMeStore(),
      execute = vi.fn(base.execute),
      before = base.getSnapshot();
    render(<AboutMePage port={{ ...base, execute }} />);
    await tab('记忆');
    for (const scope of ['只删这条', '删除整段来源']) {
      await userEvent.click(within(article('memory-basic')).getByRole('button', { name: '删除记忆' }));
      await userEvent.click(screen.getByRole('radio', { name: new RegExp(`^${scope}`) }));
      await userEvent.click(screen.getByRole('button', { name: '预览删除范围' }));
      expect(screen.getByRole('region', { name: '删除影响预览' })).toHaveTextContent('记忆');
      expect(execute).not.toHaveBeenCalled();
      await userEvent.click(screen.getByRole('button', { name: '取消' }));
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
      expect(base.getSnapshot()).toBe(before);
    }
  });

  it('requires a second confirmation and shows source deletion impact counts before cascading', async () => {
    const base = createAboutMeStore(),
      execute = vi.fn(base.execute);
    render(<AboutMePage port={{ ...base, execute }} />);
    await tab('记忆');
    await userEvent.click(within(article('memory-basic')).getByRole('button', { name: '删除记忆' }));
    await userEvent.click(screen.getByRole('radio', { name: /^删除整段来源/ }));
    await userEvent.click(screen.getByRole('button', { name: '预览删除范围' }));
    const preview = screen.getByRole('region', { name: '删除影响预览' });
    expect(preview).toHaveTextContent('记忆2 条画像条目2 条待确认内容1 条符号联想0 条');
    expect(execute).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: '确认删除整段来源' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(execute).toHaveBeenCalledTimes(1);
    expect(article('memory-basic')).toBeNull();
    expect(article('memory-life')).toBeNull();
    expect(article('memory-goals')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('删除已确认。');
  });

  it('returns focus to the edit trigger after Escape and to the active tab after deleting its trigger', async () => {
    render(<AboutMePage port={createAboutMeStore()} />);
    const trigger = screen.getByRole('button', { name: '编辑画像条目：称呼与基本情况' });
    await userEvent.click(trigger);
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(trigger).toHaveFocus());
    await userEvent.click(screen.getByRole('button', { name: '删除画像条目：称呼与基本情况' }));
    await userEvent.click(screen.getByRole('button', { name: '确认删除画像条目' }));
    await waitFor(() =>
      expect(
        within(screen.getByRole('group', { name: '关于我的分区' })).getByRole('button', { name: '画像' }),
      ).toHaveFocus(),
    );
  });

  for (const action of ['记住', '不用', '以后这类都记'])
    it(`waits for a valid proposal acknowledgement and renders a readonly result: ${action}`, async () => {
      const base = createAboutMeStore(),
        deferred = gate();
      const execute = vi.fn(async (command: AboutMeCommand) => {
        await deferred.promise;
        return base.execute(command);
      });
      render(<AboutMePage port={{ ...base, execute }} />);
      await tab('待确认');
      const pending = document.querySelector<HTMLElement>('[data-proposal-id="local-proposal"]')!;
      await userEvent.click(within(pending).getByRole('button', { name: action }));
      expect(pending).toHaveTextContent('待你确认，尚未保存为有效记忆');
      expect(portRevision()).toBe('1');
      for (const button of within(pending)
        .getAllByRole('button')
        .filter((button) => button.textContent !== '查看来源'))
        if (!button.getAttribute('aria-label')?.startsWith('查看来源')) expect(button).toBeDisabled();
      await act(async () => deferred.release());
      await waitFor(() => expect(document.querySelector('[data-proposal-id="local-proposal"]')).toBeNull());
      expect(portRevision()).toBe('2');
      const status = screen
        .getAllByRole('status')
        .map((node) => node.textContent)
        .join(' ');
      expect(status).toContain(
        action === '不用' ? '这次不记' : action === '以后这类都记' ? '本地同类记忆偏好已更新' : '已记下',
      );
    });

  it('responds to section query changes while mounted and shows readonly people, timeline and dictionary content', async () => {
    render(<AboutMePage port={createAboutMeStore()} />);
    await act(async () => {
      location.hash = '/me?section=memory';
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    });
    expect(screen.getByRole('searchbox', { name: '搜索记忆' })).toBeInTheDocument();
    await tab('重要的人');
    await userEvent.click(screen.getByRole('button', { name: /小林（合成人物）/ }));
    expect(screen.getByRole('dialog', { name: '相关记忆' })).toHaveTextContent('小林是常一起看展的朋友。');
    await userEvent.keyboard('{Escape}');
    await tab('时间线');
    expect(screen.getByRole('region', { name: '时间线' })).toHaveTextContent('面试后回顾准备过程');
    await tab('符号词典');
    expect(screen.getByRole('region', { name: '符号词典' })).toHaveTextContent('慢一点也没关系');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '删除这个联想' })).toBeInTheDocument();
  });

  it('rejects a category preference receipt that acknowledges a different category', async () => {
    const base = createAboutMeStore();
    const execute = vi.fn(async (command: AboutMeCommand): Promise<AboutMeReceipt> => ({
      id: command.id,
      requestId: command.requestId,
      kind: command.type,
      revision: 2,
      snapshotRevision: 2,
      write_status: 'saved',
      affectedIds: [command.id],
      memoryReceipt: {
        proposal_id: command.id,
        fact_id: 'wrong-category-fact',
        write_status: 'saved',
        revision: 2,
        summary: '合成信息',
        category_saved: true,
        category: 'finance',
      },
    }));
    render(<AboutMePage port={{ ...base, execute }} />);
    await tab('待确认');
    const pending = document.querySelector<HTMLElement>('[data-proposal-id="local-proposal"]')!;
    await userEvent.click(within(pending).getByRole('button', { name: '以后这类都记' }));
    expect(within(pending).getByRole('alert')).toHaveTextContent('尚未收到有效确认');
    expect(within(pending).queryByRole('status')).not.toBeInTheDocument();
    expect(portRevision()).toBe('1');
  });
});

function portRevision() {
  return document.querySelector('[data-runtime="night-me"]')?.getAttribute('data-revision');
}
