import { Button } from '../components/ui/Controls';
import { firstWindowQuery, nextWindowQuery, previousWindowQuery, windowPageAnnouncement } from './pagination';
import type { WindowQuery, WindowSample } from './types';

export function WindowPagination({
  query,
  sample,
  busy,
  dirty,
  invalid,
  unavailable,
  onRead,
}: {
  query: WindowQuery;
  sample?: WindowSample;
  busy: boolean;
  dirty: boolean;
  invalid: boolean;
  unavailable: boolean;
  onRead: (query: WindowQuery) => void;
}) {
  const first = firstWindowQuery(query),
    previous = previousWindowQuery(query),
    next = nextWindowQuery(query, sample);
  const locked = busy || dirty || invalid;
  const status = busy
    ? `正在请求偏移${query.offset}、每页最多${query.limit}天的分页。`
    : dirty
      ? '每页天数尚未应用，请先应用后翻页。'
      : invalid
        ? '请先纠正查询条件，再请求分页。'
        : unavailable
          ? `偏移${query.offset}、每页最多${query.limit}天暂无已发布样例；未借用别页。`
          : windowPageAnnouncement(query, sample);
  return (
    <nav className="tool-pagination stack small" aria-label="择日分页">
      <h2>查看其他页</h2>
      <p className="meta" role="status" aria-live="polite" aria-atomic="true" data-window-page-status>
        {status}
      </p>
      <div className="row wrap">
        {(
          [
            { label: '首页', target: first },
            { label: '上一页', target: previous },
            { label: '下一页', target: next },
          ] as const
        ).map(({ label, target }) => (
          <Button
            key={label}
            variant="ghost"
            aria-disabled={locked || !target || undefined}
            onClick={() => {
              if (!locked && target) onRead(target);
            }}>
            {label}
          </Button>
        ))}
      </div>
      <p className="meta">翻页会请求完整页面，不在本机切割结果；“暂无样例”不表示这个区间没有条件。</p>
    </nav>
  );
}
