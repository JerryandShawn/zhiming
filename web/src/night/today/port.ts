import day21 from './data/2026-10-21.json';
import day22 from './data/2026-10-22.json';
import day23 from './data/2026-10-23.json';
import day24 from './data/2026-10-24.json';
import day25 from './data/2026-10-25.json';
import day26 from './data/2026-10-26.json';
import day27 from './data/2026-10-27.json';
import { assertTodayDate, dailyEvidenceKey, freezeDaily, projectPublicDailySample } from './projection';
import { TodayDataError, type DailyEvidence, type TodayPort, type TodayPortOptions } from './types';

function delay(milliseconds: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    signal?.throwIfAborted();
    const abort = () => {
      clearTimeout(timer);
      reject(signal?.reason ?? new DOMException('已暂停', 'AbortError'));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', abort);
      resolve();
    }, milliseconds);
    signal?.addEventListener('abort', abort, { once: true });
  });
}

/** Replace this date port with an authenticated adapter after the HTTP contract is published. */
export function createTodayPort(options: TodayPortOptions = {}): TodayPort {
  if (options.delayMs !== undefined && (!Number.isFinite(options.delayMs) || options.delayMs < 0))
    throw new TodayDataError('INVALID_SAMPLE', '本地演示等待时间无效。');
  const samples = (options.samples ?? [day21, day22, day23, day24, day25, day26, day27]).map(projectPublicDailySample);
  const dates = new Map(samples.map((sample) => [sample.date, sample]));
  if (dates.size !== samples.length) throw new TodayDataError('INVALID_SAMPLE', '流日样例日期重复，请重新核对。');
  const evidence = new Map<string, DailyEvidence>();
  for (const sample of samples) for (const item of sample.evidence) evidence.set(dailyEvidenceKey(item.ref), item);
  const failures = new Set(options.failureDates),
    empty = new Set(options.emptyDates);
  return {
    availableDates: Object.freeze([...dates.keys()].sort()),
    async read(date, signal) {
      assertTodayDate(date);
      signal?.throwIfAborted();
      if (options.wait) await options.wait(date, signal);
      else if (options.delayMs) await delay(options.delayMs, signal);
      signal?.throwIfAborted();
      if (failures.has(date)) throw new TodayDataError('UNAVAILABLE', '这天的合成晨报暂时没有读取成功，可以重试。');
      const transit = dates.get(date);
      if (!transit || empty.has(date))
        return freezeDaily({ status: 'empty' as const, date, message: '这天还没有流日样例，日程与提醒仍可单独查看。' });
      return freezeDaily({ status: 'ready' as const, date, transit });
    },
    resolveEvidence(ref) {
      if (!ref || typeof ref.date !== 'string' || typeof ref.documentId !== 'string' || typeof ref.alias !== 'string')
        return;
      return evidence.get(dailyEvidenceKey(ref));
    },
  };
}
