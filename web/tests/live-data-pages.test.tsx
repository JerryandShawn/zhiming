import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuth } from '../src/api/client';
import ProfileForm, { profilePayload } from '../src/live/ProfileForm';
import MemoryCard, { memoryPayload } from '../src/live/MemoryCard';
import ReportSchedule, { schedulePayload, scheduleReceipt } from '../src/live/ReportSchedule';
import Chart from '../src/live/Chart';
import Me from '../src/live/Me';
import Cases from '../src/live/Cases';
import type { Fact, Profile, Schedule } from '../src/live/types';

const birthDraft = {
  gender: '女',
  date: '1998-03-12',
  time: '08:15',
  precision: 'exact',
  minutes: '',
  city: '合成城',
  lng: '116.4',
  lat: '39.9',
  timezone: '8',
};
const profile: Profile = {
  revision: 9,
  legacy_candidate: {},
  requires_explicit_confirmation: false,
  effective: {
    gender: '女',
    'birth.solar_datetime': '1998-03-12 08:15',
    'birth.precision': 'exact',
    'birth.location.city': '合成城',
    'birth.location.lng': 116.4,
    'birth.location.lat': 39.9,
    'birth.timezone_offset': 8,
  },
};
const fact: Fact = {
  id: 'fact-synthetic',
  revision: 3,
  status: 'active',
  content: '我喜欢早晨阅读',
  kind: 'preference',
  source_refs: [{ quote: '我喜欢早晨阅读', message_id: 'source-synthetic' }],
};
const schedule: Schedule = {
  kind: 'daily',
  revision: 4,
  enabled: true,
  time: '07:00',
  configured: true,
  can_modify: true,
  status: 'active',
};
function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}
function savedSchedule(base: Schedule, revision = base.revision + 1): Schedule {
  return { ...base, revision, receipt: { id: base.kind, kind: 'report_schedule', revision, write_status: 'saved' } };
}
function provider(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}
let epoch = 0;
beforeEach(() => {
  sessionStorage.clear();
  useAuth.getState().setToken(`synthetic-data-${++epoch}`);
  location.hash = '#/chart?tab=bazi&date=2026-10-18';
});

