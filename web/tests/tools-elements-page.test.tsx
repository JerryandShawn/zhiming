import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import SynastryPage from '../src/tools/SynastryPage';
import { countedTools } from './tools-form-test-fixtures';

const approve = async () => {
  await userEvent.click(screen.getByRole('checkbox', { name: '允许本次展示A方合成盘面' }));
  await userEvent.click(screen.getByRole('checkbox', { name: '允许本次展示B方合成盘面' }));
};
const read = () => userEvent.click(screen.getByRole('button', { name: '查看已确认的样例' }));
async function choose(label: string, option: string) {
  await userEvent.click(screen.getByRole('combobox', { name: label }));
  await userEvent.click(screen.getByRole('option', { name: option }));
}

describe('actual SynastryPage and unmodified published sample', () => {
  it('shows counts only after both confirmations, preserving four pillars and actual exposed-stem candidates', async () => {
    const controlled = countedTools(),
      original = structuredClone(controlled.synastry);
    const { container } = render(<SynastryPage port={controlled.port} />);
    expect(screen.queryByRole('heading', { name: '表层五行计数' })).not.toBeInTheDocument();
    await approve();
    expect(screen.queryByRole('region', { name: '双方表层五行计数' })).not.toBeInTheDocument();
    await read();
    const counts = await screen.findByRole('region', { name: '双方表层五行计数' });
    expect(counts).toBeVisible();
    expect(container.querySelector('[data-tool-document]')).toHaveAttribute(
      'data-tool-document',
      controlled.synastry.document_id,
    );
    for (const side of ['a', 'b'] as const) {
      const chart = screen.getByRole('region', { name: `${side.toUpperCase()}方盘面` });
      expect([...chart.querySelectorAll('.tool-pillars dd')].map((node) => node.textContent)).toEqual(
        Object.values(original.data.bazi[side === 'a' ? 'pillars_a' : 'pillars_b']),
      );
    }
    const summary = screen.getByText('表层元素与三种候选路径', { selector: 'summary' });
    await userEvent.click(summary);
    const candidates = summary.closest('details')!;
    for (const expected of original.data.bazi.useful_complement) {
      const text = `${expected.recipient.toUpperCase()} 方 · ${expected.method}候选`;
      const item = [...candidates.querySelectorAll('li')].find((node) => node.textContent?.startsWith(text));
      expect(item).toBeInTheDocument();
      expect(item).toHaveTextContent(`对方透干 ${expected.other_exposed_stems.join('、') || '无'}`);
    }
    expect(controlled.synastry).toEqual(original);
    expect(controlled.synastryReads).toHaveBeenCalledTimes(1);
  });

  it('keeps the complete evidence catalog scoped to its real document and revokes everything on cancellation', async () => {
    const controlled = countedTools();
    const { container } = render(<SynastryPage port={controlled.port} />);
    await approve();
    await read();
    await screen.findByRole('region', { name: '双方表层五行计数' });
    const own = controlled.synastry.evidence[0],
      foreign = controlled.windows[0].evidence[0];
    expect(controlled.port.resolveEvidence(own.ref)?.claim_id).toBe(own.claim_id);
    expect(controlled.port.resolveEvidence(foreign.ref)).toBeUndefined();
    const summary = screen.getByText('本结果的公开依据', { selector: 'summary' });
    await userEvent.click(summary);
    const catalog = summary.closest('details')!;
    expect(catalog.querySelectorAll('.tool-evidence-row')).toHaveLength(controlled.synastry.evidence.length);
    const entry = catalog.querySelector('.tool-evidence-row')! as HTMLElement;
    await userEvent.click(within(entry).getByRole('button', { name: `依据〔${own.ref.alias}〕` }));
    const dialog = await screen.findByRole('dialog', { name: `本结果依据〔${own.ref.alias}〕` });
    expect(dialog).toHaveTextContent(own.summary);
    expect(dialog).not.toHaveTextContent(foreign.summary);
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: '撤回本次展示' }));
    expect(screen.queryByRole('region', { name: '双方表层五行计数' })).not.toBeInTheDocument();
    expect(container.querySelector('[data-tool-document]')).not.toBeInTheDocument();
    expect(controlled.port.resolveEvidence(own.ref)).toBeUndefined();
    expect(screen.getByRole('checkbox', { name: '允许本次展示A方合成盘面' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: '允许本次展示B方合成盘面' })).not.toBeChecked();
  });

  it('does not reuse old counts or evidence for a valid unpublished relation kind', async () => {
    const controlled = countedTools();
    const { container } = render(<SynastryPage port={controlled.port} />);
    await approve();
    await read();
    await screen.findByRole('region', { name: '双方表层五行计数' });
    await choose('本次比较用途', '朋友相处');
    expect(screen.queryByRole('region', { name: '双方表层五行计数' })).not.toBeInTheDocument();
    expect(controlled.port.resolveEvidence(controlled.synastry.evidence[0].ref)).toBeUndefined();
    expect(screen.getByRole('button', { name: '查看已确认的样例' })).toBeDisabled();
    await approve();
    await read();
    await waitFor(() => expect(container.querySelector('[data-published-state="unavailable"]')).toBeInTheDocument());
    expect(container.querySelector('[data-tool-document]')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '表层五行计数' })).not.toBeInTheDocument();
    expect(controlled.synastryReads.mock.calls[1][0]).toMatchObject({ kind: 'friendship' });
  });

  it('withdraws counts even for raw 6 to 6.0 and needs a newly confirmed read before redisplay', async () => {
    const controlled = countedTools();
    render(<SynastryPage port={controlled.port} />);
    await approve();
    await read();
    await screen.findByRole('region', { name: '双方表层五行计数' });
    fireEvent.change(screen.getByLabelText('统一相位容许度（度）'), { target: { value: '6.0' } });
    expect(screen.queryByRole('region', { name: '双方表层五行计数' })).not.toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: '允许本次展示A方合成盘面' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: '允许本次展示B方合成盘面' })).not.toBeChecked();
    await approve();
    expect(screen.queryByRole('region', { name: '双方表层五行计数' })).not.toBeInTheDocument();
    expect(controlled.synastryReads).toHaveBeenCalledTimes(1);
    await read();
    expect(await screen.findByRole('region', { name: '双方表层五行计数' })).toBeVisible();
    expect(controlled.synastryReads).toHaveBeenCalledTimes(2);
    expect(controlled.synastryReads.mock.calls[1][0]).toMatchObject({ orbDegrees: 6 });
  });
});
