import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import Tarot from '../src/pages/Tarot';

describe('local tarot draft continuity', () => {
  it.each([
    ['看一件事', 1],
    ['A/B选择', 5],
  ] as const)('keeps the question, %s layout, count and orientation through reveal', async (spread, count) => {
    const user = userEvent.setup();
    render(<Tarot />);
    await user.click(screen.getByRole('button', { name: /新问题/ }));
    const question = screen.getByRole('textbox', { name: '想问什么？' });
    await user.clear(question);
    await user.type(question, '如何安排接下来一周？');
    await user.click(screen.getByRole('button', { name: new RegExp(spread) }));
    if (count === 5) {
      await user.type(screen.getByRole('textbox', { name: '选项A' }), '先准备');
      await user.type(screen.getByRole('textbox', { name: '选项B' }), '先休息');
    }
    await user.click(screen.getByRole('switch', { name: '含逆位' }));
    await user.click(screen.getByRole('button', { name: '开始（合成示例）' }));
    expect(screen.getByRole('heading', { name: '如何安排接下来一周？' })).toBeVisible();
    const next = screen.getByRole('button', { name: '查看合成牌阵' });
    expect(next).toBeDisabled();
    for (let index = 1; index <= count; index++)
      await user.click(screen.getByRole('button', { name: new RegExp(`^第${index}张牌$`) }));
    expect(screen.getByRole('status')).toHaveTextContent(`已选 ${count} / ${count}`);
    await user.click(next);
    expect(screen.getAllByRole('img', { name: '不透明的塔罗牌背' })).toHaveLength(count);
    await user.click(screen.getByRole('button', { name: '全部揭开' }));
    expect(screen.getAllByRole('img', { name: /正位$/ })).toHaveLength(count);
    expect(screen.queryByRole('img', { name: /逆位/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '看解读' }));
    expect(screen.getByRole('heading', { name: '如何安排接下来一周？' })).toBeVisible();
    expect(screen.getAllByRole('img', { name: /正位$/ })).toHaveLength(count);
    expect(screen.getByText(/仅正位/)).toBeVisible();
    if (count === 5) expect(screen.getByText('A：先准备；B：先休息')).toBeVisible();
    await user.click(screen.getByRole('button', { name: '补充背景再解读' }));
    expect(screen.getByRole('textbox', { name: '想问什么？' })).toHaveValue('如何安排接下来一周？');
  });
});
