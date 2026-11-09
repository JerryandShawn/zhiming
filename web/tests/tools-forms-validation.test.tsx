import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import WindowSearchPage from '../src/tools/WindowSearchPage';
import SynastryPage from '../src/tools/SynastryPage';
import { synastryKey } from '../src/tools/port';
import type { SynastryQuery } from '../src/tools/types';
import { countedTools } from './tools-form-test-fixtures';

afterEach(() => vi.unstubAllGlobals());
const windowSubmit = () => screen.getByRole('button', { name: '查看当前样例条件' });
const synastrySubmit = () => screen.getByRole('button', { name: '查看已确认的样例' });
const checkSynastry = () => screen.getByRole('button', { name: '核对查询条件' });
const consentA = () => screen.getByRole('checkbox', { name: '允许本次展示A方合成盘面' });
const consentB = () => screen.getByRole('checkbox', { name: '允许本次展示B方合成盘面' });
async function approve() {
  await userEvent.click(consentA());
  await userEvent.click(consentB());
}
async function choose(label: string, name: string) {
  await userEvent.click(screen.getByRole('combobox', { name: label }));
  await userEvent.click(screen.getByRole('option', { name }));
}
function expectIssue(control: HTMLElement, message: RegExp) {
  expect(control).toHaveAttribute('aria-invalid', 'true');
  const ids = (control.getAttribute('aria-describedby') ?? '').trim().split(/\s+/).filter(Boolean);
  expect(ids.length).toBeGreaterThan(0);
  expect(new Set(ids).size).toBe(ids.length);
  const nodes = ids.map((id) => document.getElementById(id));
  for (const node of nodes) expect(node).toBeInTheDocument();
  expect(nodes.some((node) => message.test(node?.textContent ?? ''))).toBe(true);
}
function expectNoFieldIssue(container: HTMLElement) {
  expect(container.querySelector('[aria-invalid="true"]')).not.toBeInTheDocument();
}

describe('window form field errors preserve drafts and revoke old evidence', () => {
  it('focuses the first invalid field, links each error, and performs zero reads for missing dates', async () => {
    const controlled = countedTools();
    render(<WindowSearchPage port={controlled.port} />);
    const start = screen.getByLabelText('起始日期（北京时间）'),
      end = screen.getByLabelText('结束日期（含当日）');
    fireEvent.change(start, { target: { value: '' } });
    fireEvent.change(end, { target: { value: '' } });
    await userEvent.click(windowSubmit());
    await waitFor(() => expect(start).toHaveFocus());
    expectIssue(start, /请填写日期/);
    expectIssue(end, /请填写日期/);
    await userEvent.click(screen.getByRole('link', { name: '结束日期：请填写日期。' }));
    expect(end).toHaveFocus();
    await userEvent.click(screen.getByRole('link', { name: '起始日期：请填写日期。' }));
    expect(start).toHaveFocus();
    expect(controlled.windowReads).not.toHaveBeenCalled();
    expect(controlled.synastryReads).not.toHaveBeenCalled();
    expect(start).toHaveValue('');
    expect(end).toHaveValue('');
  });

  it('withdraws a ready result before invalid submission and retains both corrected date drafts', async () => {
    const controlled = countedTools();
    const { container } = render(<WindowSearchPage port={controlled.port} />);
    await userEvent.click(windowSubmit());
    await screen.findByRole('heading', { name: '整个区间的项目排序' });
    const reference = controlled.windows[0].evidence[0].ref;
    expect(controlled.port.resolveEvidence(reference)).toBeDefined();
    const start = screen.getByLabelText('起始日期（北京时间）'),
      end = screen.getByLabelText('结束日期（含当日）');
    fireEvent.change(start, { target: { value: '2026-10-25' } });
    fireEvent.change(end, { target: { value: '2026-10-24' } });
    expect(container.querySelector('[data-tool-document]')).not.toBeInTheDocument();
    expect(controlled.port.resolveEvidence(reference)).toBeUndefined();
    await userEvent.click(windowSubmit());
    await waitFor(() => expect(end).toHaveFocus());
    expectIssue(end, /不能早于起始日期/);
    expect(controlled.windowReads).toHaveBeenCalledTimes(1);
    expect(start).toHaveValue('2026-10-25');
    expect(end).toHaveValue('2026-10-24');
    fireEvent.change(end, { target: { value: '2026-10-26' } });
    expect(start).toHaveValue('2026-10-25');
    await userEvent.click(windowSubmit());
    await waitFor(() => expect(controlled.windowReads).toHaveBeenCalledTimes(2));
    expectNoFieldIssue(container);
    expect(controlled.windowReads.mock.calls[1][0]).toEqual({
      purpose: '签约',
      startDate: '2026-10-25',
      endDate: '2026-10-26',
      offset: 0,
      limit: 31,
    });
    expect(container.querySelector('[data-tool-document]')).not.toBeInTheDocument();
    expect(controlled.port.resolveEvidence(reference)).toBeUndefined();
    expect(start).toHaveValue('2026-10-25');
    expect(end).toHaveValue('2026-10-26');
  });

  it('treats a valid unpublished purpose as sample unavailability rather than a red field error', async () => {
    const controlled = countedTools();
    const { container } = render(<WindowSearchPage port={controlled.port} />);
    await choose('用途', '搬家');
    await userEvent.click(windowSubmit());
    await waitFor(() =>
      expect(screen.getAllByRole('status').some((node) => /没有|无样例|尚无/.test(node.textContent ?? ''))).toBe(true),
    );
    expectNoFieldIssue(container);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(controlled.windowReads).toHaveBeenCalledTimes(1);
    expect(controlled.windowReads.mock.calls[0][0]).toMatchObject({ purpose: '搬家' });
    expect(container.querySelector('[data-tool-document]')).not.toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '用途' })).toHaveTextContent('搬家');
  });

  it('retries the exact current projected query after a transient failure without exporting WindowChoice.summary', async () => {
    const controlled = countedTools({ failWindow: 1 });
    render(<WindowSearchPage port={controlled.port} />);
    await userEvent.click(windowSubmit());
    await screen.findByRole('alert');
    const expected = { purpose: '签约', startDate: '2026-10-21', endDate: '2026-10-27', offset: 0, limit: 31 };
    expect(controlled.windowReads.mock.calls[0][0]).toEqual(expected);
    await userEvent.click(screen.getByRole('button', { name: '用当前条件重试' }));
    await screen.findByRole('heading', { name: '整个区间的项目排序' });
    expect(controlled.windowReads).toHaveBeenCalledTimes(2);
    expect(controlled.windowReads.mock.calls[1][0]).toEqual(expected);
    expect(controlled.windowReads.mock.calls[1][0]).not.toHaveProperty('summary');
    expect(screen.getByLabelText('起始日期（北京时间）')).toHaveValue('2026-10-21');
    expect(screen.getByLabelText('结束日期（含当日）')).toHaveValue('2026-10-27');
  });
});

