import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../src/api/client';
import { MemoryReceipts } from '../src/chat/interactions/MemoryReceipts';
import { validMemoryReceipt, type MemoryCommandReceipt, type MemoryCommands } from '../src/chat/interactions/contracts';
import type { Receipt } from '../src/chat/types';

const pending: Receipt = {
  proposal_id: 'synthetic-proposal',
  write_status: 'pending_confirmation',
  summary: '调理期间早点休息',
  category: 'health',
  revision: 1,
};
const saved: Receipt = { fact_id: 'synthetic-fact', write_status: 'saved', summary: '面试在下周三', revision: 1 };
const port = (execute: MemoryCommands['execute']): MemoryCommands => ({ supports: () => true, execute });
describe('receipt-driven memory commands', () => {
  it.each(['remember', 'remember-category'] as const)(
    'keeps %s success visible when saved receipts become a closed group',
    async (action) => {
      const execute = vi
        .fn<MemoryCommands['execute']>()
        .mockRejectedValueOnce(new Error('合成断线，尚未收到确认'))
        .mockResolvedValueOnce({
          proposal_id: pending.proposal_id,
          fact_id: 'new-visible-fact',
          write_status: 'saved',
          revision: 2,
          ...(action === 'remember-category' ? { category: 'health', category_saved: true } : {}),
        });
      render(<MemoryReceipts receipts={[saved, pending]} commands={port(execute)} />);
      const label = action === 'remember' ? '记住' : '以后这类都记';
      await userEvent.click(screen.getByRole('button', { name: label }));
      expect(screen.queryByText('已记下这条信息。')).not.toBeInTheDocument();
      expect(screen.queryByText('已记下这条信息，并更新了本地同类记忆偏好。')).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole('button', { name: label }));
      const caption = screen.getByText('记下了 2 件事');
      expect(caption.closest('details')).not.toHaveAttribute('open');
      const message = action === 'remember' ? '已记下这条信息。' : '已记下这条信息，并更新了本地同类记忆偏好。';
      expect(screen.getByText(message)).toBeVisible();
      expect(screen.getByText(message)).toHaveAttribute('role', 'status');
    },
  );
  it('disables unsupported proposal actions in the real v3 adapter without issuing a request', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch');
    render(<MemoryReceipts receipts={[pending]} />);
    for (const name of ['记住', '不用', '以后这类都记']) {
      const button = screen.getByRole('button', { name });
      expect(button).toBeDisabled();
      await userEvent.click(button);
    }
    expect(screen.getByText('这些确认操作尚未接入，此条不会自动保存。')).toBeVisible();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('requires category support plus an actual category preference acknowledgement', async () => {
    const execute = vi
      .fn()
      .mockResolvedValueOnce({
        proposal_id: pending.proposal_id,
        fact_id: 'new-fact',
        write_status: 'saved',
        category: 'finance',
        category_saved: true,
      })
      .mockResolvedValueOnce({
        proposal_id: pending.proposal_id,
        fact_id: 'new-fact',
        write_status: 'saved',
        category: 'health',
        category_saved: true,
        revision: 2,
      });
    const { rerender } = render(
      <MemoryReceipts receipts={[{ ...pending, category: undefined }]} commands={port(execute)} />,
    );
    expect(screen.getByRole('button', { name: '以后这类都记' })).toBeDisabled();
    rerender(<MemoryReceipts receipts={[pending]} commands={port(execute)} />);
    await userEvent.click(screen.getByRole('button', { name: '以后这类都记' }));
    expect(screen.queryByText(/已记下/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '以后这类都记' }));
    await screen.findByText('本地同类记忆偏好已更新。');
    expect(screen.getByText('已记下：调理期间早点休息')).toBeVisible();
    expect(
      validMemoryReceipt('remember-category', pending, {
        proposal_id: pending.proposal_id,
        fact_id: 'f',
        write_status: 'saved',
      }),
    ).toBe(false);
  });
  it('keeps confirmed undo revision 2 when a later final repeats a saved revision 1 object', async () => {
    const commands = port(
      vi.fn(async () => ({ fact_id: saved.fact_id, write_status: 'stopped' as const, revision: 2 })),
    );
    const { rerender } = render(<MemoryReceipts receipts={[saved]} commands={commands} />);
    await userEvent.click(screen.getByRole('button', { name: '撤销使用' }));
    await screen.findByText('已撤销，不会再提起');
    rerender(<MemoryReceipts receipts={[{ ...saved, summary: 'final 重复的旧状态' }]} commands={commands} />);
    expect(screen.queryByText(/已记下/)).not.toBeInTheDocument();
    expect(screen.getByText('已撤销，不会再提起')).toBeVisible();
  });
  it('does not turn a confirmed remember back into pending when final repeats an old proposal', async () => {
    const commands = port(
      vi.fn(async () => ({
        proposal_id: pending.proposal_id,
        fact_id: 'confirmed-fact',
        write_status: 'saved' as const,
        revision: 2,
      })),
    );
    const { rerender } = render(<MemoryReceipts receipts={[pending]} commands={commands} />);
    await userEvent.click(screen.getByRole('button', { name: '记住' }));
    await screen.findByText('已记下：调理期间早点休息');
    rerender(<MemoryReceipts receipts={[{ ...pending }]} commands={commands} />);
    expect(screen.queryByRole('button', { name: '记住' })).not.toBeInTheDocument();
    expect(screen.getByText('已记下：调理期间早点休息')).toBeVisible();
  });
  it('only displays dismiss after its receipt and rejects mismatched target IDs', async () => {
    const execute = vi
      .fn()
      .mockResolvedValueOnce({ proposal_id: 'other', write_status: 'dismissed' })
      .mockResolvedValueOnce({ proposal_id: pending.proposal_id, write_status: 'dismissed' });
    render(<MemoryReceipts receipts={[pending]} commands={port(execute)} />);
    await userEvent.click(screen.getByRole('button', { name: '不用' }));
    expect(screen.getByText('这个比较私人，要不要我记住？')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '不用' }));
    await screen.findByText('这次不记，尚未保存为有效记忆');
    expect(screen.queryByText(/已记下/)).not.toBeInTheDocument();
  });
  it('prevents reentrant commands, groups saved receipts and updates the group after confirmed undo', async () => {
    let finish: (receipt: MemoryCommandReceipt) => void = () => undefined;
    const execute = vi.fn(
      () =>
        new Promise<MemoryCommandReceipt>((resolve) => {
          finish = resolve;
        }),
    );
    render(<MemoryReceipts receipts={[saved, { ...saved, fact_id: 'second-fact' }]} commands={port(execute)} />);
    await userEvent.click(screen.getByText('记下了 2 件事'));
    const button = screen.getAllByRole('button', { name: '撤销使用' })[0];
    fireEvent.click(button);
    fireEvent.click(button);
    expect(execute).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('已撤销，不会再提起')).not.toBeInTheDocument();
    await act(async () => finish({ fact_id: saved.fact_id, write_status: 'stopped', revision: 2 }));
    expect(screen.queryByText('记下了 2 件事')).not.toBeInTheDocument();
    expect(screen.getByText('已撤销，不会再提起')).toBeVisible();
  });
  it('retains the current saved state and disables blind resubmission on 409', async () => {
    render(
      <MemoryReceipts
        receipts={[saved]}
        commands={port(async () => {
          throw new ApiError(409, '内容已在别处更新，刷新后核对');
        })}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: '撤销使用' }));
    expect(screen.getByText('已记下：面试在下周三')).toBeVisible();
    expect(screen.getByRole('button', { name: '撤销使用' })).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('刷新后核对');
  });
});
