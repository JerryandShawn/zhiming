import type { ComponentProps } from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ElementComparison } from '../src/tools/ElementComparison';
import { countedTools } from './tools-form-test-fixtures';

type Visible = NonNullable<ComponentProps<typeof ElementComparison>['a']>;
const order = ['木', '火', '土', '金', '水'];
const expected = { a: [3, 2, 2, 1, 0], b: [3, 0, 1, 2, 2] } as const;
function cell(region: HTMLElement, element: string, side: 'a' | 'b') {
  const value = region.querySelector<HTMLElement>(`tr[data-element="${element}"] td[data-side="${side}"]`);
  expect(value).not.toBeNull();
  return value!;
}

describe('real public synastry occurrence counts are displayed without a new score', () => {
  it('shows all ten original counts, including both actual zeros and accessible headers', () => {
    const sample = countedTools().synastry;
    render(<ElementComparison a={sample.data.bazi.visible_a} b={sample.data.bazi.visible_b} />);
    const region = screen.getByRole('region', { name: '双方表层五行计数' });
    expect(within(region).getByRole('table', { name: '已返回的表层出现次数' })).toBeVisible();
    expect(
      within(region)
        .getAllByRole('columnheader')
        .map((node) => node.textContent),
    ).toEqual(['五行', 'A方计数', 'B方计数']);
    expect(region.querySelectorAll('tbody tr')).toHaveLength(5);
    for (const [index, element] of order.entries()) {
      expect(within(region).getByRole('rowheader', { name: element })).toBeVisible();
      for (const side of ['a', 'b'] as const) {
        const count = cell(region, element, side);
        expect(count).toHaveTextContent(String(expected[side][index]));
        expect(count.querySelector('data')).toHaveAttribute('value', String(expected[side][index]));
        expect(count).not.toHaveTextContent('未返回');
      }
    }
  });

  it('does not change original stems/counts or add a total, percentage, strength or compatibility display', () => {
    const sample = countedTools().synastry,
      before = structuredClone(sample);
    const { container } = render(<ElementComparison a={sample.data.bazi.visible_a} b={sample.data.bazi.visible_b} />);
    expect(sample).toEqual(before);
    expect(sample.data.bazi.visible_a.stems).toEqual(['甲', '戊', '丁', '乙', '丁', '辛', '甲', '戊']);
    expect(sample.data.bazi.visible_b.stems).toEqual(['乙', '壬', '甲', '庚', '庚', '甲', '癸', '己']);
    expect(container.querySelectorAll('data')).toHaveLength(10);
    expect(container.querySelector('meter,progress,[role="meter"],[role="progressbar"]')).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\d+(?:\.\d+)?[%％]/);
    expect(screen.getByText(/不代表气量、旺衰、喜忌或关系适配，也不合计为总分/)).toBeVisible();
    const region = screen.getByRole('region', { name: '双方表层五行计数' });
    const ids = region.getAttribute('aria-describedby')!.split(/\s+/);
    expect(ids.every((id) => document.getElementById(id))).toBe(true);
  });
});

describe('pure UI missing-value constructions, never sent to a P8 port', () => {
  it('leaves a missing side unavailable instead of copying the other side or filling zero', () => {
    const b = countedTools().synastry.data.bazi.visible_b;
    render(<ElementComparison b={b} />);
    const region = screen.getByRole('region', { name: '双方表层五行计数' });
    for (const element of order) {
      expect(cell(region, element, 'a')).toHaveTextContent('未返回可用值');
      expect(cell(region, element, 'a').querySelector('data')).toBeNull();
      expect(cell(region, element, 'b').querySelector('data')).toHaveAttribute(
        'value',
        String(b.element_counts[element]),
      );
    }
  });

  it('keeps missing, NaN, negative and fractional UI values distinct from an actual zero', () => {
    // Deliberately incomplete UI props only; this is not a scientific response or catalog sample.
    const uiOnly: Visible = {
      stems: [],
      element_counts: { 火: 0, 土: NaN, 金: -1, 水: 0.5 },
      qi_strength_assessed: false,
    };
    const b = countedTools().synastry.data.bazi.visible_b;
    render(<ElementComparison a={uiOnly} b={b} />);
    const region = screen.getByRole('region', { name: '双方表层五行计数' });
    for (const element of ['木', '土', '金', '水']) {
      expect(cell(region, element, 'a')).toHaveTextContent('未返回可用值');
      expect(cell(region, element, 'a').querySelector('data')).toBeNull();
    }
    expect(cell(region, '火', 'a').querySelector('data')).toHaveAttribute('value', '0');
    expect(cell(region, '火', 'b').querySelector('data')).toHaveAttribute('value', '0');
  });

  it('does not invent missing element rows or an all-zero table', () => {
    const a: Visible = { stems: [], element_counts: { 木: 3 }, qi_strength_assessed: false };
    const b: Visible = { stems: [], element_counts: { 金: 2 }, qi_strength_assessed: false };
    const mounted = render(<ElementComparison a={a} b={b} />);
    const region = screen.getByRole('region', { name: '双方表层五行计数' });
    expect([...region.querySelectorAll('tbody tr')].map((row) => row.getAttribute('data-element'))).toEqual([
      '木',
      '金',
    ]);
    mounted.rerender(<ElementComparison />);
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('当前没有返回可对照的五行计数，不补成全0。');
    expect(mounted.container.querySelector('data')).not.toBeInTheDocument();
  });
});
