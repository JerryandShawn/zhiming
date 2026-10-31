import { AboutMeError } from '../me/types';
import type { BirthCommand, BirthDraft, BirthPort, BirthReceipt, BirthSummary } from './types';

export const emptyBirthDraft = (): BirthDraft => ({
  date: '',
  time: '',
  precision: '',
  uncertaintyMinutes: '',
  gender: '',
  city: '',
  longitude: '',
  latitude: '',
  timezoneOffset: '',
});
function normalize(draft: BirthDraft): BirthDraft {
  const result = emptyBirthDraft();
  for (const key of Object.keys(result) as (keyof BirthDraft)[]) {
    const value = draft[key];
    if (typeof value !== 'string') throw new AboutMeError('INVALID', 422, '请核对出生资料格式。');
    Object.assign(result, { [key]: value.trim() });
  }
  if (
    result.date &&
    (!/^\d{4}-\d{2}-\d{2}$/.test(result.date) ||
      Number.isNaN(new Date(`${result.date}T00:00:00Z`).getTime()) ||
      new Date(`${result.date}T00:00:00Z`).toISOString().slice(0, 10) !== result.date)
  )
    throw new AboutMeError('INVALID', 422, '请填写有效阳历日期。');
  if (!['', 'exact', 'approximate', 'unknown'].includes(result.precision) || !['', '男', '女'].includes(result.gender))
    throw new AboutMeError('INVALID', 422, '请核对精度与排盘性别。');
  if (result.precision === 'unknown') {
    result.time = '';
    result.uncertaintyMinutes = '';
  }
  if (
    result.time &&
    (!result.date ||
      !['exact', 'approximate'].includes(result.precision) ||
      !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(result.time))
  )
    throw new AboutMeError('INVALID', 422, '提供时刻时，请核对日期、精度与有效时刻。');
  if (['exact', 'approximate'].includes(result.precision) && !result.time)
    throw new AboutMeError('INVALID', 422, '准确或大约时刻不能为空；不知道可选时刻未知。');
  if (
    result.precision === 'approximate' &&
    (!/^\d+$/.test(result.uncertaintyMinutes) ||
      Number(result.uncertaintyMinutes) < 1 ||
      Number(result.uncertaintyMinutes) > 1440)
  )
    throw new AboutMeError('INVALID', 422, '大约时刻需要1至1440的误差分钟。');
  if (result.precision !== 'approximate') result.uncertaintyMinutes = '';
  for (const [key, lower, upper] of [
    ['longitude', -180, 180],
    ['latitude', -90, 90],
    ['timezoneOffset', -12, 14],
  ] as const)
    if (
      result[key] &&
      (!Number.isFinite(Number(result[key])) || Number(result[key]) < lower || Number(result[key]) > upper)
    )
      throw new AboutMeError('INVALID', 422, '请核对经纬度或时区范围。');
  if (!Object.values(result).some(Boolean))
    throw new AboutMeError('INVALID', 422, '请提供至少一项实际资料，或暂时跳过。');
  return result;
}
// Raw fields are confined to this port and the dedicated confirmation Sheet.
export function createBirthPort(seed?: { revision: number; draft: BirthDraft }): BirthPort {
  let revision = seed?.revision ?? 0;
  let draft = seed ? normalize(seed.draft) : emptyBirthDraft();
  const completed = new Map<string, { signature: string; receipt: BirthReceipt }>();
  const summary = (): BirthSummary => {
    const fields = (Object.keys(draft) as (keyof BirthDraft)[]).filter((key) => Boolean(draft[key]));
    const complete = Boolean(
      draft.date &&
      draft.time &&
      draft.gender &&
      draft.longitude &&
      draft.latitude &&
      draft.timezoneOffset &&
      ['exact', 'approximate'].includes(draft.precision),
    );
    return {
      revision,
      status: revision === 0 ? 'unconfirmed' : complete ? 'complete' : 'partial',
      confirmedFields: fields,
      canComputeGift: false,
    };
  };
  return {
    readSummary: summary,
    readPrivate: () => ({ revision, draft: { ...draft } }),
    async confirm(command: BirthCommand) {
      if (!command.requestId || command.confirmed !== true)
        throw new AboutMeError('INVALID', 422, '请先明确勾选保存授权。');
      const normalized = normalize(command.draft),
        signature = JSON.stringify({ expectedRevision: command.expectedRevision, draft: normalized });
      const prior = completed.get(command.requestId);
      if (prior) {
        if (prior.signature !== signature)
          throw new AboutMeError('REPLAY_CHANGED', 409, '原资料提交内容已改变，请先核对原操作。');
        return prior.receipt;
      }
      if (!Number.isInteger(command.expectedRevision) || command.expectedRevision !== revision)
        throw new AboutMeError('CONFLICT', 409, '资料版本已变化，草稿保留，请读取最新资料并再次核对。');
      draft = normalized;
      revision++;
      const value = summary();
      const receipt: BirthReceipt = Object.freeze({
        requestId: command.requestId,
        kind: 'birth-confirm',
        write_status: 'saved',
        revision,
        confirmation: value.status === 'complete' ? 'complete' : 'partial',
        confirmedFields: Object.freeze([...value.confirmedFields]) as (keyof BirthDraft)[],
      });
      completed.set(command.requestId, { signature, receipt });
      return receipt;
    },
  };
}
