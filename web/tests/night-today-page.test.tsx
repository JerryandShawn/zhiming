import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import TodayPage from '../src/night/today/TodayPage';
import { createSettingsPort } from '../src/night/settings/port';
import type { DailyTransitView, TodayPort, TodayReadResult } from '../src/night/today/types';
import sample from '../src/night/today/data/2026-10-21.json';

const day21 = '2026-10-21';
const day22 = '2026-10-22';
const noon = () => new Date('2026-10-21T12:00:00+08:00');
function transit(date: string, summary: string): DailyTransitView {
  const value = structuredClone(sample) as DailyTransitView;
  value.date = date;
  value.highlights = value.highlights.slice(0, 1).map((item) => ({
    ...item,
    summary,
    refs: item.refs.map((ref) => ({ ...ref, date })),
  }));
  value.evidence = value.evidence.map((item) => ({ ...item, ref: { ...item.ref, date } }));
  return value;
}
function ready(date: string, summary: string): TodayReadResult {
  return { status: 'ready', date, transit: transit(date, summary) };
}
function port(read: TodayPort['read']): TodayPort {
  return { availableDates: [day21, day22], read: vi.fn(read), resolveEvidence: vi.fn(() => undefined) };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => {
    resolve = accept;
  });
  return { promise, resolve };
}
const select = () => screen.getByLabelText('查看哪天的流日');
const changeDate = (value: string) => fireEvent.change(select(), { target: { value } });

describe('morning page lifecycle and date isolation', () => {
  it('ignores a late prior-date result even when the mock adapter ignores abort', async () => {
    const old = deferred<TodayReadResult>(),
      current = deferred<TodayReadResult>();
    const api = port((date) => (date === day21 ? old.promise : current.promise));
    const { container } = render(<TodayPage port={api} settings={createSettingsPort()} now={noon} />);
    changeDate(day22);
    await act(async () => current.resolve(ready(day22, '只属于新日期的正文')));
    expect(screen.getByText('只属于新日期的正文')).toBeVisible();
    await act(async () => old.resolve(ready(day21, '不应出现的迟到正文')));
    expect(screen.queryByText('不应出现的迟到正文')).not.toBeInTheDocument();
    expect(container.querySelector('[data-runtime="night-today"]')).toHaveAttribute('data-today', day21);
    expect(select()).toHaveValue(day22);
  });
  it.each(['result', 'transit'] as const)('rejects a wrong %s date without displaying its body', async (mismatch) => {
    const result = ready(day21, '错日的内容不能显示');
    if (mismatch === 'result') result.date = day22;
    else if (result.status === 'ready') result.transit.date = day22;
    render(<TodayPage port={port(async () => result)} settings={createSettingsPort()} now={noon} />);
    await screen.findByRole('alert');
    expect(screen.queryByText('错日的内容不能显示')).not.toBeInTheDocument();
    expect(screen.getByRole('list', { name: '安排与提醒列表' })).toBeVisible();
  });
  it('clears prior-date evidence and body immediately, then can recover from an error', async () => {
    let fail = true;
    const gate = deferred<TodayReadResult>();
    const api = port(async (date) => {
      if (date === day21) return ready(date, '原日期正文');
      if (fail) throw new Error('simulated offline');
      return gate.promise;
    });
    render(<TodayPage port={api} settings={createSettingsPort()} now={noon} />);
    await screen.findByText('原日期正文');
    changeDate(day22);
    expect(screen.queryByText('原日期正文')).not.toBeInTheDocument();
    await screen.findByRole('alert');
    fail = false;
    fireEvent.click(screen.getByRole('button', { name: '重试流日' }));
    await act(async () => gate.resolve(ready(day22, '重试后这一天的正文')));
    expect(screen.getByText('重试后这一天的正文')).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('reads Beijing dates across midnight and keeps a deliberately browsed date separate', async () => {
    let instant = new Date('2026-10-21T00:30:00+09:00');
    const api = port(async (date) => ({ status: 'empty', date, message: '没有该日样例' }));
    const { container } = render(<TodayPage port={api} settings={createSettingsPort()} now={() => instant} />);
    await waitFor(() => expect(api.read).toHaveBeenCalledWith('2026-10-20', expect.any(AbortSignal)));
    expect(select()).toHaveValue('2026-10-20');
    instant = new Date('2026-10-21T01:01:00+09:00');
    fireEvent(window, new Event('focus'));
    await waitFor(() => expect(select()).toHaveValue(day21));
    changeDate(day22);
    instant = new Date('2026-10-22T01:01:00+09:00');
    fireEvent(window, new Event('focus'));
    await waitFor(() =>
      expect(container.querySelector('[data-runtime="night-today"]')).toHaveAttribute('data-today', day22),
    );
    expect(select()).toHaveValue(day22);
    changeDate(day21);
    instant = new Date('2026-10-23T01:01:00+09:00');
    fireEvent(window, new Event('focus'));
    await waitFor(() =>
      expect(container.querySelector('[data-runtime="night-today"]')).toHaveAttribute('data-today', '2026-10-23'),
    );
    expect(select()).toHaveValue(day21);
  });
  it('reacts to the shared settings port without reloading the date or sending a report', async () => {
    const api = port(async (date) => ({ status: 'empty', date, message: '暂无样例' }));
    const settings = createSettingsPort();
    render(<TodayPage port={api} settings={settings} now={noon} />);
    await screen.findByText(/晨报按北京时间 07:00/);
    const revision = settings.getSnapshot().reports.schedules.find((item) => item.kind === 'daily')!.revision;
    await act(async () => {
      await settings.execute({
        type: 'report-save',
        kind: 'daily',
        requestId: 'synthetic-morning-off',
        expectedRevision: revision,
        draft: { enabled: false, time: '06:30' },
      });
    });
    expect(screen.getByText('晨报已暂停；你仍可以手动查看今日页。')).toBeVisible();
    expect(api.read).toHaveBeenCalledTimes(1);
  });
  it('refuses evidence resolved from another date or document despite matching short aliases', async () => {
    const value = transit(day21, '公开要点');
    const api = port(async () => ({ status: 'ready', date: day21, transit: value }));
    api.resolveEvidence = vi.fn((ref) => ({
      ref: { ...ref, date: day22 },
      label: '错日依据',
      summary: '不应泄漏的错日说明',
    }));
    render(<TodayPage port={api} settings={createSettingsPort()} now={noon} />);
    await screen.findByText('公开要点');
    expect(screen.queryByRole('button', { name: '查看八字依据' })).not.toBeInTheDocument();
    expect(screen.queryByText('不应泄漏的错日说明')).not.toBeInTheDocument();
  });
});
