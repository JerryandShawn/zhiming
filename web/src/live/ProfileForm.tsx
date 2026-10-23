import { useState } from 'react';
import { api } from '../api/client';
import { pendingPayload } from '../api/operations';
import { Button, Checkbox, Input } from '../components/ui/Controls';
import { Select } from '../components/ui/Selection';
import { record, text, useCommand } from './common';
import DateField from './DateField';
import TimeField from './TimeField';
import type { Profile } from './types';

type Draft = {
  gender: string;
  date: string;
  time: string;
  precision: string;
  minutes: string;
  city: string;
  lng: string;
  lat: string;
  timezone: string;
};
const scope = 'profile-confirm:self';
function initial(profile: Profile): Draft {
  const pending = pendingPayload<Record<string, unknown>>(scope);
  const raw = record(pending?.profile ?? profile.legacy_candidate);
  const birth = record(raw.birth),
    location = record(birth.location),
    flat = profile.effective;
  const read = (field: string, fallback: unknown) => (pending ? fallback : (flat[field] ?? fallback));
  const stamp = text(read('birth.solar_datetime', birth.solar_datetime));
  return {
    gender: text(read('gender', raw.gender)),
    date: stamp.slice(0, 10),
    time: stamp.slice(11, 16) || '00:00',
    precision: text(read('birth.precision', birth.precision ?? (birth.time_unknown ? 'unknown' : 'exact'))),
    minutes: text(read('birth.time_uncertainty_minutes', birth.time_uncertainty_minutes)),
    city: text(read('birth.location.city', location.city ?? location.name)),
    lng: text(read('birth.location.lng', location.lng)),
    lat: text(read('birth.location.lat', location.lat)),
    timezone: text(read('birth.timezone_offset', birth.timezone_offset)),
  };
}
export function profilePayload(draft: Draft, revision: number, confirmed: boolean) {
  if (!confirmed) throw new Error('请先核对资料并勾选保存授权。');
  if (!['男', '女'].includes(draft.gender)) throw new Error('请选择排盘所用性别。');
  const date = new Date(`${draft.date}T00:00:00Z`);
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(draft.date) ||
    Number.isNaN(date.getTime()) ||
    date.toISOString().slice(0, 10) !== draft.date
  )
    throw new Error('请填写有效阳历日期。');
  if (!['exact', 'approximate', 'unknown'].includes(draft.precision)) throw new Error('请明确选择时刻精度。');
  if (draft.precision !== 'unknown' && !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(draft.time))
    throw new Error('请填写有效出生时间。');
  if (
    draft.precision === 'approximate' &&
    (!Number.isInteger(Number(draft.minutes)) || Number(draft.minutes) < 1 || Number(draft.minutes) > 1440)
  )
    throw new Error('大约时刻需要填写 1 至 1440 的误差分钟数。');
  const numbers = [draft.lng, draft.lat, draft.timezone];
  if (
    numbers.some((value) => !value.trim() || !Number.isFinite(Number(value))) ||
    Math.abs(Number(draft.lng)) > 180 ||
    Math.abs(Number(draft.lat)) > 90 ||
    Number(draft.timezone) < -12 ||
    Number(draft.timezone) > 14
  )
    throw new Error('请核对出生地经纬度与 UTC 偏移。');
  return {
    expected_revision: revision,
    confirmed: true,
    profile: {
      gender: draft.gender,
      birth: {
        solar_datetime: draft.date + (draft.precision === 'unknown' ? '' : ` ${draft.time}`),
        precision: draft.precision,
        time_unknown: draft.precision === 'unknown',
        time_uncertainty_minutes: draft.precision === 'approximate' ? Number(draft.minutes) : 0,
        timezone_offset: Number(draft.timezone),
        location: { city: draft.city.trim(), lng: Number(draft.lng), lat: Number(draft.lat) },
      },
    },
  };
}
export default function ProfileForm({ profile, onSaved }: { profile: Profile; onSaved?: () => void }) {
  const [draft, setDraft] = useState(() => initial(profile));
  const pending = pendingPayload<Record<string, unknown>>(scope);
  const [version, setVersion] = useState(() => Number(pending?.expected_revision ?? profile.revision));
  const [consent, setConsent] = useState(pending?.confirmed === true);
  const command = useCommand(scope);
  const locked = command.busy || Boolean(pending);
  const update = (field: keyof Draft, value: string) => setDraft((old) => ({ ...old, [field]: value }));
  async function save() {
    try {
      const body = profilePayload(draft, version, consent);
      const result = await command.submit<{ receipts: { write_status?: string }[]; revision: number }>(
        'POST',
        '/api/subjects/self/profile/confirm',
        body,
        (value) =>
          Number.isInteger(value.revision) &&
          Array.isArray(value.receipts) &&
          value.receipts.length > 0 &&
          value.receipts.every((item) => item.write_status === 'saved'),
      );
      if (result) {
        setVersion(result.revision);
        setConsent(false);
        command.setStatus(`已保存 ${result.receipts.length} 项经你确认的资料。`);
        onSaved?.();
      }
    } catch (error) {
      command.setStatus(error instanceof Error ? error.message : '请核对资料。');
    }
  }
  async function refresh() {
    try {
      const latest = await api<Profile>('/api/subjects/self/profile');
      setVersion(latest.revision);
      command.unlock();
    } catch {
      command.setStatus('最新资料读取失败，草稿仍保留。');
    }
  }
  return (
    <section className="section">
      <h2>核对出生资料</h2>
      <p className="meta">出生资料仅在此处展示。请逐项核对后明确授权；历史档案不会自动成为已确认事实。</p>
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}>
        <fieldset disabled={locked} className="stack">
          <div className="field">
            排盘所用性别
            <Select
              label="排盘所用性别"
              value={draft.gender}
              options={[
                { value: '', label: '请选择' },
                { value: '男', label: '男' },
                { value: '女', label: '女' },
              ]}
              onChange={(value) => update('gender', value)}
            />
          </div>
          <DateField
            label="阳历出生日期"
            value={draft.date}
            onChange={(value) => update('date', value)}
            disabled={locked}
          />
          <div className="field">
            出生时刻精度
            <Select
              label="出生时刻精度"
              value={draft.precision}
              options={[
                { value: 'exact', label: '准确时刻' },
                { value: 'approximate', label: '大约时刻' },
                { value: 'unknown', label: '时刻未知' },
                ...(draft.precision === 'interval'
                  ? [{ value: 'interval', label: '原资料为时段，请明确选择精度' }]
                  : []),
              ]}
              onChange={(value) => update('precision', value)}
            />
          </div>
          <TimeField
            label="当地出生时间"
            value={draft.time}
            onChange={(value) => update('time', value)}
            disabled={draft.precision === 'unknown' || locked}
          />
          {draft.precision === 'unknown' && <p className="meta">时刻未知时只保存日期，不把候选样本当作出生时刻。</p>}
          {draft.precision === 'approximate' && (
            <label className="field">
              前后误差（分钟）
              <Input
                type="number"
                min="1"
                max="1440"
                step="1"
                required
                value={draft.minutes}
                onChange={(event) => update('minutes', event.target.value)}
              />
            </label>
          )}
          <label className="field">
            出生地名称
            <Input
              required
              maxLength={120}
              value={draft.city}
              onChange={(event) => update('city', event.target.value)}
            />
          </label>
          {(
            [
              ['lng', '经度'],
              ['lat', '纬度'],
              ['timezone', '出生地 UTC 偏移（小时）'],
            ] as const
          ).map(([key, label]) => (
            <label className="field" key={key}>
              {label}
              <Input
                type="number"
                step="any"
                required
                value={draft[key]}
                onChange={(event) => update(key, event.target.value)}
              />
            </label>
          ))}
          <label className="row">
            <Checkbox
              label="我已核对并授权保存出生与性别资料"
              checked={consent}
              onChange={(event) => setConsent(event.target.checked)}
            />
            我已核对并授权保存出生与性别资料，用于后续排盘。
          </label>
        </fieldset>
        {pending && <p className="meta">上次提交尚未确认，资料已锁定；重试将沿用原请求。</p>}
        <Button type="submit" variant="primary" disabled={!consent || command.conflict} loading={command.busy}>
          {pending ? '重试原资料提交' : '确认并保存资料'}
        </Button>
        {command.conflict && <Button onClick={() => void refresh()}>读取最新资料，保留草稿</Button>}
        <p role="status">{command.status}</p>
      </form>
    </section>
  );
}
