import { Button, Input } from '../components/ui/Controls';
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
export type WindowChangeSource = 'condition' | 'preset';

export function WindowSearchForm({
  query,
  compatible,
  issues,
  prefix,
  targets,
  change,
  limitDraft,
  limitPending,
  busy,
  editLimit,
  applyLimit,
}: {
  query: WindowQuery;
  compatible: readonly WindowChoice[];
  issues: readonly FieldIssue<WindowField>[];
  prefix: string;
  targets: InputTargets<WindowField>;
  change: (query: WindowQuery, source: WindowChangeSource) => void;
  limitDraft: string;
  limitPending: boolean;
  busy: boolean;
  editLimit: (raw: string) => void;
  applyLimit: () => void;
}) {
  const offsetErrors = issues.filter((issue) => issue.field === 'offset');
  const limitAria = inputAria('limit', issues, prefix);
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
          onChange={(purpose) => change({ ...query, purpose: purpose as Purpose, offset: 0 }, 'condition')}
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
            onChange={(event) => change({ ...query, [field]: event.target.value, offset: 0 }, 'condition')}
          />
          <ToolFieldIssues field={field} issues={issues} prefix={prefix} />
        </div>
      ))}
      <div className="field">
        <label htmlFor={targets.limit}>每页天数</label>
        <Input
          id={targets.limit}
          type="text"
          inputMode="numeric"
          value={limitDraft}
          required
          aria-invalid={limitAria['aria-invalid']}
          aria-describedby={[`${prefix}-limit-hint`, limitAria['aria-describedby']].filter(Boolean).join(' ')}
          onChange={(event) => editLimit(event.target.value)}
        />
        <p id={`${prefix}-limit-hint`} className="meta">
          填写1至31的整数；应用后从首页请求，空白不会自动补值。
        </p>
        <ToolFieldIssues field="limit" issues={issues} prefix={prefix} />
        <Button onClick={applyLimit} disabled={busy}>
          应用每页天数
        </Button>
        {limitPending && <p className="meta">当前输入尚未应用，翻页已暂停。</p>}
      </div>
      <div className="field">
        查看范围
        {compatible.length ? (
          <ToolSelect
            id={targets.offset}
            label="查看范围"
            value={windowKey(query)}
            options={compatible.map((item) => ({ value: windowKey(item), label: windowChoiceLabel(item) }))}
            aria-invalid={offsetErrors.length ? true : undefined}
            aria-describedby={offsetErrors.length ? `${prefix}-offset-error` : undefined}
            onChange={(value) => {
              const next = compatible.find((item) => windowKey(item) === value);
              if (next) change(next, 'preset');
            }}
          />
        ) : (
          <p
            id={targets.offset}
            tabIndex={-1}
            className="meta"
            aria-invalid={offsetErrors.length ? true : undefined}
            aria-describedby={offsetErrors.length ? `${prefix}-offset-error` : undefined}>
            当前请求偏移{query.offset}，每页最多{query.limit}天；此条件没有可选的已发布分页。
          </p>
        )}
        <ToolFieldIssues field="offset" issues={issues} prefix={prefix} />
      </div>
    </>
  );
}
