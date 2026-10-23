import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MemoryReceipts } from '../src/chat/interactions/MemoryReceipts';
import type { Receipt } from '../src/chat/types';

const first: Receipt = { fact_id: 'landmark-1', write_status: 'saved', summary: '合成偏好', revision: 1 };

describe('memory cards remain reachable without duplicate landmarks', () => {
  it('preserves the existing single-card region and action', () => {
    render(<MemoryReceipts receipts={[first]} />);
    expect(screen.getByRole('region', { name: '记忆记录' })).toHaveTextContent(first.summary);
    expect(screen.getByRole('button', { name: '撤销使用' })).toBeInTheDocument();
  });
  it('uses groups for two saved cards even when their summaries are identical', async () => {
    render(<MemoryReceipts receipts={[first, { ...first, fact_id: 'landmark-2' }]} />);
    await userEvent.click(screen.getByText('记下了 2 件事'));
    expect(screen.getAllByRole('group', { name: '记忆记录' })).toHaveLength(2);
    expect(screen.queryByRole('region', { name: '记忆记录' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '撤销使用' })).toHaveLength(2);
  });
  it('also avoids duplicate pending landmarks without dropping either proposal', () => {
    render(
      <MemoryReceipts
        receipts={['one', 'two'].map((id) => ({
          proposal_id: id,
          write_status: 'pending_confirmation',
          summary: '合成待确认',
          revision: 1,
        }))}
      />,
    );
    expect(screen.getAllByRole('group', { name: '待确认记忆' })).toHaveLength(2);
    expect(screen.queryByRole('region', { name: '待确认记忆' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '记住' })).toHaveLength(2);
  });
  it('does not count an undone status as a second visible card', () => {
    render(<MemoryReceipts receipts={[first, { ...first, fact_id: 'landmark-stopped', write_status: 'stopped' }]} />);
    expect(screen.getByRole('region', { name: '记忆记录' })).toHaveTextContent(first.summary);
    expect(screen.getByRole('status')).toHaveTextContent('已撤销，不会再提起');
  });
});
