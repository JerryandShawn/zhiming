import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Checkbox } from '../src/components/ui/Controls';
import { Select, TimePicker } from '../src/components/ui/Selection';
import { DatePicker } from '../src/components/DatePicker';
import Chat from '../src/pages/Chat';

describe('14 I reviewed static controls', () => {
  it('keeps citation adjacent to the quoted text and punctuation', () => {
    render(<Chat />);
    const chip = screen.getByRole('button', { name: '查看第1条依据' });
    expect(chip.parentElement).toHaveTextContent('周三是戊辰日1，对你');
    expect(chip.previousSibling?.textContent).toBe('周三是戊辰日');
    expect(chip.nextSibling?.textContent?.startsWith('，')).toBe(true);
  });
  it('retains native checkbox semantics while the visual target is customized', async () => {
    const change = vi.fn();
    render(<Checkbox label="聚焦跳槽" onChange={change} />);
    const control = screen.getByRole('checkbox', { name: '聚焦跳槽' });
    control.focus();
    await userEvent.keyboard(' ');
    expect(control).toBeChecked();
    expect(change).toHaveBeenCalledOnce();
  });
  it('opens a custom month calendar, preserves date markers, and returns focus after selection', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch');
    render(<DatePicker />);
    const trigger = screen.getByRole('button', { name: /看哪一天：今天 10月17日/ });
    await userEvent.click(trigger);
    expect(screen.getByRole('button', { name: '2026-10-01 法定假日 国庆' })).toBeVisible();
    expect(screen.getByRole('button', { name: '2026-10-10 调休上班' })).toBeVisible();
    expect(screen.getByRole('button', { name: '2026-10-23 霜降' })).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '2026-10-18 重阳' }));
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(trigger).toHaveTextContent('看哪一天：10月18日');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it('does not invent holiday dates for an unpublished year', async () => {
    render(<DatePicker />);
    await userEvent.click(screen.getByRole('button', { name: /看哪一天/ }));
    for (let i = 0; i < 3; i++) await userEvent.click(screen.getByRole('button', { name: '下个月' }));
    expect(screen.getByText('该年放假安排尚未公布')).toBeVisible();
    expect(screen.queryByRole('button', { name: /法定假日/ })).not.toBeInTheDocument();
  });
  it('selects options with arrows, Enter, and focus return', async () => {
    const change = vi.fn();
    render(
      <Select
        label="星期"
        value="1"
        onChange={change}
        options={[
          { value: '1', label: '星期一' },
          { value: '2', label: '星期二' },
        ]}
      />,
    );
    const trigger = screen.getByRole('combobox', { name: '星期' });
    trigger.focus();
    await userEvent.keyboard('{ArrowDown}');
    await waitFor(() => expect(screen.getByRole('option', { name: '星期一' })).toHaveFocus());
    await userEvent.keyboard('{ArrowDown}{Enter}');
    expect(change).toHaveBeenCalledWith('2');
    await waitFor(() => expect(trigger).toHaveFocus());
  });
  it('restricts time options to a valid day and updates the local button', async () => {
    render(<TimePicker label="发送时间" initial="07:00" />);
    await userEvent.click(screen.getByRole('button', { name: '发送时间 07:00' }));
    await userEvent.click(screen.getByRole('combobox', { name: '发送时间小时' }));
    expect(screen.getAllByRole('option')).toHaveLength(24);
    await userEvent.click(screen.getByRole('option', { name: '10' }));
    await userEvent.click(screen.getByRole('combobox', { name: '发送时间分钟' }));
    expect(screen.getAllByRole('option')).toHaveLength(60);
    await userEvent.click(screen.getByRole('option', { name: '30' }));
    expect(screen.getByRole('button', { name: '发送时间 10:30' })).toBeInTheDocument();
  });
});
