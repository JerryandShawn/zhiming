import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MiniCalendar } from '../src/components/Calendar';
import { MonthCalendar } from '../src/calendar/MonthCalendar';
import { TodayCalendar } from '../src/calendar/TodayCalendar';
import { dateLabel, monthDays, unavailableCalendar, validDate, type CalendarSource } from '../src/calendar/data';
import { exampleCalendar, todayExampleCalendar } from '../src/calendar/examples';

function viewport(desktop: boolean) {
  vi.mocked(window.matchMedia).mockImplementation((query) => ({
    matches: desktop && query === '(min-width: 1024px)',
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}
beforeEach(() => viewport(false));

describe('calendar facts and publication coverage', () => {
  it('retains the original preview date names and exposes all five marker types', () => {
    render(<MiniCalendar onSelect={vi.fn()} />);
    expect(screen.getByRole('button', { name: /^2026-10-01 法定假日 国庆/ })).toBeVisible();
    expect(screen.getByRole('button', { name: /^2026-10-10 调休上班/ })).toBeVisible();
    expect(screen.getByRole('button', { name: /^2026-10-08 寒露/ })).toBeVisible();
    expect(screen.getByRole('button', { name: /^2026-10-18 重阳/ })).toBeVisible();
    expect(screen.getByRole('button', { name: /^2026-10-21 你的安排：面试安排/ })).toBeVisible();
    expect(document.querySelector('[data-date="2026-10-01"]')).toHaveAccessibleName(
      '2026-10-01 法定假日 国庆 1 休 国庆',
    );
    expect(document.querySelector('[data-date="2026-10-10"]')).toHaveAccessibleName('2026-10-10 调休上班 10 班');
    expect(screen.getByText('合成日历示例 · 不代表真实安排')).toBeVisible();
    expect(screen.getByText('你的安排')).toBeVisible();
  });

  it('keeps festival, term and arrangement together with independently identifiable dots', () => {
    const source: CalendarSource = () => ({
      source: 'synthetic',
      holidayStatus: 'covered',
      notes: { '2026-10-08': { festivals: ['合成节日'], terms: ['寒露'], arrangements: ['核对日程'] } },
    });
    render(<MonthCalendar today="2026-10-17" source={source} onSelect={vi.fn()} />);
    const cell = screen.getByRole('button', { name: /^2026-10-08 合成节日 寒露 你的安排：核对日程/ });
    expect(within(cell).getByText('合成节日')).toBeVisible();
    expect(within(cell).getByText('寒露')).toBeVisible();
    expect(cell.querySelector('.calendar-term')).toBeInTheDocument();
    expect(cell.querySelector('.calendar-event')).toBeInTheDocument();
    expect(within(cell).getByRole('img', { name: '核对日程' })).toBeVisible();
  });

  it('distinguishes actual today from a separately selected date', () => {
    render(<MonthCalendar today="2026-10-17" selected="2026-10-21" source={exampleCalendar} onSelect={vi.fn()} />);
    const today = screen.getByRole('button', { name: /^2026-10-17 / });
    const chosen = screen.getByRole('button', { name: /2026-10-21/ });
    expect(today).toHaveAttribute('aria-current', 'date');
    expect(today).toHaveAttribute('aria-pressed', 'false');
    expect(chosen).toHaveAttribute('aria-pressed', 'true');
    expect(chosen).not.toHaveAttribute('aria-current');
  });

  it('gives noninteractive day cells an accessible name and date identity', () => {
    render(<MiniCalendar />);
    const day = screen.getByRole('group', { name: '2026-10-01 法定假日 国庆' });
    expect(day).toHaveAttribute('data-date', '2026-10-01');
    expect(document.querySelectorAll('[data-date]')).toHaveLength(35);
  });

  it('separates uncovered months from the fixture explicitly marked unpublished', async () => {
    render(<MiniCalendar onSelect={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: '下个月' }));
    expect(screen.getByText('该月节假日与调休数据暂未载入。')).toBeVisible();
    expect(screen.queryByText('该年放假安排尚未公布')).not.toBeInTheDocument();
    for (let i = 0; i < 2; i++) await userEvent.click(screen.getByRole('button', { name: '下个月' }));
    expect(screen.getByText('该年放假安排尚未公布')).toBeVisible();
    expect(screen.queryByRole('button', { name: /法定假日/ })).not.toBeInTheDocument();
  });

  it.each(['2027-01-01', '2090-01-01'])('does not infer unpublished status from year %s', (today) => {
    render(<MonthCalendar today={today} source={unavailableCalendar} onSelect={vi.fn()} />);
    expect(screen.queryByText('该年放假安排尚未公布')).not.toBeInTheDocument();
    expect(screen.getByText(/尚未接入，当前仅显示公历/)).toBeVisible();
    expect(document.querySelector('.calendar-event')).toBeNull();
    expect(document.querySelector('.calendar-term')).toBeNull();
    expect(document.body.textContent).not.toContain('面试安排');
  });

  it('accepts published future coverage explicitly supplied by a source', () => {
    const source: CalendarSource = () => ({
      source: 'verified',
      holidayStatus: 'covered',
      notes: { '2030-01-01': { festivals: ['来源已核对节日'] } },
    });
    render(<MonthCalendar today="2030-01-01" source={source} />);
    expect(screen.getByRole('group', { name: '2030-01-01 来源已核对节日' })).toBeVisible();
    expect(screen.queryByText('该年放假安排尚未公布')).not.toBeInTheDocument();
    expect(screen.queryByText(/合成日历/)).not.toBeInTheDocument();
  });

  it('does not carry notes from the month into adjacent-month overflow cells', () => {
    const source: CalendarSource = () => ({
      source: 'synthetic',
      holidayStatus: 'covered',
      notes: { '2026-09-28': { arrangements: ['不属于本月'] } },
    });
    render(<MonthCalendar today="2026-10-17" source={source} />);
    expect(screen.getByRole('group', { name: '2026-09-28' })).toHaveClass('outside');
    expect(screen.queryByRole('img', { name: '不属于本月' })).not.toBeInTheDocument();
  });

  it('aligns leap February and cross-year months on Monday without using the host timezone', () => {
    const february = monthDays('2024-02');
    expect(february[0].date).toBe('2024-01-29');
    expect(february.filter((day) => day.inside)).toHaveLength(29);
    expect(february).toHaveLength(35);
    expect(monthDays('2027-01')[0].date).toBe('2026-12-28');
    expect(validDate('2024-02-29')).toBe(true);
    expect(validDate('2026-02-29')).toBe(false);
    expect(validDate('2026-13-01')).toBe(false);
    expect(dateLabel('2026-10-17', {})).toBe('2026-10-17');
  });
});

describe('today calendar placement and safe data source', () => {
  it('opens the mobile sheet and restores trigger focus without fetching or manufacturing arrangements', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch');
    render(<TodayCalendar today="2030-07-09" />);
    const trigger = screen.getByRole('button', { name: '查看本月日历' });
    expect(screen.queryByRole('region', { name: '2030年7月日历' })).not.toBeInTheDocument();
    await userEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: '本月日历' });
    expect(within(dialog).getByRole('region', { name: '2030年7月日历' })).toHaveAttribute(
      'data-calendar-source',
      'unavailable',
    );
    expect(within(dialog).getByRole('link', { name: '查看该日命盘' })).toHaveAttribute(
      'href',
      '#/chart?tab=bazi&date=2030-07-09',
    );
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('shows the inline desktop month, updates only its selected day, and links the exact chart date', async () => {
    viewport(true);
    render(<TodayCalendar today="2026-10-17" />);
    expect(screen.queryByRole('button', { name: '查看本月日历' })).not.toBeInTheDocument();
    const calendar = screen.getByRole('region', { name: '2026年10月日历' });
    await userEvent.click(within(calendar).getByRole('button', { name: /^2026-10-21 / }));
    expect(within(calendar).getByRole('button', { name: /^2026-10-17 / })).toHaveAttribute('aria-current', 'date');
    expect(screen.getByRole('link', { name: '查看该日命盘' })).toHaveAttribute(
      'href',
      '#/chart?tab=bazi&date=2026-10-21',
    );
    await userEvent.click(screen.getByRole('button', { name: '回到今天' }));
    expect(within(calendar).getByRole('button', { name: /^2026-10-17 / })).toHaveAttribute('aria-pressed', 'true');
  });

  it('marks the today preview explicitly synthetic and retains a term plus arrangement on the same date', () => {
    viewport(true);
    render(<TodayCalendar today="2026-10-17" source={todayExampleCalendar} />);
    const day = screen.getByRole('button', { name: /^2026-10-23 霜降 你的安排：合成复盘安排/ });
    expect(day.querySelector('.calendar-term')).toBeInTheDocument();
    expect(day.querySelector('.calendar-event')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '查看该日命盘' })).not.toBeInTheDocument();
    expect(screen.getByText(/选择不会改变排盘或保存安排/)).toBeVisible();
  });
});
