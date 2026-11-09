import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Answer } from '../src/chat/Answers';
import { initialStream } from '../src/chat/types';
import { InteractiveAskCard } from '../src/chat/interactions/AskCard';
import { ToolProgress } from '../src/chat/interactions/ToolProgress';
import type { AskAnswerReceipt } from '../src/chat/interactions/contracts';

const question = {
  question: '先看安排还是准备？',
  options: ['安排', '准备'],
  allow_free_text: true,
  why: '核对接下来的一步',
};
describe('shared answer interactions', () => {
  it('only locks a selected answer after confirmation and prevents duplicate asynchronous activation', async () => {
    let finish: (receipt: AskAnswerReceipt) => void = () => undefined;
    const submit = vi.fn(
      () =>
        new Promise<AskAnswerReceipt>((resolve) => {
          finish = resolve;
        }),
    );
    render(<InteractiveAskCard question={question} onAnswer={submit} />);
    const option = screen.getByRole('button', { name: '安排' });
    fireEvent.click(option);
    fireEvent.click(option);
    expect(submit).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('你选了：安排')).not.toBeInTheDocument();
    await act(async () => finish({ status: 'accepted', answer: '安排', request_id: 'synthetic-ask' }));
    expect(screen.getByText('你选了：安排')).toBeVisible();
    expect(option).toHaveAttribute('aria-pressed', 'true');
    for (const button of screen.getAllByRole('button')) expect(button).toBeDisabled();
  });
  it('keeps an unconfirmed answer retryable and does not invent a legacy acknowledgement', async () => {
    const submit = vi
      .fn()
      .mockRejectedValueOnce(new Error('尚未收到确认'))
      .mockResolvedValue({ status: 'accepted', answer: '安排', request_id: 'synthetic-retry' });
    const { unmount } = render(<InteractiveAskCard question={question} onAnswer={submit} />);
    await userEvent.click(screen.getByRole('button', { name: '安排' }));
    expect(screen.queryByText('你选了：安排')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '安排' }));
    expect(submit.mock.calls).toEqual([['安排'], ['安排']]);
    expect(screen.getByText('你选了：安排')).toBeVisible();
    unmount();
    const legacy = vi.fn();
    render(<InteractiveAskCard question={question} onReply={legacy} />);
    await userEvent.click(screen.getByRole('button', { name: '准备' }));
    expect(legacy).toHaveBeenCalledWith('准备');
    expect(screen.queryByText('你选了：准备')).not.toBeInTheDocument();
    expect(screen.getByText('选择已发出，尚未收到确认。')).toBeVisible();
  });
  it('rejects a response for a different answer instead of marking it answered', async () => {
    const submit = vi.fn(async () => ({
      status: 'accepted' as const,
      answer: '准备',
      request_id: 'synthetic-wrong-answer',
    }));
    render(<InteractiveAskCard question={question} onAnswer={submit} />);
    await userEvent.click(screen.getByRole('button', { name: '安排' }));
    expect(screen.getByRole('alert')).toHaveTextContent('尚未收到回答确认');
    expect(screen.queryByText(/你选了/)).not.toBeInTheDocument();
  });
  it('focuses the main composer for free text and supports a controlled confirmed selection', async () => {
    const { rerender } = render(
      <>
        <textarea id="composer-input" aria-label="主输入框" />
        <InteractiveAskCard question={question} />
      </>,
    );
    await userEvent.click(screen.getByRole('button', { name: '我自己说' }));
    expect(screen.getByRole('textbox')).toHaveFocus();
    rerender(<InteractiveAskCard question={question} answered="准备" />);
    expect(screen.getByRole('button', { name: '准备' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '安排' })).toBeDisabled();
  });
  it('shows an explicit review pending state without a spinner and exposes the revised tooltip by keyboard', async () => {
    const { container, rerender } = render(<Answer state={initialStream()} reviewPending />);
    expect(screen.getByText('复核中')).toBeVisible();
    expect(container.querySelector('.spinner')).toBeNull();
    rerender(<Answer state={{ ...initialStream(), revised: true }} />);
    const badge = screen.getByText('已修订');
    badge.focus();
    await screen.findByRole('tooltip');
    expect(screen.getByRole('tooltip')).toHaveTextContent('复核后修正了一处说法');
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
  it('keeps the tool dot static, counts only completed operations and folds the finished list', async () => {
    const tools = [{ name: 'memory_recall', summary: '查找面试安排', done: false }];
    const { container, rerender } = render(<ToolProgress tools={tools} status="在翻上次的安排…" complete={false} />);
    expect(screen.getByRole('status')).toHaveTextContent('在翻上次的安排');
    expect(container.querySelector('.status-dot')).not.toBeNull();
    rerender(
      <ToolProgress
        tools={[
          { ...tools[0], done: true },
          { name: 'chart_compute', summary: '核对流日', done: true },
        ]}
        status=""
        complete
      />,
    );
    expect(container.querySelector('.status-dot')).toBeNull();
    const caption = screen.getByText('查了 1 次记忆 · 完成 1 次计算');
    expect(caption.closest('details')).not.toHaveAttribute('open');
    await userEvent.click(caption);
    expect(caption.closest('details')).toHaveAttribute('open');
  });
  it('renders all decision dimensions and a pending tag using responsive layout classes', () => {
    render(
      <Answer
        state={{
          ...initialStream(),
          decisions: [
            {
              option: '先准备',
              benefit: '从容',
              cost: '一晚时间',
              risk: '待确认',
              reversibility: '可以调整',
              first_step: '列清单',
            },
          ],
        }}
      />,
    );
    for (const label of ['收益', '代价', '风险', '可逆性', '第一步']) expect(screen.getByText(label)).toBeVisible();
    expect(screen.getAllByText('待确认')).toHaveLength(2);
    expect(screen.getByLabelText('可比较的选择')).toHaveClass('live-decision-options', 'count-1');
  });
});
