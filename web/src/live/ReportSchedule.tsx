import { useState } from 'react';
import { api } from '../api/client';
import { pendingPayload } from '../api/operations';
import { Button, Switch } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import { shownTime, useCommand } from './common';
import TimeField from './TimeField';
import type { ReportKind, Schedule, Schedules } from './types';

export const reportNames: Record<ReportKind, string> = {
  daily: '晨报',
  weekly: '周报',
  monthly: '月报',
  quarterly: '季报',
};
export function validSchedules(value: Schedules) {
  return (
    value.timezone === 'Asia/Shanghai' &&
    value.prepare_minutes === 15 &&
    Array.isArray(value.schedules) &&
    value.schedules.length === 4 &&
    new Set(value.schedules.map((item) => item.kind)).size === 4 &&
    value.schedules.every((item) => Object.hasOwn(reportNames, item.kind) && Number.isInteger(item.revision))
  );
}
type Draft = { enabled: boolean; time: string; weekday?: number; day?: number | 'last' };
export function schedulePayload(kind: ReportKind, revision: number, draft: Draft) {
  const payload: Record<string, unknown> = {
    kind,
    expected_revision: revision,
    enabled: draft.enabled,
    time: draft.time,
  };
  if (kind === 'weekly') payload.weekday = draft.weekday;
  if (kind === 'monthly' || kind === 'quarterly') payload.day = draft.day;
  return payload;
}
export function scheduleReceipt(value: Schedule, kind: ReportKind, expected?: Draft) {
  return (
    value.kind === kind &&
    value.receipt?.id === kind &&
    value.receipt.kind === 'report_schedule' &&
    value.receipt.write_status === 'saved' &&
    Number.isInteger(value.revision) &&
    value.receipt.revision === value.revision &&
    (!expected ||
      (value.enabled === expected.enabled &&
        value.time === expected.time &&
        (kind !== 'weekly' || value.weekday === expected.weekday) &&
        (!['monthly', 'quarterly'].includes(kind) || value.day === expected.day)))
  );
}
export default function ReportSchedule({ item }: { item: Schedule }) {
  const scope = `report-schedule:${item.kind}`;
  const pending = pendingPayload<Record<string, unknown>>(scope);
  const [current, setCurrent] = useState(item);
  const [version, setVersion] = useState(Number(pending?.expected_revision ?? item.revision));
  const [draft, setDraft] = useState<Draft>(() => ({
    enabled: pending ? pending.enabled === true : item.enabled,
    time: String(pending?.time ?? item.time),
    weekday: Number(pending?.weekday ?? item.weekday ?? 1),
    day: (pending?.day ?? item.day ?? 1) as number | 'last',
  }));
  const command = useCommand(scope);
  const disabled = !current.configured || !current.can_modify || command.busy || Boolean(pending);
  async function save() {
    const result = await command.submit<Schedule>(
      'PATCH',
      '/api/reports/schedules',
      schedulePayload(item.kind, version, draft),
      (value) => scheduleReceipt(value, item.kind, draft),
    );
    if (result) {
      setCurrent(result);
      setVersion(result.revision);
      setDraft({ enabled: result.enabled, time: result.time, weekday: result.weekday, day: result.day });
      command.setStatus(`已保存${reportNames[item.kind]}设置，版本 ${result.revision}。`);
    }
  }
  async function refresh() {
    try {
      const value = await api<Schedules>('/api/reports/schedules');
      if (!validSchedules(value)) throw new Error('报告设置不完整。');
      const latest = value.schedules.find((row) => row.kind === item.kind);
      if (!latest) throw new Error('报告类型缺失。');
      setCurrent(latest);
      setVersion(latest.revision);
      command.unlock();
    } catch {
      command.setStatus('最新设置读取失败，草稿仍保留。');
    }
  }
  const active = current.enabled && current.status === 'active';
  const update = (change: Partial<Draft>) => setDraft((old) => ({ ...old, ...change }));
  return (
    <section className="setting-group" data-report-kind={item.kind}>
      <h3>{reportNames[item.kind]}</h3>
      <p className="meta">
        {current.configured ? (current.enabled ? '已启用' : '已暂停') : '渠道尚未配置'} · 保存版本 {current.revision}
      </p>
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}>
        <fieldset disabled={disabled} className="stack">
          <div className="setting-row">
            <span>启用{reportNames[item.kind]}</span>
            <Switch
              label={`启用${reportNames[item.kind]}`}
              checked={draft.enabled}
              disabled={disabled}
              onChange={(enabled) => update({ enabled })}
            />
          </div>
          <TimeField
            label={`${reportNames[item.kind]}发送时间`}
            value={draft.time}
            onChange={(time) => update({ time })}
            disabled={disabled}
          />
          {item.kind === 'weekly' && (
            <Select
              label="周报星期"
              value={String(draft.weekday)}
              onChange={(value) => update({ weekday: Number(value) })}
              options={['一', '二', '三', '四', '五', '六', '日'].map((label, index) => ({
                value: String(index + 1),
                label: `星期${label}`,
              }))}
            />
          )}
          {(item.kind === 'monthly' || item.kind === 'quarterly') && (
            <Select
              label={`${reportNames[item.kind]}日期`}
              value={String(draft.day)}
              onChange={(value) => update({ day: value === 'last' ? 'last' : Number(value) })}
              options={[
                ...Array.from({ length: 28 }, (_, index) => ({ value: String(index + 1), label: `${index + 1} 日` })),
                { value: 'last', label: '月末（最后一天）' },
              ]}
            />
          )}
        </fieldset>
        {item.kind === 'quarterly' && <p className="meta">仅在 1、4、7、10 月发送；月末为这些月份的最后一天。</p>}
        <p className="meta">
          {active ? '下期' : '启用后预览'}准备：{shownTime(active ? current.next_prepare : current.preview_prepare)}
          <br />
          发送：{shownTime(active ? current.next_delivery : current.preview_delivery)}
        </p>
        {current.status_reason && <p className="small-text">{current.status_reason}</p>}
        <p className="meta">预览来自已保存设置。编辑后须保存才会更新。</p>
        <Button
          type="submit"
          disabled={!current.configured || !current.can_modify || command.conflict}
          loading={command.busy}>
          {pending ? '重试原报告设置' : `保存${reportNames[item.kind]}设置`}
        </Button>
        {command.conflict && <Button onClick={() => void refresh()}>读取最新设置，保留草稿</Button>}
        <p role="status">{command.status}</p>
      </form>
    </section>
  );
}
