import { useLayoutEffect } from 'react';
import type { FieldIssue, QuerySummary, WindowField, SynastryField } from './inputValidationTypes';

export const windowInputLabels: Record<WindowField | 'query', string> = {
  purpose: '用途',
  startDate: '起始日期',
  endDate: '结束日期',
  offset: '分页偏移',
  limit: '每页天数',
  query: '查询条件',
};
export const synastryInputLabels: Record<SynastryField | 'query', string> = {
  a: 'A方对象',
  b: 'B方对象',
  kind: '比较用途',
  asOfDate: '核对日期',
  orbDegrees: '相位容许度',
  query: '查询条件',
};

export type InputTargets<Field extends string> = Record<Field | 'query', string>;
export function inputAria<Field extends string>(field: Field, issues: readonly FieldIssue<Field>[], prefix: string) {
  const invalid = issues.some((issue) => issue.field === field);
  return {
    'aria-invalid': invalid || undefined,
    'aria-describedby': invalid ? `${prefix}-${field}-error` : undefined,
  } as const;
}
export function ToolFieldIssues<Field extends string>({
  field,
  issues,
  prefix,
}: {
  field: Field;
  issues: readonly FieldIssue<Field>[];
  prefix: string;
}) {
  const items = issues.filter((issue) => issue.field === field);
  return items.length ? (
    <p id={`${prefix}-${field}-error`} className="tool-field-error small-text">
      {items.map((issue) => issue.message).join(' ')}
    </p>
  ) : null;
}

export function ToolInputErrors<Field extends string>({
  issues,
  targets,
  prefix,
  labels,
}: {
  issues: readonly FieldIssue<Field>[];
  targets: InputTargets<Field>;
  prefix: string;
  labels: Record<Field | 'query', string>;
}) {
  useLayoutEffect(() => {
    if (issues.length) document.getElementById(targets[issues[0].field])?.focus({ preventScroll: false });
  }, [issues, targets]);
  if (!issues.length) return null;
  return (
    <div
      id={targets.query}
      className="tool-input-errors stack small"
      role="alert"
      tabIndex={-1}
      aria-labelledby={`${prefix}-errors-title`}>
      <h2 id={`${prefix}-errors-title`}>请先核对查询条件</h2>
      <ul>
        {issues.map((issue, index) => (
          <li key={`${issue.field}:${issue.code}:${index}`}>
            <a
              href={`#${targets[issue.field]}`}
              onClick={(event) => {
                event.preventDefault();
                document.getElementById(targets[issue.field])?.focus();
              }}>
              {labels[issue.field]}：{issue.message}
            </a>
          </li>
        ))}
      </ul>
      <p className="meta">尚未请求样例。已保留输入，可逐项改正后重新核对。</p>
    </div>
  );
}

export function ToolQuerySummary({ summary }: { summary: QuerySummary }) {
  return (
    <section className="tool-input-summary stack small" aria-label="本次查询条件">
      <h2>本次查询条件</h2>
      <dl className="tool-query-summary">
        {summary.map((item) => (
          <div key={item.id}>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>
      <p className="meta">仅核对这些查询字段的格式；不表示出生资料、归属、授权或计算结果已通过。</p>
    </section>
  );
}
