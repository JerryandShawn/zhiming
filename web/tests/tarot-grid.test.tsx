import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CardPicker } from '../src/components/TarotCards';
import { CardBackGrid } from '../src/tarot/CardBackGrid';
import { nextBackIndex } from '../src/tarot/keyboard';

beforeEach(() => {
  vi.mocked(window.matchMedia).mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
});

describe('physical tarot grid navigation', () => {
  it.each([6, 13])('keeps columns intact around selected holes with %i columns', (columns) => {
    const locked = Array.from({ length: 78 }, (_, index) => index === 1 || index === columns);
    expect(nextBackIndex(0, 'ArrowDown', columns, locked)).toBe(columns * 2);
    expect(nextBackIndex(columns * 2, 'ArrowUp', columns, locked)).toBe(0);
    expect(nextBackIndex(2, 'ArrowDown', columns, locked)).toBe(columns + 2);
    expect(nextBackIndex(0, 'ArrowRight', columns, locked)).toBe(2);
  });

  it('holds at deck boundaries, skips locked ends and does not process unrelated keys', () => {
    const locked = Array.from({ length: 78 }, (_, index) => index === 0 || index === 77);
    expect(nextBackIndex(1, 'Home', 6, locked)).toBe(1);
    expect(nextBackIndex(1, 'End', 6, locked)).toBe(76);
    expect(nextBackIndex(1, 'ArrowUp', 6, locked)).toBe(1);
    expect(nextBackIndex(76, 'ArrowDown', 6, locked)).toBe(76);
    expect(nextBackIndex(7, 'Enter', 6, locked)).toBe(7);
  });

  it('locks selected cards, keeps one tab stop and sends only the chosen opaque identity', async () => {
    const select = vi.fn();
    render(
      <CardBackGrid
        backs={Array.from({ length: 78 }, (_, index) => ({
          id: `opaque-${index}`,
          label: `牌背${index + 1}`,
          selected: index === 1 || index === 6,
        }))}
        onSelect={select}
      />,
    );
    expect(screen.getAllByRole('button')).toHaveLength(78);
    expect(document.querySelectorAll('.tarot-picker button[tabindex="0"]')).toHaveLength(1);
    expect(screen.getByRole('button', { name: '牌背2' })).toBeDisabled();
    screen.getByRole('button', { name: '牌背1' }).focus();
    await userEvent.keyboard('{ArrowDown}');
    expect(screen.getByRole('button', { name: '牌背13' })).toHaveFocus();
    await userEvent.keyboard('{Enter}');
    expect(select).toHaveBeenCalledExactlyOnceWith('opaque-12');
    expect(document.querySelectorAll('img')).toHaveLength(78);
    expect(document.querySelector('img:not([src="/static/tarot/back.svg"])')).toBeNull();
  });

  it('uses desktop 13-column movement rather than the compacted list of enabled buttons', async () => {
    vi.mocked(window.matchMedia).mockImplementation((query) => ({
      matches: query === '(min-width: 1024px)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    render(<CardPicker selected={[1]} onChange={vi.fn()} />);
    screen.getByRole('button', { name: '第1张牌' }).focus();
    await userEvent.keyboard('{ArrowDown}');
    expect(screen.getByRole('button', { name: '第14张牌' })).toHaveFocus();
  });

  it('continues after a local selection without allowing duplicates or more than the spread count', async () => {
    render(<CardPicker count={3} />);
    await userEvent.click(screen.getByRole('button', { name: '第1张牌' }));
    expect(screen.getByRole('button', { name: '第1张牌' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '第2张牌' })).toHaveFocus();
    await userEvent.keyboard('{Enter}{Enter}');
    expect(screen.getByRole('status')).toHaveTextContent('已选 3 / 3');
    const grid = screen.getByRole('group', { name: '亲手点选牌背' });
    expect(grid).toHaveFocus();
    expect(Array.from(grid.querySelectorAll('button')).every((button) => button.disabled)).toBe(true);
  });

  it('returns to the same unconfirmed choice after a failed pending write', async () => {
    const backs = [{ id: 'opaque-A', label: '第一张', selected: false }];
    const select = vi.fn();
    const view = render(<CardBackGrid backs={backs} onSelect={select} />);
    await userEvent.click(screen.getByRole('button', { name: '第一张' }));
    view.rerender(<CardBackGrid backs={backs} onSelect={select} disabled />);
    view.rerender(<CardBackGrid backs={backs} onSelect={select} />);
    expect(screen.getByRole('button', { name: '第一张' })).toHaveFocus();
    expect(select).toHaveBeenCalledTimes(1);
  });
});
