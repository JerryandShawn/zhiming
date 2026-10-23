import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import WindowSearchPage from '../src/tools/WindowSearchPage';
import { countedTools } from './tools-form-test-fixtures';
import {
  delayedWindowTools,
  emptyQuery,
  fullQuery,
  middleQuery,
  nextUnpublishedQuery,
  previousUnpublishedQuery,
} from './tools-pagination-test-fixtures';

const submit = () => screen.getByRole('button', { name: '查看当前样例条件' });
const pager = () => screen.getByRole('navigation', { name: '择日分页' });
const previous = () => within(pager()).getByRole('button', { name: '上一页' });
const next = () => within(pager()).getByRole('button', { name: '下一页' });
const first = () => within(pager()).getByRole('button', { name: '首页' });
const limit = () => screen.getByRole('textbox', { name: '每页天数' });
const applyLimit = () => screen.getByRole('button', { name: '应用每页天数' });
async function preset(name: string) {
  await userEvent.click(screen.getByRole('combobox', { name: '查看范围' }));
  await userEvent.click(screen.getByRole('option', { name }));
}
const hasResult = () => screen.findByRole('heading', { name: '整个区间的项目排序' });
const unavailable = () =>
  waitFor(() => expect(document.querySelector('[data-published-state="unavailable"]')).toBeInTheDocument());

