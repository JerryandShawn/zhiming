import { useState } from 'react';
import { Button, Input, Switch } from '../../components/ui/Controls';
import type { ReportKind, Schedule } from '../../live/types';
import type { ReportDraft, SettingsPort } from './types';
import { useSettingsCommand } from './useSettingsCommand';

const names: Record<ReportKind, string> = { daily: '晨报', weekly: '周报', monthly: '月报', quarterly: '季报' };
const draftOf = (item: Schedule): ReportDraft => ({
  enabled: item.enabled,
  time: item.time,
  weekday: item.weekday,
  day: item.day,
});
export function ReportForm({ item, port }: { item: Schedule; port: SettingsPort }) {
  const [draft, setDraft] = useState(() => draftOf(item)),
    [revision, setRevision] = useState(item.revision),
    [review, setReview] = useState(false);
  const operation = useSettingsCommand(port),
    name = names[item.kind];
  const blocked =
    !item.configured || !item.can_modify || Boolean(item.delivery_state?.sending || item.delivery_state?.uncertain);
  const locked = operation.busy || operation.hasPending || blocked;
  return (
    <article className="night-settings-report" data-report-kind={item.kind} data-revision={item.revision}>
      <h3>{name}</h3>
      <p className="meta">
        {item.enabled ? '已启用' : '已暂停'} · 保存版本 {item.revision}
      </p>
      <form
        className="stack small"
        onSubmit={(event) => {
          event.preventDefault();
          if (blocked) return;
          void operation
            .run(
              {
                type: 'report-save',
                kind: item.kind,
                expectedRevision: revision,
                requestId: crypto.randomUUID(),
                draft: { ...draft },
              },
              (receipt, command) => {
                if (command.type !== 'report-save') return false;
                const result = receipt.report;
                return (
                  receipt.write_status === 'saved' &&
                  result?.kind === command.kind &&
                  result.revision === receipt.revision &&
                  result.enabled === command.draft.enabled &&
                  result.time === command.draft.time &&
                  result.receipt?.id === command.kind &&
                  result.receipt.kind === 'report_schedule' &&
                  result.receipt.write_status === 'saved' &&
                  result.receipt.revision === result.revision &&
                  (command.kind !== 'weekly' || result.weekday === command.draft.weekday) &&
                  (!['monthly', 'quarterly'].includes(command.kind) || result.day === command.draft.day)
                );
              },
            )
            .then((receipt) => {
              if (receipt?.report) {
                setRevision(receipt.report.revision);
                setDraft(draftOf(receipt.report));
              }
            });
        }}>
        <fieldset disabled={locked} className="stack small">
          <div className="setting-row">
            <span>启用{name}</span>
            <Switch
              label={`启用${name}`}
              checked={draft.enabled}
              disabled={locked}
              onChange={(enabled) => setDraft((old) => ({ ...old, enabled }))}
            />
          </div>
          <label className="field">
            {name}发送时间
            <Input
              type="time"
              aria-label={`${name}发送时间`}
              value={draft.time}
              onChange={(event) => setDraft((old) => ({ ...old, time: event.target.value }))}
            />
          </label>
          {item.kind === 'weekly' && (
            <label className="field">
              周报星期
              <select
                className="input"
                aria-label="周报星期"
                value={draft.weekday}
                onChange={(event) => setDraft((old) => ({ ...old, weekday: Number(event.target.value) }))}>
                {['一', '二', '三', '四', '五', '六', '日'].map((day, index) => (
                  <option key={day} value={index + 1}>
                    星期{day}
                  </option>
                ))}
              </select>
            </label>
          )}
          {['monthly', 'quarterly'].includes(item.kind) && (
            <label className="field">
              {name}日期
              <select
                className="input"
                aria-label={`${name}日期`}
                value={draft.day}
                onChange={(event) =>
                  setDraft((old) => ({
                    ...old,
                    day: event.target.value === 'last' ? 'last' : Number(event.target.value),
                  }))
                }>
                {Array.from({ length: 28 }, (_, index) => (
                  <option key={index} value={index + 1}>
                    {index + 1} 日
                  </option>
                ))}
                <option value="last">月末（最后一天）</option>
              </select>
            </label>
          )}
        </fieldset>
        {item.kind === 'quarterly' && <p className="meta">仅在 1、4、7、10 月发送；月末为这些月份的最后一天。</p>}
        <p className="meta settings-preview">
          已保存预览 · 准备：
          {item.next_prepare || item.preview_prepare || (item.enabled ? '本地示例不安排真实投递' : '已暂停')}
          <br />
          发送：{item.next_delivery || item.preview_delivery || (item.enabled ? '本地示例不安排真实投递' : '已暂停')}
        </p>
        {blocked && <p className="meta">当前渠道或投递状态不允许修改，请先核对已保存状态。</p>}
        {operation.error && <p role="alert">{operation.error}</p>}
        {operation.saved && (
          <p role="status" className="settings-feedback">
            已保存{name}设置（本地演示）。
          </p>
        )}
        {operation.conflict && (
          <div className="stack small">
            <Button onClick={() => setReview(true)}>读取当前{name}设置</Button>
            {review && (
              <div className="settings-preview">
                <p>
                  {item.enabled ? '已启用' : '已暂停'} · {item.time} · 版本 {item.revision}
                </p>
                <Button
                  onClick={() => {
                    setRevision(item.revision);
                    operation.reset();
                    setReview(false);
                  }}>
                  已核对，保留草稿继续
                </Button>
              </div>
            )}
          </div>
        )}
        <div className="row wrap">
          <Button type="submit" loading={operation.busy} disabled={operation.conflict || blocked}>
            {operation.hasPending ? '重试原报告设置' : `保存${name}设置`}
          </Button>
          <Button
            variant="ghost"
            disabled={operation.busy || operation.hasPending}
            onClick={() => {
              setDraft(draftOf(item));
              setRevision(item.revision);
              operation.reset();
            }}>
            取消修改
          </Button>
        </div>
      </form>
    </article>
  );
}