describe('synastry form validation stays separate from fresh display consent', () => {
  it('lets an unconfirmed user check invalid fields, focuses the first error, and never reads the port', async () => {
    const controlled = countedTools();
    render(<SynastryPage port={controlled.port} />);
    const date = screen.getByLabelText('核对日期（北京时间）'),
      orb = screen.getByLabelText('统一相位容许度（度）');
    fireEvent.change(date, { target: { value: '' } });
    fireEvent.change(orb, { target: { value: '六' } });
    expect(synastrySubmit()).toBeDisabled();
    await userEvent.click(checkSynastry());
    await waitFor(() => expect(date).toHaveFocus());
    expectIssue(date, /请填写日期/);
    expectIssue(orb, /0至10度/);
    expect(date).toHaveValue('');
    expect(orb).toHaveValue('六');
    expect(controlled.synastryReads).not.toHaveBeenCalled();
    expect(consentA()).not.toBeChecked();
    expect(consentB()).not.toBeChecked();
  });

  it('associates duplicate viewer objects with B and focuses its accessible selection control', async () => {
    const controlled = countedTools();
    render(<SynastryPage port={controlled.port} />);
    await choose('B 方合成对象', '阿远（合成）');
    await userEvent.click(checkSynastry());
    const b = screen.getByRole('combobox', { name: 'B 方合成对象' });
    await waitFor(() => expect(b).toHaveFocus());
    expectIssue(b, /不同/);
    expect(screen.getByRole('combobox', { name: 'A 方合成对象' })).not.toHaveAttribute('aria-invalid', 'true');
    expect(controlled.synastryReads).not.toHaveBeenCalled();
  });

  it('clears a ready chart and its evidence on an empty orb, and never silently converts empty input to zero or six', async () => {
    const controlled = countedTools();
    const { container } = render(<SynastryPage port={controlled.port} />);
    await approve();
    await userEvent.click(synastrySubmit());
    await screen.findByRole('heading', { name: '两侧盘面各自保留' });
    const reference = controlled.synastry.evidence[0].ref;
    expect(controlled.port.resolveEvidence(reference)).toBeDefined();
    const orb = screen.getByLabelText('统一相位容许度（度）');
    fireEvent.change(orb, { target: { value: '' } });
    expect(container.querySelector('[data-tool-document]')).not.toBeInTheDocument();
    expect(controlled.port.resolveEvidence(reference)).toBeUndefined();
    expect(consentA()).not.toBeChecked();
    expect(consentB()).not.toBeChecked();
    await userEvent.click(checkSynastry());
    await waitFor(() => expect(orb).toHaveFocus());
    expectIssue(orb, /0至10度/);
    expect(orb).toHaveValue('');
    expect(controlled.synastryReads).toHaveBeenCalledTimes(1);
    expect(synastrySubmit()).toBeDisabled();
    fireEvent.change(orb, { target: { value: '6' } });
    await userEvent.click(checkSynastry());
    expect(orb).toHaveValue('6');
    expect(screen.getByLabelText('核对日期（北京时间）')).toHaveValue('2026-10-21');
    expectNoFieldIssue(container);
    expect(controlled.synastryReads).toHaveBeenCalledTimes(1);
    expect(synastrySubmit()).toBeDisabled();
    expect(consentA()).not.toBeChecked();
    expect(consentB()).not.toBeChecked();
  });

  it.each(['a', 'b', 'kind', 'date', 'orb'] as const)(
    'withdraws both confirmations when %s changes without doing a read',
    async (field) => {
      const controlled = countedTools();
      render(<SynastryPage port={controlled.port} />);
      await approve();
      expect(synastrySubmit()).toBeEnabled();
      if (field === 'a') await choose('A 方合成对象', '小禾（合成）');
      if (field === 'b') await choose('B 方合成对象', '阿远（合成）');
      if (field === 'kind') await choose('本次比较用途', '合作');
      if (field === 'date')
        fireEvent.change(screen.getByLabelText('核对日期（北京时间）'), { target: { value: '2026-10-22' } });
      if (field === 'orb') fireEvent.change(screen.getByLabelText('统一相位容许度（度）'), { target: { value: '0' } });
      expect(consentA()).not.toBeChecked();
      expect(consentB()).not.toBeChecked();
      expect(synastrySubmit()).toBeDisabled();
      expect(controlled.synastryReads).not.toHaveBeenCalled();
    },
  );

  it('keeps a valid zero orb and current summary when the port explicitly reports unavailable', async () => {
    const controlled = countedTools();
    const { container } = render(<SynastryPage port={controlled.port} />);
    const orb = screen.getByLabelText('统一相位容许度（度）');
    fireEvent.change(orb, { target: { value: '0' } });
    await approve();
    await userEvent.click(synastrySubmit());
    await waitFor(() =>
      expect(screen.getAllByRole('status').some((node) => /没有|无样例|尚无/.test(node.textContent ?? ''))).toBe(true),
    );
    expect(controlled.synastryReads).toHaveBeenCalledTimes(1);
    expect(controlled.synastryReads.mock.calls[0][0]).toMatchObject({ orbDegrees: 0 });
    expect(orb).toHaveValue('0');
    expectNoFieldIssue(container);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(container.querySelector('[data-tool-document]')).not.toBeInTheDocument();
    expect(controlled.port.resolveEvidence(controlled.synastry.evidence[0].ref)).toBeUndefined();
    expect(screen.getByText('0°', { exact: true })).toBeInTheDocument();
  });

  it('retries only the same query and fresh-confirmation key after a transient read failure', async () => {
    const controlled = countedTools({ failSynastry: 1 });
    render(<SynastryPage port={controlled.port} />);
    await approve();
    await userEvent.click(synastrySubmit());
    await screen.findByRole('alert');
    const expected: SynastryQuery = {
      a: 'ayuan',
      b: 'xiaohe',
      kind: 'romantic',
      asOfDate: '2026-10-21',
      orbDegrees: 6,
    };
    const consent = { queryKey: synastryKey(expected), a: true, b: true };
    expect(controlled.synastryReads.mock.calls[0].slice(0, 2)).toEqual([expected, consent]);
    expect(consentA()).toBeChecked();
    expect(consentB()).toBeChecked();
    await userEvent.click(screen.getByRole('button', { name: '用本次确认重试' }));
    await screen.findByRole('heading', { name: '两侧盘面各自保留' });
    expect(controlled.synastryReads).toHaveBeenCalledTimes(2);
    expect(controlled.synastryReads.mock.calls[1].slice(0, 2)).toEqual([expected, consent]);
  });

  it('does not send or persist validation drafts or valid-but-unavailable query checks', async () => {
    const controlled = countedTools();
    const fetch = vi.fn(() => Promise.reject(new Error('Unexpected HTTP request')));
    vi.stubGlobal('fetch', fetch);
    const setItem = vi.spyOn(Storage.prototype, 'setItem'),
      removeItem = vi.spyOn(Storage.prototype, 'removeItem');
    render(<SynastryPage port={controlled.port} />);
    fireEvent.change(screen.getByLabelText('统一相位容许度（度）'), { target: { value: '六' } });
    await userEvent.click(checkSynastry());
    fireEvent.change(screen.getByLabelText('统一相位容许度（度）'), { target: { value: '0' } });
    await userEvent.click(checkSynastry());
    expect(controlled.synastryReads).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
    expect(setItem).not.toHaveBeenCalled();
    expect(removeItem).not.toHaveBeenCalled();
  });
});
