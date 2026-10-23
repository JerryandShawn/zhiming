import type { WindowQuery, WindowSample } from './types';

type Page = WindowSample['data']['pagination'];
const validNumbers = (query: WindowQuery) =>
  Number.isInteger(query.offset) &&
  query.offset >= 0 &&
  Number.isInteger(query.limit) &&
  query.limit >= 1 &&
  query.limit <= 31;

/** Parse only the page-size editor; bounds remain the centralized query validator's responsibility. */
export const parseWindowLimitDraft = (raw: string) => (/^[0-9]+$/.test(raw) ? Number(raw) : Number.NaN);

export function firstWindowQuery(query: WindowQuery): WindowQuery | undefined {
  return validNumbers(query) && query.offset > 0 ? { ...query, offset: 0 } : undefined;
}
export function previousWindowQuery(query: WindowQuery): WindowQuery | undefined {
  if (!validNumbers(query) || query.offset === 0) return;
  const offset = Math.max(0, query.offset - query.limit);
  // Large Number integers are permitted by the viewer, but subtraction must actually advance.
  return offset < query.offset ? { ...query, offset } : undefined;
}
export function nextWindowOffset(query: WindowQuery, page?: Page): number | undefined {
  if (
    !validNumbers(query) ||
    !page ||
    page.offset !== query.offset ||
    page.limit !== query.limit ||
    page.has_more !== true ||
    typeof page.next_offset !== 'number' ||
    !Number.isInteger(page.next_offset) ||
    page.next_offset <= query.offset
  )
    return;
  return page.next_offset;
}
export function matchesWindowQuery(query: WindowQuery, sample: WindowSample) {
  const data = sample.data;
  return (
    data.purpose === query.purpose &&
    data.range.start_date === query.startDate &&
    data.range.end_date === query.endDate &&
    data.pagination.offset === query.offset &&
    data.pagination.limit === query.limit
  );
}
export function nextWindowQuery(query: WindowQuery, sample?: WindowSample): WindowQuery | undefined {
  if (!sample || !matchesWindowQuery(query, sample)) return;
  const offset = nextWindowOffset(query, sample.data.pagination);
  return offset === undefined ? undefined : { ...query, offset };
}
export function windowPageAnnouncement(query: WindowQuery, sample?: WindowSample) {
  if (!sample || !matchesWindowQuery(query, sample)) return '尚未取得当前条件的分页响应。';
  const { candidates, pagination: page } = sample.data;
  const ranks = candidates.length
    ? `；第${candidates[0].rank}${candidates.length > 1 ? `–${candidates.at(-1)!.rank}` : ''}名`
    : '；当前是末尾空页，不代表整个区间没有条件';
  return `当前返回${page.returned}条，区间共${page.total}天${ranks}。`;
}
