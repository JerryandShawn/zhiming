import { useEffect, useRef, useState } from 'react';
import { Button, Checkbox, Input } from '../../components/ui/Controls';
import DateField from '../../live/DateField';
import type { BirthCommand, BirthDraft, BirthPort, BirthReceipt } from './types';

export function BirthForm({
  port,
  accepted,
  close,
}: {
  port: BirthPort;
  accepted: (receipt: BirthReceipt) => boolean;
  close: () => void;
}) {
  const [initial] = useState(() => port.readPrivate());
  const [draft, setDraft] = useState<BirthDraft>(() => ({ ...initial.draft }));
  const [revision, setRevision] = useState(initial.revision),
    [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [conflict, setConflict] = useState(false);
  const [latest, setLatest] = useState<ReturnType<BirthPort['readPrivate']>>();
  const pending = useRef<BirthCommand>(),
    active = useRef(false),
    mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const locked = busy || Boolean(pending.current);
  const update = (key: keyof BirthDraft, value: string) => setDraft((old) => ({ ...old, [key]: value }));
  async function save() {
    if (active.current || conflict || !consent || !draft.date.trim()) return;
    active.current = true;
    const command = pending.current ?? {
      requestId: crypto.randomUUID(),
      expectedRevision: revision,
      confirmed: true as const,
      draft: { ...draft },
    };
    pending.current = command;
    setBusy(true);
    setError('');
    try {
      const receipt = await port.confirm(command);
      if (!mounted.current) return;
      if (
        receipt.requestId !== command.requestId ||
        receipt.kind !== 'birth-confirm' ||
        receipt.write_status !== 'saved' ||
        !Number.isInteger(receipt.revision) ||
        receipt.revision <= command.expectedRevision ||
        !['partial', 'complete'].includes(receipt.confirmation) ||
        !receipt.confirmedFields.includes('date') ||
        !accepted(receipt)
      )
        throw new Error('INVALID_RECEIPT');
      close();
    } catch (reason: unknown) {
      if (!mounted.current) return;
      const status = reason && typeof reason === 'object' && 'status' in reason ? reason.status : undefined;
      if (status === 422) pending.current = undefined;
      setConflict(status === 409);
      setError(
        status === 409
          ? '资料版本已变化，草稿仍保留，请先核对当前资料。'
          : status === 422
            ? '请核对日期、时刻精度与坐标格式，尚未保存。'
            : '尚未收到有效确认，请保留原资料重试。',
      );
    } finally {
      active.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return (
    <form
      className="stack onboarding-birth-form"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}>
      <p className="meta">可以只给日期。时间、地点或性别不确定就留空，不会替你补成午夜或某座城市。</p>
      <fieldset className="stack" disabled={locked}>
        <DateField
          label="阳历出生日期"
          value={draft.date}
          onChange={(value) => update('date', value)}
          disabled={locked}
        />
        <label className="field">
          出生时刻精度
          <select
            className="input"
            aria-label="出生时刻精度"
            value={draft.precision}
            onChange={(event) => update('precision', event.target.value)}>
            <option value="">尚未填写</option>
            <option value="exact">准确时刻</option>
            <option value="approximate">大约时刻</option>
            <option value="unknown">时刻未知</option>
          </select>
        </label>
        <label className="field">
          当地出生时间
          <Input
            type="time"
            aria-label="当地出生时间"
            value={draft.time}
            disabled={draft.precision === 'unknown'}
            onChange={(event) => update('time', event.target.value)}
          />
        </label>
        {draft.precision === 'approximate' && (
          <label className="field">
            前后误差（分钟）
            <Input
              type="number"
              min="1"
              max="1440"
              value={draft.uncertaintyMinutes}
              onChange={(event) => update('uncertaintyMinutes', event.target.value)}
            />
          </label>
        )}
        <label className="field">
          排盘所用性别
          <select
            className="input"
            aria-label="排盘所用性别"
            value={draft.gender}
            onChange={(event) => update('gender', event.target.value)}>
            <option value="">暂不填写</option>
            <option value="男">男</option>
            <option value="女">女</option>
          </select>
        </label>
        <label className="field">
          出生地名称
          <Input aria-label="出生地名称" value={draft.city} onChange={(event) => update('city', event.target.value)} />
        </label>
        <details>
          <summary>出生地坐标与时区（可暂不填写）</summary>
          <div className="stack small">
            {(
              [
                ['longitude', '经度'],
                ['latitude', '纬度'],
                ['timezoneOffset', '出生地 UTC 偏移（小时）'],
              ] as const
            ).map(([key, label]) => (
              <label className="field" key={key}>
                {label}
                <Input
                  type="number"
                  step="any"
                  value={draft[key]}
                  onChange={(event) => update(key, event.target.value)}
                />
              </label>
            ))}
          </div>
        </details>
        <label className="row">
          <Checkbox
            label="我已核对并授权保存出生资料"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
          />
          我已核对并授权保存出生资料，用于后续排盘。
        </label>
      </fieldset>
      {error && <p role="alert">{error}</p>}
      {conflict && (
        <div className="stack small">
          <Button onClick={() => setLatest(port.readPrivate())}>读取并核对当前资料</Button>
          {latest && (
            <section className="stack small" aria-label="当前已保存的出生资料">
              <h3>当前已保存的资料</h3>
              <dl>
                {(
                  [
                    ['date', '阳历出生日期'],
                    ['time', '当地出生时间'],
                    ['city', '出生地名称'],
                    ['precision', '出生时刻精度'],
                    ['gender', '排盘所用性别'],
                    ['uncertaintyMinutes', '误差分钟'],
                    ['longitude', '经度'],
                    ['latitude', '纬度'],
                    ['timezoneOffset', 'UTC偏移'],
                  ] as const
                ).map(([key, label]) => (
                  <div key={key}>
                    <dt>{label}</dt>
                    <dd>{latest.draft[key] || '未填'}</dd>
                  </div>
                ))}
              </dl>
              <p className="meta">上方草稿没有改变；请核对差异后决定是否继续提交。</p>
              <Button
                onClick={() => {
                  setRevision(latest.revision);
                  pending.current = undefined;
                  setConflict(false);
                  setError('');
                  setLatest(undefined);
                }}>
                已核对当前资料，保留草稿继续
              </Button>
            </section>
          )}
        </div>
      )}
      <div className="row wrap">
        <Button type="submit" disabled={!consent || !draft.date.trim() || conflict} loading={busy}>
          {pending.current ? '重试原资料提交' : '确认并保存资料'}
        </Button>
        <Button variant="ghost" onClick={close} disabled={busy}>
          取消
        </Button>
      </div>
    </form>
  );
}
