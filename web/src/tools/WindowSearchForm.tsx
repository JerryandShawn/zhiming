import { Input } from '../components/ui/Controls';
import { purposes, windowKey } from './port';
import { ToolSelect } from './ToolSelect';
import { inputAria, ToolFieldIssues, type InputTargets } from './ToolInputFeedback';
import type { FieldIssue, WindowField } from './inputValidationTypes';
import type { Purpose, WindowChoice, WindowQuery } from './types';

export const windowChoiceLabel = ({ summary }: WindowChoice) =>
  !summary.returned
    ? '末尾空页'
    : summary.returned === summary.total
      ? `全部 ${summary.total} 天`
      : summary.first_rank === summary.last_rank
        ? `第 ${summary.first_rank} 名`
        : `第 ${summary.first_rank}–${summary.last_rank} 名`;

export function WindowSearchForm({
  query,
  compatible,
  issues,
  prefix,
  targets,
  change,
}: {
  query: WindowQuery;
  compatible: readonly WindowChoice[];
  issues: readonly FieldIssue<WindowField>[];
  prefix: string;
  targets: InputTargets<WindowField>;
  change: (query: WindowQuery) => void;
}) {
  const pageErrors = issues.filter((issue) => issue.field === 'offset' || issue.field === 'limit');
  return (
    <>
      <div className="field">
        用途
        <ToolSelect
          id={targets.purpose}
          label="用途"
          value={query.purpose}
          options={purposes.map((value) => ({ value, label: value }))}
          {...inputAria('purpose', issues, prefix)}
          onChange={(purpose) => change({ ...query, purpose: purpose as Purpose })}
        />
        <ToolFieldIssues field="purpose" issues={issues} prefix={prefix} />
      </div>
      {(['startDate', 'endDate'] as const).map((field) => (
        <div className="field" key={field}>
          <label htmlFor={targets[field]}>
            {field === 'startDate' ? '起始日期（北京时间）' : '结束日期（含当日）'}
          </label>
          <Input
            id={targets[field]}
            type="date"
            value={query[field]}
            required
            {...inputAria(field, issues, prefix)}
            onChange={(event) => change({ ...query, [field]: event.target.value })}
          />
          <ToolFieldIssues field={field} issues={issues} prefix={prefix} />
        </div>
      ))}
      <div className="field">
        查看范围
        {compatible.length ? (
          <ToolSelect
            id={targets.offset}
            label="查看范围"
            value={windowKey(query)}
            options={compatible.map((item) => ({ value: windowKey(item), label: windowChoiceLabel(item) }))}
            aria-invalid={pageErrors.length ? true : undefined}
            aria-describedby={pageErrors.length ? `${prefix}-pagination-error` : undefined}
            onChange={(value) => {
              const next = compatible.find((item) => windowKey(item) === value);
              if (next) change(next);
            }}
          />
        ) : (
          <p
            id={targets.offset}
            tabIndex={-1}
            className="meta"
            aria-invalid={pageErrors.length ? true : undefined}
            aria-describedby={pageErrors.length ? `${prefix}-pagination-error` : undefined}>
            当前请求偏移{query.offset}，每页最多{query.limit}天；此条件没有可选的已发布分页。
          </p>
        )}
        {pageErrors.length > 0 && (
          <p id={`${prefix}-pagination-error`} className="tool-field-error small-text">
            {pageErrors.map((issue) => issue.message).join(' ')}
          </p>
        )}
      </div>
    </>
  );
}
