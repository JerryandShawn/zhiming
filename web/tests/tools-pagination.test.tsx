import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import {
  firstWindowQuery,
  matchesWindowQuery,
  nextWindowOffset,
  nextWindowQuery,
  parseWindowLimitDraft,
  previousWindowQuery,
  windowPageAnnouncement,
} from '../src/tools/pagination';
import { WindowPagination } from '../src/tools/WindowPagination';
import { validateWindowInput } from '../src/tools/inputValidation';
import type { WindowQuery, WindowSample } from '../src/tools/types';
import { countedTools } from './tools-form-test-fixtures';
import {
  emptyQuery,
  fullQuery,
  middleQuery,
  nextUnpublishedQuery,
  previousUnpublishedQuery,
} from './tools-pagination-test-fixtures';

describe('pagination follows response metadata and requested arithmetic', () => {
  it('retains the three real published page responses, including next_offset 6 rather than nearby preset 7', () => {
    const { windows } = countedTools();
    const [full, middle, empty] = windows;
    expect(windows.map((sample) => sample.data.pagination)).toEqual([
      { total: 7, offset: 0, limit: 31, returned: 7, has_more: false, next_offset: null },
      { total: 7, offset: 3, limit: 3, returned: 3, has_more: true, next_offset: 6 },
      { total: 7, offset: 7, limit: 3, returned: 0, has_more: false, next_offset: null },
    ]);
    expect(nextWindowQuery(fullQuery, full)).toBeUndefined();
    expect(nextWindowQuery(middleQuery, middle)).toEqual(nextUnpublishedQuery);
    expect(nextWindowQuery(emptyQuery, empty)).toBeUndefined();
    expect(previousWindowQuery(middleQuery)).toEqual(previousUnpublishedQuery);
    expect(previousWindowQuery(emptyQuery)).toEqual({ ...emptyQuery, offset: 4 });
    expect(firstWindowQuery(middleQuery)).toEqual(previousUnpublishedQuery);
    expect(firstWindowQuery(fullQuery)).toBeUndefined();
  });

  it('refuses a response for a different purpose, date, offset or limit without using its next pointer', () => {
    const middle = countedTools().windows[1];
    expect(matchesWindowQuery(middleQuery, middle)).toBe(true);
    for (const change of [
      { purpose: '搬家' as const },
      { startDate: '2026-10-20' },
      { endDate: '2026-10-28' },
      { offset: 0 },
      { limit: 31 },
    ]) {
      const query = { ...middleQuery, ...change };
      expect(matchesWindowQuery(query, middle)).toBe(false);
      expect(nextWindowQuery(query, middle)).toBeUndefined();
      expect(windowPageAnnouncement(query, middle)).toMatch(/尚未取得当前条件/);
    }
    expect(nextWindowQuery(middleQuery)).toBeUndefined();
  });

  it('tests a 32-day 31/1/0 sequence as pagination metadata only, without inventing a P8 sample or evidence', () => {
    const query: WindowQuery = {
      purpose: '签约',
      startDate: '2028-01-01',
      endDate: '2028-02-01',
      offset: 0,
      limit: 31,
    };
    const first: WindowSample['data']['pagination'] = {
      total: 32,
      offset: 0,
      limit: 31,
      returned: 31,
      has_more: true,
      next_offset: 31,
    };
    const last: WindowSample['data']['pagination'] = {
      total: 32,
      offset: 31,
      limit: 31,
      returned: 1,
      has_more: false,
      next_offset: null,
    };
    const empty: WindowSample['data']['pagination'] = {
      total: 32,
      offset: 62,
      limit: 31,
      returned: 0,
      has_more: false,
      next_offset: null,
    };
    expect(nextWindowOffset(query, first)).toBe(31);
    expect(nextWindowOffset({ ...query, offset: 31 }, last)).toBeUndefined();
    expect(nextWindowOffset({ ...query, offset: 62 }, empty)).toBeUndefined();
    expect(previousWindowQuery({ ...query, offset: 62 })).toEqual({ ...query, offset: 31 });
    expect(previousWindowQuery({ ...query, offset: 31 })).toEqual(query);
    // There is deliberately no WindowSample, provenance, document_id or source
    // modification for this unpublished 2028 range.
  });

  it('requires an advancing integer next offset and matching page coordinates', () => {
    const page = countedTools().windows[1].data.pagination;
    for (const change of [
      { has_more: false },
      { next_offset: null },
      { next_offset: 3 },
      { next_offset: 2 },
      { next_offset: 3.5 },
      { next_offset: Infinity },
      { next_offset: NaN },
      { offset: 0 },
      { limit: 31 },
    ])
      expect(nextWindowOffset(middleQuery, { ...page, ...change })).toBeUndefined();
    expect(nextWindowOffset(middleQuery)).toBeUndefined();
  });

  it.each(['', ' ', '0', '32', '1.5', '3\n', '3\r\n'])(
    'keeps raw page size %j invalid through the centralized validator',
    (raw) => {
      const value = validateWindowInput({ ...middleQuery, limit: parseWindowLimitDraft(raw) });
      expect(value).toMatchObject({ status: 'invalid', issues: [expect.objectContaining({ field: 'limit' })] });
    },
  );

  it.each(['1', '31'])('accepts supported page size %s without adding an alternative default', (raw) => {
    expect(validateWindowInput({ ...middleQuery, limit: parseWindowLimitDraft(raw) })).toMatchObject({
      status: 'valid',
      query: { limit: Number(raw) },
    });
  });

  it('does not repeat a previous request when subtraction cannot advance a permitted large integer offset', async () => {
    const query: WindowQuery = { ...middleQuery, offset: 1e20 };
    expect(Number.isInteger(query.offset)).toBe(true);
    expect(validateWindowInput(query).status).toBe('valid');
    expect(previousWindowQuery(query)).toBeUndefined();
    const onRead = vi.fn();
    render(<WindowPagination query={query} busy={false} dirty={false} invalid={false} unavailable onRead={onRead} />);
    const previous = screen.getByRole('button', { name: '上一页' });
    expect(previous).toHaveAttribute('aria-disabled', 'true');
    await userEvent.click(previous);
    await userEvent.keyboard('{Enter}');
    expect(onRead).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: '首页' }));
    expect(onRead).toHaveBeenCalledTimes(1);
    expect(onRead).toHaveBeenCalledWith({ ...query, offset: 0 });
  });

  it('describes a genuine empty response without implying the whole range has no conditions', () => {
    const empty = countedTools().windows[2];
    const text = windowPageAnnouncement(emptyQuery, empty);
    expect(text).toContain('当前返回0条');
    expect(text).toContain('区间共7天');
    expect(text).toContain('末尾空页');
    expect(text).toContain('不代表整个区间没有条件');
  });
});