describe('M4 data contract projections', () => {
  it('requires consent and a positive approximate uncertainty; unknown has no fabricated time', () => {
    expect(() => profilePayload(birthDraft, 9, false)).toThrow(/勾选/);
    expect(() => profilePayload({ ...birthDraft, precision: 'approximate' }, 9, true)).toThrow(/误差分钟/);
    expect(() => profilePayload({ ...birthDraft, precision: 'approximate', minutes: '1.5' }, 9, true)).toThrow();
    const payload = profilePayload({ ...birthDraft, precision: 'unknown' }, 9, true);
    expect(payload.profile.birth.solar_datetime).toBe('1998-03-12');
    expect(payload.profile.birth.time_unknown).toBe(true);
    expect(payload.profile.birth.time_uncertainty_minutes).toBe(0);
    expect(Object.keys(payload)).toEqual(['expected_revision', 'confirmed', 'profile']);
  });
  it('requires structural value consent and the exact new value in the new original quote', () => {
    const structured = { ...fact, field: 'work.hours', value: 8 };
    expect(() => memoryPayload(structured, '改为6小时', '6', false, 3)).toThrow(/勾选/);
    expect(() => memoryPayload(structured, '现在更短', '6', true, 3)).toThrow(/写明/);
    expect(memoryPayload(structured, '改为6小时', '6', true, 3)).toEqual({
      expected_revision: 3,
      text: '改为6小时',
      value: 6,
    });
    expect(() => memoryPayload({ ...structured, value: true }, '现在改成yes', 'yes', true, 3)).toThrow(/True/);
  });
  it('projects only allowed report keys and checks the receipt revision against the returned row', () => {
    expect(
      Object.keys(schedulePayload('daily', 4, { enabled: true, time: '07:00', day: 31, weekday: 1 })).sort(),
    ).toEqual(['enabled', 'expected_revision', 'kind', 'time']);
    expect(schedulePayload('weekly', 4, { enabled: false, time: '08:00', weekday: 7, day: 31 })).toEqual({
      kind: 'weekly',
      expected_revision: 4,
      enabled: false,
      time: '08:00',
      weekday: 7,
    });
    expect(schedulePayload('monthly', 4, { enabled: true, time: '09:00', day: 'last' })).toHaveProperty('day', 'last');
    expect(scheduleReceipt(savedSchedule(schedule), 'daily')).toBe(true);
    expect(scheduleReceipt({ ...savedSchedule(schedule), revision: 9 }, 'daily')).toBe(false);
    expect(scheduleReceipt(savedSchedule(schedule), 'weekly')).toBe(false);
  });
  it('disables the unknown birth time control and saves only after explicit consent and a real receipt', async () => {
    const fetch = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(response({ revision: 10, receipts: [{ write_status: 'saved' }] }));
    render(<ProfileForm profile={profile} />);
    expect(screen.getByRole('button', { name: '确认并保存资料' })).toBeDisabled();
    await userEvent.click(screen.getByRole('combobox', { name: '出生时刻精度' }));
    await userEvent.click(screen.getByRole('option', { name: '时刻未知' }));
    expect(screen.getByRole('combobox', { name: '当地出生时间小时' })).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox', { name: '我已核对并授权保存出生与性别资料' }));
    await userEvent.click(screen.getByRole('button', { name: '确认并保存资料' }));
    await screen.findByText('已保存 1 项经你确认的资料。');
    const body = JSON.parse(String(fetch.mock.calls[0][1]?.body));
    expect(body.profile.birth.solar_datetime).toBe('1998-03-12');
    expect(body.request_id).toEqual(expect.any(String));
  });
  it('retains a changed profile draft through 409, locks saving, then uses the freshly read version', async () => {
    const fetch = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response({}, 409))
      .mockResolvedValueOnce(response({ ...profile, revision: 12 }))
      .mockResolvedValueOnce(response({ revision: 13, receipts: [{ write_status: 'saved' }] }));
    render(<ProfileForm profile={profile} />);
    await userEvent.clear(screen.getByLabelText('出生地名称'));
    await userEvent.type(screen.getByLabelText('出生地名称'), '新的合成城');
    await userEvent.click(screen.getByRole('checkbox', { name: '我已核对并授权保存出生与性别资料' }));
    await userEvent.click(screen.getByRole('button', { name: '确认并保存资料' }));
    await screen.findByText(/内容已在别处更新，草稿已保留/);
    expect(screen.getByRole('button', { name: '确认并保存资料' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '读取最新资料，保留草稿' }));
    expect(screen.getByLabelText('出生地名称')).toHaveValue('新的合成城');
    await waitFor(() => expect(screen.getByRole('button', { name: '确认并保存资料' })).toBeEnabled());
    await userEvent.click(screen.getByRole('button', { name: '确认并保存资料' }));
    await screen.findByText('已保存 1 项经你确认的资料。');
    const original = JSON.parse(String(fetch.mock.calls[0][1]?.body));
    const updated = JSON.parse(String(fetch.mock.calls[2][1]?.body));
    expect(updated.expected_revision).toBe(12);
    expect(updated.request_id).not.toBe(original.request_id);
    expect(updated.profile.birth.location.city).toBe('新的合成城');
  });
  it('does not claim a profile save from an empty receipt and reuses the exact request after an ambiguous result', async () => {
    const fetch = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response({ revision: 10, receipts: [] }))
      .mockResolvedValueOnce(response({ revision: 10, receipts: [{ write_status: 'saved' }] }));
    render(<ProfileForm profile={profile} />);
    await userEvent.click(screen.getByRole('checkbox', { name: '我已核对并授权保存出生与性别资料' }));
    await userEvent.click(screen.getByRole('button', { name: '确认并保存资料' }));
    await screen.findByText(/没有收到有效保存回执/);
    expect(screen.queryByText(/已保存 \d+ 项/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '重试原资料提交' }));
    await screen.findByText('已保存 1 项经你确认的资料。');
    expect(fetch.mock.calls[0][1]?.body).toBe(fetch.mock.calls[1][1]?.body);
  });
  it('preserves report edits on 409 and validates the next submission with the new revision', async () => {
    const fresh = { ...schedule, revision: 8, time: '11:00' };
    const fetch = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response({}, 409))
      .mockResolvedValueOnce(
        response({
          timezone: 'Asia/Shanghai',
          prepare_minutes: 15,
          schedules: [
            fresh,
            { ...schedule, kind: 'weekly' },
            { ...schedule, kind: 'monthly' },
            { ...schedule, kind: 'quarterly' },
          ],
        }),
      )
      .mockResolvedValueOnce(response(savedSchedule({ ...fresh, enabled: false, time: schedule.time })));
    render(<ReportSchedule item={schedule} />);
    await userEvent.click(screen.getByRole('switch', { name: '启用晨报' }));
    await userEvent.click(screen.getByRole('button', { name: '保存晨报设置' }));
    await screen.findByText(/内容已在别处更新，草稿已保留/);
    expect(screen.getByRole('button', { name: '保存晨报设置' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '读取最新设置，保留草稿' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '保存晨报设置' })).toBeEnabled());
    expect(screen.getByRole('switch', { name: '启用晨报' })).not.toBeChecked();
    await userEvent.click(screen.getByRole('button', { name: '保存晨报设置' }));
    await screen.findByText('已保存晨报设置，版本 9。');
    const body = JSON.parse(String(fetch.mock.calls[2][1]?.body));
    expect(Object.keys(body).sort()).toEqual(['enabled', 'expected_revision', 'kind', 'request_id', 'time']);
    expect(body.expected_revision).toBe(8);
    expect(body.enabled).toBe(false);
    expect(body.time).toBe('07:00');
  });
  it('shows only an authorized source quote while checking whether the retained source is available', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      response({ source_available: true, sources: [{ content: 'PRIVATE_BIRTH_RAW_1998-03-12' }] }),
    );
    render(<MemoryCard fact={fact} onSaved={vi.fn()} />);
    await userEvent.click(screen.getByText('来源与修改记录'));
    await userEvent.click(screen.getByRole('button', { name: '查看原始来源' }));
    await screen.findByText('我喜欢早晨阅读', { selector: 'blockquote' });
    expect(document.body).not.toHaveTextContent('PRIVATE_BIRTH_RAW');
  });
  it('distinguishes source deletion and checks the deleted effect receipt', async () => {
    const onSaved = vi.fn();
    const fetch = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(response({ id: fact.id, revision: 4, write_status: 'deleted', kind: 'fact' }));
    render(<MemoryCard fact={fact} onSaved={onSaved} />);
    await userEvent.click(screen.getByText('删除范围', { selector: 'summary' }));
    await userEvent.click(screen.getByRole('combobox', { name: '删除范围' }));
    await userEvent.click(screen.getByRole('option', { name: '删除整段来源及关联内容' }));
    await userEvent.click(screen.getByRole('checkbox', { name: '确认删除所选范围' }));
    await userEvent.click(screen.getByRole('button', { name: '确认删除所选范围' }));
    await screen.findByText('已收到删除回执。');
    expect(String(fetch.mock.calls[0][0])).toContain('scope=source&expected_revision=3');
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toMatchObject({ scope: 'source', expected_revision: 3 });
    expect(onSaved).toHaveBeenCalledOnce();
  });
  it('never renders original birth or unknown private chart fields', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      response({
        solar_datetime: 'PRIVATE_BIRTH_RAW',
        utc_time: 'PRIVATE_UTC',
        private_deck: 'PRIVATE_DECK',
        pillars: { day: { ganzhi: '甲子' } },
        day_master: '甲',
        core_meta: { branches: [{ civil_datetime: 'PRIVATE_BRANCH' }] },
      }),
    );
    provider(<Chart />);
    const pillar = await screen.findByRole('button', { name: '查看日柱甲子依据' });
    expect(document.body.textContent).not.toMatch(/PRIVATE_BIRTH|PRIVATE_UTC|PRIVATE_DECK|PRIVATE_BRANCH/);
    await userEvent.click(pillar);
    const link = screen.getByRole('link', { name: '带着这项依据问明镜' });
    const params = new URLSearchParams(link.getAttribute('href')?.split('?')[1]);
    expect(params.get('date')).toBe('2026-10-18');
    expect(params.get('system')).toBe('bazi');
    expect(params.get('key')).toBe('pillars.day.ganzhi');
  });
  it('hides birth fact originals outside the profile confirmation section', async () => {
    location.hash = '#/me?section=memory';
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      response([{ ...fact, field: 'birth.solar_datetime', content: 'PRIVATE_BIRTH_RAW', value: '1998-03-12' }]),
    );
    provider(<Me />);
    await screen.findByText(/出生资料已隐藏/);
    expect(document.body).not.toHaveTextContent('PRIVATE_BIRTH_RAW');
    expect(document.body).not.toHaveTextContent('1998-03-12');
  });
  it('creates an actual case, then submits an edited goal with its entity revision', async () => {
    let records: { id: string; revision: number; status: string; title: string; goal: string }[] = [];
    const commands: Record<string, unknown>[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_path, options) => {
      if (!options?.body) return response(records);
      const body = JSON.parse(String(options.body));
      commands.push(body);
      if (options.method === 'POST') {
        const created = { id: 'case-synthetic', revision: 1, status: 'open', title: body.title, goal: body.goal };
        records = [created];
        return response(created);
      }
      const updated = { ...records[0], ...body.changes, revision: 2 };
      records = [updated];
      return response(updated);
    });
    location.hash = '#/cases';
    provider(<Cases />);
    await userEvent.click(screen.getByRole('button', { name: '新建事项' }));
    await userEvent.type(screen.getByLabelText('标题'), '合成学习计划');
    await userEvent.type(screen.getByLabelText('目标'), '先核对可用时间');
    await userEvent.click(screen.getByRole('button', { name: '创建事项' }));
    await screen.findByText('事项已保存。');
    await userEvent.click(screen.getByRole('button', { name: '关闭' }));
    await userEvent.click(await screen.findByRole('button', { name: /合成学习计划/ }));
    await userEvent.clear(screen.getByLabelText('事项目标'));
    await userEvent.type(screen.getByLabelText('事项目标'), '每天先留一小时');
    await userEvent.click(screen.getByRole('button', { name: '保存事项更正' }));
    await screen.findByText('事项更正已保存。');
    expect(commands[0]).toMatchObject({ title: '合成学习计划', goal: '先核对可用时间', subject_id: 'self' });
    expect(commands[1]).toMatchObject({ expected_revision: 1, changes: { goal: '每天先留一小时', status: 'open' } });
    expect(commands[0].request_id).not.toBe(commands[1].request_id);
  });
  it('reads legacy sections without promoting prediction bodies or raw birth fields to facts', async () => {
    location.hash = '#/me?section=timeline';
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) =>
      String(path).startsWith('/api/memories')
        ? response([])
        : response({
            forecasts: [{ date: '2026-10-18', prediction: 'PRIVATE_LEGACY_PREDICTION', birth: 'PRIVATE_BIRTH_RAW' }],
            stats: { accuracy: 'PRIVATE_ACCURACY' },
          }),
    );
    provider(<Me />);
    await screen.findByText('此分区保留 1 条历史记录。');
    expect(screen.getByText('记录日期：2026-10-18')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/PRIVATE_LEGACY|PRIVATE_BIRTH|PRIVATE_ACCURACY/);
    expect(screen.getByRole('button', { name: '修改此分区' })).toBeDisabled();
  });
});