describe('published window pagination never borrows a nearby sample', () => {
  it('retains every preset exact offset and limit and reads only after explicit submit', async () => {
    const controlled = countedTools();
    const { container } = render(<WindowSearchPage port={controlled.port} />);
    expect(controlled.windowReads).not.toHaveBeenCalled();
    await userEvent.click(submit());
    await hasResult();
    expect(controlled.windowReads.mock.calls[0][0]).toEqual(fullQuery);
    expect(limit()).toHaveValue('31');
    expect(next()).toHaveAttribute('aria-disabled', 'true');
    await preset('第 4–6 名');
    expect(controlled.windowReads).toHaveBeenCalledTimes(1);
    expect(container.querySelector('[data-tool-document]')).not.toBeInTheDocument();
    expect(limit()).toHaveValue('3');
    await userEvent.click(submit());
    await hasResult();
    expect(controlled.windowReads.mock.calls[1][0]).toEqual(middleQuery);
    await preset('末尾空页');
    expect(controlled.windowReads).toHaveBeenCalledTimes(2);
    expect(limit()).toHaveValue('3');
    await userEvent.click(submit());
    await screen.findByText('这已是末尾空页。');
    expect(controlled.windowReads.mock.calls[2][0]).toEqual(emptyQuery);
    expect(next()).toHaveAttribute('aria-disabled', 'true');
    for (const [query] of controlled.windowReads.mock.calls)
      expect(Object.keys(query).sort()).toEqual(['purpose', 'startDate', 'endDate', 'offset', 'limit'].sort());
  });

  it('Next reads the actual next_offset 6/3 and shows unavailable, revoking old evidence rather than jumping to the 7/3 preset', async () => {
    const controlled = countedTools();
    const { container } = render(<WindowSearchPage port={controlled.port} />);
    await preset('第 4–6 名');
    await userEvent.click(submit());
    await hasResult();
    const reference = controlled.windows.find((sample) => sample.data.pagination.offset === 3)!.evidence[0].ref;
    expect(controlled.port.resolveEvidence(reference)).toBeDefined();
    const focused = next();
    expect(focused).not.toHaveAttribute('aria-disabled', 'true');
    await userEvent.click(focused);
    await unavailable();
    expect(controlled.windowReads).toHaveBeenCalledTimes(2);
    expect(controlled.windowReads.mock.calls[1][0]).toEqual(nextUnpublishedQuery);
    expect(controlled.windowReads.mock.calls.some(([query]) => query.offset === 7)).toBe(false);
    expect(container.querySelector('[data-tool-document]')).not.toBeInTheDocument();
    expect(controlled.port.resolveEvidence(reference)).toBeUndefined();
    expect(next()).toBe(focused);
    expect(focused).toHaveFocus();
    expect(next()).toHaveAttribute('aria-disabled', 'true');
    expect(container.querySelector('[aria-invalid="true"]')).not.toBeInTheDocument();
  });

  it('Previous requests 0/3 without silently changing the limit to the 0/31 full preset', async () => {
    const controlled = countedTools();
    const { container } = render(<WindowSearchPage port={controlled.port} />);
    await preset('第 4–6 名');
    await userEvent.click(submit());
    await hasResult();
    const focused = previous();
    await userEvent.click(focused);
    await unavailable();
    expect(controlled.windowReads).toHaveBeenCalledTimes(2);
    expect(controlled.windowReads.mock.calls[1][0]).toEqual(previousUnpublishedQuery);
    expect(container.querySelector('[data-tool-document]')).not.toBeInTheDocument();
    expect(previous()).toBe(focused);
    expect(focused).toHaveFocus();
    expect(previous()).toHaveAttribute('aria-disabled', 'true');
    await userEvent.click(previous());
    await userEvent.click(first());
    expect(controlled.windowReads).toHaveBeenCalledTimes(2);
  });

  it('Previous from the 7/3 empty page means 4/3, never the available 3/3 preset', async () => {
    const controlled = countedTools();
    render(<WindowSearchPage port={controlled.port} />);
    await preset('末尾空页');
    await userEvent.click(submit());
    await screen.findByText('这已是末尾空页。');
    await userEvent.click(previous());
    await unavailable();
    expect(controlled.windowReads.mock.calls[1][0]).toEqual({ ...middleQuery, offset: 4 });
    expect(controlled.windowReads.mock.calls.some(([query]) => query.offset === 3)).toBe(false);
  });

  it.each(['date', 'purpose', 'limit'] as const)(
    'changing %s starts at offset zero and retains the new requested conditions',
    async (field) => {
      const controlled = countedTools();
      render(<WindowSearchPage port={controlled.port} />);
      await preset('第 4–6 名');
      expect(controlled.windowReads).not.toHaveBeenCalled();
      if (field === 'date') {
        fireEvent.change(screen.getByLabelText('结束日期（含当日）'), { target: { value: '2026-10-28' } });
        await userEvent.click(submit());
      } else if (field === 'purpose') {
        await userEvent.click(screen.getByRole('combobox', { name: '用途' }));
        await userEvent.click(screen.getByRole('option', { name: '面试' }));
        await userEvent.click(submit());
      } else {
        fireEvent.change(limit(), { target: { value: '1' } });
        await userEvent.click(applyLimit());
      }
      await unavailable();
      expect(controlled.windowReads).toHaveBeenCalledTimes(1);
      expect(controlled.windowReads.mock.calls[0][0]).toEqual({
        ...middleQuery,
        offset: 0,
        ...(field === 'date' ? { endDate: '2026-10-28' } : field === 'purpose' ? { purpose: '面试' } : { limit: 1 }),
      });
    },
  );

  it.each(['', '0', '32', '1.5'])(
    'invalid raw page size %j preserves the draft, blocks paging and performs no new read',
    async (raw) => {
      const controlled = countedTools();
      const { container } = render(<WindowSearchPage port={controlled.port} />);
      await preset('第 4–6 名');
      await userEvent.click(submit());
      await hasResult();
      const reference = controlled.windows.find((sample) => sample.data.pagination.offset === 3)!.evidence[0].ref;
      fireEvent.change(limit(), { target: { value: raw } });
      expect(controlled.port.resolveEvidence(reference)).toBeUndefined();
      expect(container.querySelector('[data-tool-document]')).not.toBeInTheDocument();
      await userEvent.click(applyLimit());
      expect(limit()).toHaveValue(raw);
      expect(limit()).toHaveAttribute('aria-invalid', 'true');
      await waitFor(() => expect(limit()).toHaveFocus());
      const linked = limit().getAttribute('aria-describedby') ?? '';
      expect(linked).not.toBe('');
      expect(
        linked.split(/\s+/).some((id) => /1至31|1–31|1-31/.test(document.getElementById(id)?.textContent ?? '')),
      ).toBe(true);
      for (const button of [first(), previous(), next()]) {
        expect(button).toHaveAttribute('aria-disabled', 'true');
        await userEvent.click(button);
      }
      expect(controlled.windowReads).toHaveBeenCalledTimes(1);
      await userEvent.click(submit());
      expect(controlled.windowReads).toHaveBeenCalledTimes(1);
      expect(limit()).toHaveValue(raw);
    },
  );

  it.each([1, 31])(
    'valid page size %s is applied explicitly at offset zero without coercing the limit',
    async (size) => {
      const controlled = countedTools();
      const { container } = render(<WindowSearchPage port={controlled.port} />);
      await preset('第 4–6 名');
      fireEvent.change(limit(), { target: { value: String(size) } });
      expect(controlled.windowReads).not.toHaveBeenCalled();
      await userEvent.click(applyLimit());
      await waitFor(() => expect(controlled.windowReads).toHaveBeenCalledTimes(1));
      expect(controlled.windowReads.mock.calls[0][0]).toEqual({ ...middleQuery, offset: 0, limit: size });
      expect(limit()).toHaveValue(String(size));
      expect(container.querySelector('[aria-invalid="true"]')).not.toBeInTheDocument();
      if (size === 31) await hasResult();
      else await unavailable();
    },
  );

  it('blocks all paging while busy and while a raw size edit has not been applied', async () => {
    const controlled = delayedWindowTools();
    render(<WindowSearchPage port={controlled.port} />);
    await preset('第 4–6 名');
    await userEvent.click(submit());
    expect(controlled.reads).toHaveLength(1);
    await act(async () => controlled.reads[0].settled);
    for (const button of [first(), previous(), next()]) {
      expect(button).toHaveAttribute('aria-disabled', 'true');
      await userEvent.click(button);
    }
    expect(controlled.reads).toHaveLength(1);
    await act(async () => controlled.reads[0].release());
    await hasResult();
    fireEvent.change(limit(), { target: { value: '1' } });
    for (const button of [first(), previous(), next()]) {
      expect(button).toHaveAttribute('aria-disabled', 'true');
      await userEvent.click(button);
    }
    expect(controlled.reads).toHaveLength(1);
  });

  it('ignores a completed old page delivered after a changed-date request returns unavailable', async () => {
    const controlled = delayedWindowTools();
    const { container } = render(<WindowSearchPage port={controlled.port} />);
    await preset('第 4–6 名');
    await userEvent.click(submit());
    const old = controlled.reads[0];
    await act(async () => old.settled);
    const reference = controlled.windows.find((sample) => sample.data.pagination.offset === 3)!.evidence[0].ref;
    expect(controlled.port.resolveEvidence(reference)).toBeDefined();
    fireEvent.change(screen.getByLabelText('结束日期（含当日）'), { target: { value: '2026-10-28' } });
    expect(controlled.port.resolveEvidence(reference)).toBeUndefined();
    await userEvent.click(submit());
    const current = controlled.reads[1];
    expect(current.query).toEqual({ ...middleQuery, endDate: '2026-10-28', offset: 0 });
    await act(async () => current.release());
    await unavailable();
    await act(async () => old.release());
    expect(old.signal?.aborted).toBe(true);
    expect(container.querySelector('[data-tool-document]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-published-state="unavailable"]')).toBeInTheDocument();
    expect(controlled.port.resolveEvidence(reference)).toBeUndefined();
    expect(screen.getByLabelText('结束日期（含当日）')).toHaveValue('2026-10-28');
    expect(limit()).toHaveValue('3');
  });
});
