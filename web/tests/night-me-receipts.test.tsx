import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MemoryReceipts } from '../src/chat/interactions/MemoryReceipts';
import { createMemoryReceiptRegistry } from '../src/chat/interactions/memoryProjection';
import type { Receipt } from '../src/chat/types';
import { createNightPort } from '../src/night/port';
import { useAboutMeReceipts } from '../src/night/useAboutMeReceipts';
import type { MemoryCommandReceipt } from '../src/chat/interactions/contracts';

describe('shared About Me and Chat projection', () => {
  it('ignores a late command confirmation after the stable parent has unmounted', async () => {
    const registry = createMemoryReceiptRegistry();
    const pending: Receipt = {
      proposal_id: 'late-proposal',
      write_status: 'pending_confirmation',
      summary: '合成待确认',
      revision: 1,
    };
    let resolve!: (value: MemoryCommandReceipt) => void;
    const result = new Promise<MemoryCommandReceipt>((done) => {
      resolve = done;
    });
    const view = render(
      <MemoryReceipts
        receipts={[pending]}
        registry={registry}
        commands={{ supports: () => true, execute: () => result }}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: '记住' }));
    view.unmount();
    await act(async () =>
      resolve({ proposal_id: pending.proposal_id, fact_id: 'late-fact', revision: 2, write_status: 'saved' }),
    );
    expect(registry.receipts.get('proposal:late-proposal')?.write_status).toBe('pending_confirmation');
    expect(registry.receipts.has('fact:late-fact')).toBe(false);
  });
  it.each(['remember', 'remember-category'] as const)(
    'keeps %s acknowledgement visible after the shared aggregate notifies',
    async (action) => {
      const port = createNightPort(),
        registry = createMemoryReceiptRegistry();
      const receipts: Receipt[] = [
        { fact_id: 'local-preference', write_status: 'saved', summary: '偏好先看简短结论（合成示例）' },
        {
          proposal_id: 'local-proposal',
          write_status: 'pending_confirmation',
          summary: '希望跟进一项健康安排（合成示例）',
          category: 'health',
          revision: 1,
        },
      ];
      function Harness() {
        useAboutMeReceipts(port.aboutMe, registry);
        return <MemoryReceipts receipts={receipts} commands={port.memory} registry={registry} />;
      }
      render(<Harness />);
      await userEvent.click(screen.getByRole('button', { name: action === 'remember' ? '记住' : '以后这类都记' }));
      const feedback = action === 'remember' ? '已记下这条信息。' : '已记下这条信息，并更新了本地同类记忆偏好。';
      expect(screen.getByText(feedback, { exact: true })).toBeVisible();
      expect(port.aboutMe.getSnapshot().memories.filter((item) => item.proposalId === 'local-proposal')).toHaveLength(
        1,
      );
    },
  );
});
