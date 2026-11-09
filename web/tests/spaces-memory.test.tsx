import { act, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import MemoryPreview from '../src/spaces/MemoryPreview';
import { useSpacesDemo } from '../src/spaces/store';

beforeEach(() => useSpacesDemo.getState().reset());

describe('按区查看合成记忆', () => {
  it('七个区分别列出记忆、重要的人与事项，敏感区使用锁图标', () => {
    render(<MemoryPreview />);
    const groups = screen.getAllByRole('region', { name: /记忆分组$/ });
    expect(groups).toHaveLength(7);
    for (const group of groups) {
      expect(within(group).getByRole('heading', { name: /^记忆$/ })).toBeVisible();
      expect(within(group).getByRole('heading', { name: '重要的人' })).toBeVisible();
      expect(within(group).getByRole('heading', { name: '事项' })).toBeVisible();
    }
    expect(screen.getAllByRole('img', { name: '敏感区' })).toHaveLength(2);
    expect(screen.getByRole('region', { name: '感情人际记忆分组' })).toHaveTextContent('小林（合成人物）');
    expect(screen.getByRole('region', { name: '家庭记忆分组' })).toHaveTextContent('家人甲（合成人物）');
    expect(screen.getByRole('link', { name: '审阅旧对话整理建议' })).toHaveAttribute('href', '#/organize');
  });

  it('草稿移动不影响分区事项，应用后移动，撤销后恢复', () => {
    render(<MemoryPreview />);
    const career = screen.getByRole('region', { name: '事业学业记忆分组' });
    const family = screen.getByRole('region', { name: '家庭记忆分组' });
    const title = '准备产品岗位面试（合成事项）';
    act(() => {
      useSpacesDemo.getState().moveTopic('interview', 'family');
    });
    expect(within(career).getByRole('link', { name: title })).toBeVisible();
    act(() => {
      useSpacesDemo.getState().apply();
    });
    expect(within(career).queryByRole('link', { name: title })).not.toBeInTheDocument();
    expect(within(family).getByRole('link', { name: title })).toHaveAttribute(
      'href',
      '#/chat?space=family&topic=interview',
    );
    act(() => {
      useSpacesDemo.getState().revert();
    });
    expect(within(career).getByRole('link', { name: title })).toBeVisible();
    expect(within(family).queryByRole('link', { name: title })).not.toBeInTheDocument();
  });
});
