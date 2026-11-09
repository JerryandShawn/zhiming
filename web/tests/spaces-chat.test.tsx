import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChatPreview from '../src/spaces/ChatPreview';
import { RouteBadge } from '../src/spaces/RouteBadge';
import { SpaceNavigation } from '../src/spaces/SpaceNavigation';
import { useSpacesDemo } from '../src/spaces/store';

function navigate(hash: string) {
  act(() => {
    window.history.replaceState(null, '', `?spaces=demo${hash}`);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
}

async function choose(label: string, option: string) {
  const user = userEvent.setup();
  await user.click(screen.getByRole('combobox', { name: label }));
  await user.click(screen.getByRole('option', { name: option }));
}

beforeEach(() => {
  useSpacesDemo.getState().reset();
  navigate('#/chat?space=all');
});

describe('功能区合成对话预览', () => {
  it('全部视图按时间显示全部消息，并为每条回答保留归区入口', () => {
    const { container } = render(<ChatPreview />);
    const data = useSpacesDemo.getState().data;
    const expected = [...data.messages].sort((a, b) => a.at.localeCompare(b.at)).map((item) => item.id);
    expect(
      Array.from(container.querySelectorAll('[data-message]')).map((item) => item.getAttribute('data-message')),
    ).toEqual(expected);
    expect(screen.getAllByRole('button', { name: /^(?:敏感区 )?归入：/ })).toHaveLength(
      data.messages.filter((item) => item.role === 'assistant').length,
    );
    expect(screen.getByRole('heading', { name: '全部 · 按时间' })).toBeVisible();
  });

  it('切换区与话题只显示对应消息，保留显式模拟模式', async () => {
    const user = userEvent.setup();
    const { container } = render(<ChatPreview />);
    await user.click(
      within(screen.getByRole('navigation', { name: '手机功能区' })).getByRole('link', { name: '事业学业' }),
    );
    await waitFor(() => expect(screen.getByRole('heading', { name: '学习计划' })).toBeVisible());
    expect(container.querySelectorAll('[data-message]')).toHaveLength(2);
    await user.click(
      within(screen.getByRole('navigation', { name: '区内话题' })).getByRole('link', { name: /跳槽 · 面试/ }),
    );
    await waitFor(() => expect(screen.getByRole('heading', { name: '跳槽 · 面试' })).toBeVisible());
    expect(
      Array.from(container.querySelectorAll('[data-message]')).map((item) => item.getAttribute('data-message')),
    ).toEqual(['i1', 'i2', 'i3', 'i4']);
    expect(window.location.search).toBe('?spaces=demo');
    expect(screen.queryByText('想每周留两晚学习数据分析。')).not.toBeInTheDocument();
  });

  it('七区与全部可横滑；身心和财务使用同一中性标签及锁图标', () => {
    navigate('#/chat?space=career&topic=interview');
    render(<SpaceNavigation mobile />);
    const navigation = screen.getByRole('navigation', { name: '手机功能区' });
    expect(within(navigation).getAllByRole('link')).toHaveLength(8);
    expect(within(navigation).getAllByRole('img', { name: '敏感区' })).toHaveLength(2);
    expect(within(navigation).getByRole('link', { name: '事业学业' })).toHaveAttribute('aria-current', 'page');
    expect(within(navigation).getByText('事业学业').closest('.tag')).toHaveClass('accent');
    expect(within(navigation).getByText('身心').closest('.tag')).toHaveClass('neutral');
    expect(within(navigation).getByText('财务').closest('.tag')).toHaveClass('neutral');
  });

  it('回答归区只移动选定消息，原文与时间保持不变，不发网络请求', async () => {
    const fetcher = vi.fn();
    vi.stubGlobal('fetch', fetcher);
    const before = structuredClone(useSpacesDemo.getState().data.messages);
    const user = userEvent.setup();
    render(<RouteBadge messageId="i2" spaceId="career" topicId="interview" />);
    await user.click(screen.getByRole('button', { name: /^归入：/ }));
    expect(screen.getByText(/不会连带移动其他消息/)).toBeVisible();
    await choose('主区', '家庭');
    await user.click(screen.getByRole('button', { name: '确认本地归属' }));
    expect(screen.getByRole('status')).toHaveTextContent('本地模拟已改归属');
    const after = useSpacesDemo.getState().data.messages;
    expect(after.find((item) => item.id === 'i2')).toEqual({
      ...before.find((item) => item.id === 'i2'),
      spaceId: 'family',
      topicId: 'reunion',
    });
    expect(after.filter((item) => item.id !== 'i2')).toEqual(before.filter((item) => item.id !== 'i2'));
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('新话题名字不能为空，确认后建立本地话题并保留原文', async () => {
    const user = userEvent.setup();
    render(<RouteBadge messageId="i2" spaceId="career" topicId="interview" />);
    await user.click(screen.getByRole('button', { name: /^归入：/ }));
    await choose('归入话题', '新建话题…');
    await user.click(screen.getByRole('button', { name: '确认本地归属' }));
    expect(screen.getByRole('alert')).toHaveTextContent('新话题需要一个名字');
    expect(useSpacesDemo.getState().data.topics.some((item) => item.title === '')).toBe(false);
    await user.type(screen.getByRole('textbox', { name: '新话题名字' }), '协作中的分歧');
    await user.click(screen.getByRole('button', { name: '确认本地归属' }));
    const state = useSpacesDemo.getState();
    const topic = state.data.topics.find((item) => item.title === '协作中的分歧');
    expect(topic).toMatchObject({ spaceId: 'career', messageIds: ['i2'] });
    expect(state.data.messages.find((item) => item.id === 'i2')?.topicId).toBe(topic?.id);
  });

  it('输入框归属可更改；草稿不发送，切区后采用新话题归属', async () => {
    const fetcher = vi.fn();
    vi.stubGlobal('fetch', fetcher);
    navigate('#/chat?space=career&topic=interview');
    const before = structuredClone(useSpacesDemo.getState().data);
    const user = userEvent.setup();
    render(<ChatPreview />);
    await user.type(screen.getByRole('textbox', { name: '本地对话草稿' }), '一段试写内容');
    await user.click(screen.getByRole('button', { name: /^将归入：/ }));
    await choose('主区', '家庭');
    await user.click(screen.getByRole('button', { name: '确认本地归属' }));
    expect(screen.getByRole('button', { name: /^将归入：家庭/ })).toBeVisible();
    expect(useSpacesDemo.getState().data).toEqual(before);
    navigate('#/chat?space=finance&topic=budget');
    expect(screen.getByRole('button', { name: /将归入：财务/ })).toBeVisible();
    expect(screen.getByRole('textbox', { name: '本地对话草稿' })).toHaveValue('一段试写内容');
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('不存在的深链接安全回退，不显示错误话题归属', () => {
    navigate('#/chat?space=unknown&topic=missing');
    render(<ChatPreview />);
    expect(screen.getByRole('heading', { name: '全部 · 按时间' })).toBeVisible();
    expect(screen.getByRole('status')).toHaveTextContent('已显示可用的示例对话');
    navigate('#/chat?space=career&topic=reunion');
    expect(screen.getByRole('heading', { name: '学习计划' })).toBeVisible();
    expect(screen.queryByText('想在月底安排一次家庭聚餐。')).not.toBeInTheDocument();
  });
});
