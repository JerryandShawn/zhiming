import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import SettingsPage from '../src/night/settings/SettingsPage';
import { ReportForm } from '../src/night/settings/ReportForms';
import { createSettingsPort } from '../src/night/settings/port';
import type { SettingsCommand, SettingsPort } from '../src/night/settings/types';

beforeEach(() => history.replaceState(null, '', '/?night=demo#/settings'));
const row = (kind: string) => document.querySelector<HTMLElement>(`[data-report-kind="${kind}"]`)!;

it('uses all four report contracts, 1..28 or last, and cancels edits without a write', async () => {
  const base = createSettingsPort(),
    execute = vi.fn(base.execute);
  render(<SettingsPage port={{ ...base, execute }} />);
  expect(document.querySelectorAll('[data-report-kind]')).toHaveLength(4);
  const monthly = within(row('monthly'));
  expect(monthly.getByRole('combobox', { name: '月报日期' }).querySelectorAll('option')).toHaveLength(29);
  expect(monthly.queryByRole('option', { name: '29 日' })).not.toBeInTheDocument();
  expect(within(row('quarterly')).getByText(/仅在 1、4、7、10 月发送/)).toBeInTheDocument();
  fireEvent.change(within(row('daily')).getByLabelText('晨报发送时间'), { target: { value: '09:15' } });
  await userEvent.click(within(row('daily')).getByRole('button', { name: '取消修改' }));
  expect(within(row('daily')).getByLabelText('晨报发送时间')).toHaveValue('07:00');
  expect(execute).not.toHaveBeenCalled();
});

it('waits for a report receipt and keeps a failed request payload and ID immutable on retry', async () => {
  const base = createSettingsPort();
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const execute = vi
    .fn<SettingsPort['execute']>()
    .mockRejectedValueOnce(new Error('network'))
    .mockImplementation(async (command) => {
      await gate;
      return base.execute(command);
    });
  render(<SettingsPage port={{ ...base, execute }} />);
  fireEvent.change(within(row('daily')).getByLabelText('晨报发送时间'), { target: { value: '09:15' } });
  await userEvent.click(within(row('daily')).getByRole('button', { name: '保存晨报设置' }));
  expect(within(row('daily')).queryByRole('status')).not.toBeInTheDocument();
  expect(within(row('daily')).getByLabelText('晨报发送时间')).toBeDisabled();
  await userEvent.click(within(row('daily')).getByRole('button', { name: '重试原报告设置' }));
  expect(within(row('daily')).queryByRole('status')).not.toBeInTheDocument();
  expect(execute.mock.calls[1][0]).toBe(execute.mock.calls[0][0]);
  await act(async () => release());
  await waitFor(() =>
    expect(within(row('daily')).getByRole('status')).toHaveTextContent('已保存晨报设置（本地演示）。'),
  );
  expect(base.getSnapshot().reports.schedules[0].time).toBe('09:15');
});

it('keeps followup quiet hours separate from the explicitly scheduled morning report', async () => {
  const port = createSettingsPort();
  render(<SettingsPage port={port} />);
  await userEvent.click(screen.getByRole('switch', { name: '跟进开关' }));
  await userEvent.click(screen.getByRole('button', { name: '3次' }));
  fireEvent.change(screen.getByLabelText('免打扰开始时间'), { target: { value: '21:00' } });
  await userEvent.click(screen.getByRole('button', { name: '保存主动联系设置' }));
  expect(port.getSnapshot().contact).toMatchObject({
    followup: false,
    dailyCap: 3,
    dndStart: '21:00',
    dndEnd: '08:00',
  });
  expect(port.getSnapshot().reports.schedules[0]).toMatchObject({ enabled: true, time: '07:00', revision: 1 });
  expect(screen.getByRole('status')).toHaveTextContent('已保存主动联系设置（本地演示）。');
});

it('requires device confirmation, cannot revoke the current device, and leaves real auth storage unchanged', async () => {
  const port = createSettingsPort(),
    execute = vi.fn(port.execute);
  sessionStorage.setItem('mingjing-auth-token', 'synthetic-do-not-change');
  render(<SettingsPage port={{ ...port, execute }} />);
  const current = document.querySelector<HTMLElement>('[data-device-id="mock-current"]')!;
  expect(within(current).getByRole('button', { name: '吊销此设备' })).toBeDisabled();
  const phone = document.querySelector<HTMLElement>('[data-device-id="mock-phone"]')!;
  await userEvent.click(within(phone).getByRole('button', { name: '吊销此设备' }));
  await userEvent.click(screen.getByRole('button', { name: '取消' }));
  expect(execute).not.toHaveBeenCalled();
  await userEvent.click(within(phone).getByRole('button', { name: '吊销此设备' }));
  await userEvent.click(screen.getByRole('button', { name: '确认吊销（本地演示）' }));
  expect(phone).toHaveAttribute('data-status', 'revoked');
  expect(screen.getByRole('status')).toHaveTextContent('已吊销此合成设备');
  await userEvent.keyboard('{Escape}');
  await userEvent.click(screen.getByRole('button', { name: '退出本地演示' }));
  await userEvent.click(screen.getByRole('button', { name: '确认退出本地演示' }));
  expect(port.getSnapshot().localSessionEnded).toBe(true);
  expect(sessionStorage.getItem('mingjing-auth-token')).toBe('synthetic-do-not-change');
  sessionStorage.removeItem('mingjing-auth-token');
});

it('locks report writes when delivery is sending or uncertain', () => {
  const base = createSettingsPort(),
    execute = vi.fn(base.execute);
  const item = {
    ...base.getSnapshot().reports.schedules[0],
    delivery_state: { sending: 1, uncertain: 0, pending: 0, sent: 0 },
  };
  render(<ReportForm item={item} port={{ ...base, execute }} />);
  expect(screen.getByRole('button', { name: '保存晨报设置' })).toBeDisabled();
  fireEvent.submit(document.querySelector('form')!);
  expect(execute).not.toHaveBeenCalled();
});

it('accepts a matching unchanged report policy receipt at its current revision', async () => {
  const port = createSettingsPort(),
    report = port.getSnapshot().reports.schedules[0];
  const execute = vi.fn(async (command: SettingsCommand) => ({
    requestId: command.requestId,
    kind: command.type,
    write_status: 'saved' as const,
    revision: report.revision,
    snapshotRevision: 1,
    report,
  }));
  render(<ReportForm item={report} port={{ ...port, execute }} />);
  await userEvent.click(screen.getByRole('button', { name: '保存晨报设置' }));
  expect(screen.getByRole('status')).toHaveTextContent('已保存晨报设置（本地演示）。');
});
