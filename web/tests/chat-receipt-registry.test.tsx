import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryReceipts } from '../src/chat/interactions/MemoryReceipts';
import { createMemoryReceiptRegistry } from '../src/chat/interactions/memoryProjection';
import type { MemoryCommands } from '../src/chat/interactions/contracts';
import { useAuth } from '../src/api/client';
import type { Receipt } from '../src/chat/types';
import { initialStream } from '../src/chat/types';
import { Answer } from '../src/chat/Answers';

const saved: Receipt = { fact_id: 'synthetic', summary: '合成偏好', write_status: 'saved', revision: 1 };
afterEach(() => useAuth.getState().setToken(''));
describe('memory receipt high-water registry', () => {
  it('synchronizes raw inbound revision 2 to an already mounted answer after commit', async () => {
    const registry = createMemoryReceiptRegistry(),
      listener = vi.fn();
    registry.subscribe(listener);
    const view = (incoming?: Receipt) => (
      <>
        <Answer state={{ ...initialStream(), receipts: [saved] }} receiptRegistry={registry} />
        {incoming && <Answer state={{ ...initialStream(), receipts: [incoming] }} receiptRegistry={registry} />}
      </>
    );
    const { rerender } = render(view());
    expect(listener).not.toHaveBeenCalled();
    rerender(view({ ...saved, write_status: 'stopped', revision: 2 }));
    await waitFor(() => expect(screen.getAllByText('已撤销，不会再提起')).toHaveLength(2));
    expect(screen.queryByText('已记下：合成偏好')).not.toBeInTheDocument();
    expect(listener).toHaveBeenCalledTimes(1);
    rerender(view({ ...saved, write_status: 'stopped', revision: 2 }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(listener).toHaveBeenCalledTimes(1);
  });
  it('does not broadcast or loop for repeated same-revision objects and only enriches missing metadata', async () => {
    const registry = createMemoryReceiptRegistry(),
      listener = vi.fn();
    registry.subscribe(listener);
    const view = () => (
      <>
        <Answer state={{ ...initialStream(), receipts: [{ ...saved }] }} receiptRegistry={registry} />
        <Answer
          state={{ ...initialStream(), receipts: [{ ...saved, summary: '重复对象的另一摘要' }] }}
          receiptRegistry={registry}
        />
      </>
    );
    const { rerender } = render(view());
    for (let attempt = 0; attempt < 3; attempt++) rerender(view());
    await act(async () => {
      await Promise.resolve();
    });
    expect(listener).not.toHaveBeenCalled();
    expect(screen.getAllByText('已记下：合成偏好')).toHaveLength(2);
  });
  it('synchronizes two mounted answers only after a confirmed command, without broadcasting during render', async () => {
    const registry = createMemoryReceiptRegistry();
    const listener = vi.fn(),
      unsubscribe = registry.subscribe(listener);
    const execute = vi.fn<MemoryCommands['execute']>(async () => ({
      fact_id: saved.fact_id,
      write_status: 'stopped',
      revision: 2,
    }));
    const commands: MemoryCommands = { supports: () => true, execute };
    render(
      <>
        <Answer
          state={{ ...initialStream(), receipts: [saved] }}
          receiptRegistry={registry}
          memoryCommands={commands}
        />
        <Answer
          state={{ ...initialStream(), receipts: [{ ...saved }] }}
          receiptRegistry={registry}
          memoryCommands={commands}
        />
      </>,
    );
    expect(listener).not.toHaveBeenCalled();
    expect(screen.getAllByText('已记下：合成偏好')).toHaveLength(2);
    await userEvent.click(screen.getAllByRole('button', { name: '撤销使用' })[0]);
    expect(await screen.findAllByText('已撤销，不会再提起')).toHaveLength(2);
    expect(screen.queryByText('已记下：合成偏好')).not.toBeInTheDocument();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(execute).toHaveBeenCalledTimes(1);
    unsubscribe();
  });
  it('keeps a confirmed withdrawal across stream Answer unmount and completed Answer remount', async () => {
    const registry = createMemoryReceiptRegistry();
    const commands: MemoryCommands = {
      supports: () => true,
      execute: vi.fn(async () => ({ fact_id: saved.fact_id, write_status: 'stopped' as const, revision: 2 })),
    };
    const first = render(<MemoryReceipts receipts={[saved]} commands={commands} registry={registry} />);
    await userEvent.click(screen.getByRole('button', { name: '撤销使用' }));
    await screen.findByText('已撤销，不会再提起');
    first.unmount();
    const second = render(<MemoryReceipts receipts={[{ ...saved }]} commands={commands} registry={registry} />);
    expect(screen.queryByText(/已记下/)).not.toBeInTheDocument();
    expect(screen.getByText('已撤销，不会再提起')).toBeVisible();
    second.rerender(
      <MemoryReceipts
        receipts={[{ ...saved, summary: '较新版本', revision: 3 }]}
        commands={commands}
        registry={registry}
      />,
    );
    expect(screen.getByText('已记下：较新版本')).toBeVisible();
    second.rerender(<MemoryReceipts receipts={[{ ...saved }]} commands={commands} registry={registry} />);
    expect(screen.getByText('已记下：较新版本')).toBeVisible();
  });
  it('keeps a confirmed proposal across remount and deduplicates fact/proposal aliases in late final', async () => {
    const registry = createMemoryReceiptRegistry();
    const pending: Receipt = {
      proposal_id: 'synthetic-proposal',
      write_status: 'pending_confirmation',
      summary: '合成待确认事项',
      revision: 1,
    };
    const commands: MemoryCommands = {
      supports: () => true,
      execute: vi.fn(async () => ({
        proposal_id: pending.proposal_id,
        fact_id: 'confirmed-fact',
        write_status: 'saved' as const,
        revision: 2,
      })),
    };
    const first = render(<MemoryReceipts receipts={[pending]} commands={commands} registry={registry} />);
    await userEvent.click(screen.getByRole('button', { name: '记住' }));
    await screen.findByText('已记下：合成待确认事项');
    first.unmount();
    render(
      <MemoryReceipts
        receipts={[{ ...pending }, { fact_id: 'confirmed-fact', write_status: 'saved', summary: '', revision: 1 }]}
        commands={commands}
        registry={registry}
      />,
    );
    expect(screen.queryByRole('button', { name: '记住' })).not.toBeInTheDocument();
    expect(screen.getAllByText('已记下：合成待确认事项')).toHaveLength(1);
  });
  it('ignores a registry captured under a different login namespace', async () => {
    useAuth.getState().setToken('synthetic-owner-A');
    const registry = createMemoryReceiptRegistry();
    const commands: MemoryCommands = {
      supports: () => true,
      execute: vi.fn(async () => ({ fact_id: saved.fact_id, write_status: 'stopped' as const, revision: 2 })),
    };
    const first = render(<MemoryReceipts receipts={[saved]} commands={commands} registry={registry} />);
    await userEvent.click(screen.getByRole('button', { name: '撤销使用' }));
    await screen.findByText('已撤销，不会再提起');
    first.unmount();
    useAuth.getState().setToken('synthetic-owner-B');
    render(
      <MemoryReceipts receipts={[{ ...saved, summary: 'B 的合成偏好' }]} commands={commands} registry={registry} />,
    );
    expect(screen.getByText('已记下：B 的合成偏好')).toBeVisible();
    expect(screen.queryByText('已撤销，不会再提起')).not.toBeInTheDocument();
  });
});
