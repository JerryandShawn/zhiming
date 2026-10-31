import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ZiweiPalaces from '../src/charts/ZiweiPalaces';
import AstroDiagram from '../src/charts/AstroDiagram';
import LuckPeriods from '../src/charts/LuckPeriods';
import TimeBasis from '../src/charts/TimeBasis';
import ChartDemo from '../src/charts/ChartDemo';
import { astroDemo, baziDemo, timeBasisDemo, ziweiDemo } from '../src/charts/demo';
import { list, object, wheelPoint } from '../src/charts/data';

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
beforeEach(() => {
  viewport(false);
  location.hash = '#/chart?tab=bazi';
});

describe('data-driven chart components', () => {
  it('places twelve returned palaces around the desktop perimeter, with the center free', () => {
    viewport(true);
    const shuffled = { ...ziweiDemo, palaces: [...list(ziweiDemo.palaces)].reverse() };
    const { container } = render(<ZiweiPalaces data={shuffled} date="2026-10-18" />);
    expect(container.querySelector('[data-palace-view]')).toHaveAttribute('data-palace-view', 'grid');
    expect(container.querySelectorAll('[data-palace-branch]')).toHaveLength(12);
    const checks = { 巳: ['1', '1'], 申: ['4', '1'], 亥: ['4', '4'], 寅: ['1', '4'], 子: ['3', '4'] };
    for (const [branch, [column, row]] of Object.entries(checks)) {
      const cell = container.querySelector<HTMLElement>(`[data-palace-branch="${branch}"]`)!;
      expect(cell.style.gridColumn).toBe(column);
      expect(cell.style.gridRow).toBe(row);
    }
    expect(container.querySelector('.chart-palace-center')).toHaveTextContent('命宫 子');
    expect(container.querySelector('.mutagen-忌 .icon')).toBeInTheDocument();
  });

  it('starts mobile in the expandable list and only switches to a grid when requested', async () => {
    const { container } = render(<ZiweiPalaces data={ziweiDemo} date="2026-10-18" />);
    expect(container.querySelector('[data-palace-view]')).toHaveAttribute('data-palace-view', 'list');
    expect(container.querySelectorAll('details')).toHaveLength(12);
    await userEvent.click(screen.getByText('命宫 · 甲子', { selector: 'summary' }));
    expect(screen.getByRole('button', { name: /^查看命宫宫位依据/ })).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '网格' }));
    expect(container.querySelector('[data-palace-view]')).toHaveAttribute('data-palace-view', 'grid');
    expect(screen.getByRole('button', { name: '宫位列表' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('does not invent missing palaces or fabricate a twelve-palace grid', () => {
    render(<ZiweiPalaces data={{ palaces: [{ name: '命宫', ganzhi: '甲子', major: [] }] }} date="2026-10-18" />);
    expect(screen.getByRole('button', { name: '网格' })).toBeDisabled();
    expect(screen.getByText(/宫位或地支数据不完整/)).toBeVisible();
    expect(document.querySelectorAll('details')).toHaveLength(1);
  });

  it('opens a palace explanation by keyboard and restores focus after Escape', async () => {
    viewport(true);
    render(<ZiweiPalaces data={ziweiDemo} date="2026-10-18" />);
    const trigger = screen.getByRole('button', { name: /^查看命宫宫位依据/ });
    expect(trigger).toHaveAccessibleName(/甲子/);
    expect(trigger).toHaveAccessibleName(/紫微/);
    trigger.focus();
    await userEvent.keyboard('{Enter}');
    const dialog = await screen.findByRole('dialog', { name: '命宫宫位依据' });
    expect(dialog).toHaveTextContent('紫微');
    expect(dialog).toHaveTextContent('三合');
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it('maps real longitude coordinates and aspect endpoints without an ornamental fixed triangle', () => {
    const data = {
      asc: { longitude: 0 },
      planets: { 太阳: { longitude: 0 }, 月亮: { longitude: 90 } },
      aspects: [{ from: '太阳', to: '月亮', aspect: '刑相', orb: 0 }],
      houses: [],
    };
    const { container } = render(<AstroDiagram data={data} />);
    const line = container.querySelector('line[data-aspect="太阳-月亮"]')!;
    expect(Number(line.getAttribute('x1'))).toBeCloseTo(88);
    expect(Number(line.getAttribute('y1'))).toBeCloseTo(200);
    expect(Number(line.getAttribute('x2'))).toBeCloseTo(200);
    expect(Number(line.getAttribute('y2'))).toBeCloseTo(312);
    expect(line).toHaveClass('tense');
    expect(container.querySelector('[data-planet="太阳"]')).toHaveAttribute('data-longitude', '0');
    expect(wheelPoint(0, 112, 90).x).toBeCloseTo(200);
    expect(wheelPoint(0, 112, 90).y).toBeCloseTo(88);
  });

  it('draws only returned valid houses and describes their missing coverage', () => {
    const { container } = render(<AstroDiagram data={{ ...astroDemo, houses: [{ house: 1, longitude: 13 }] }} />);
    expect(container.querySelectorAll('[data-house]')).toHaveLength(1);
    expect(screen.getByText(/宫头数据不完整/)).toBeVisible();
  });

  it('rejects non-finite, boolean and missing coordinates instead of inventing a wheel', () => {
    const { container } = render(
      <AstroDiagram
        data={{
          planets: { 太阳: { longitude: NaN }, 月亮: { longitude: true }, 水星: { longitude: Infinity }, 金星: {} },
        }}
      />,
    );
    expect(container.querySelector('svg.chart-astro-wheel')).not.toBeInTheDocument();
    expect(screen.getByText(/没有可用的星体黄经/)).toBeVisible();
  });

  it('does not infer unreturned aspects or draw an aspect whose endpoint is absent', async () => {
    const { container } = render(
      <AstroDiagram
        data={{
          planets: { 太阳: { longitude: 0 }, 月亮: { longitude: 90 } },
          aspects: [{ from: '太阳', to: '缺失星体', aspect: '刑相', orb: 0 }],
        }}
      />,
    );
    expect(container.querySelectorAll('[data-aspect]')).toHaveLength(0);
    await userEvent.click(screen.getByText('核对轮图角度与相位'));
    expect(screen.getByText(/缺少端点或类型/)).toBeVisible();
    expect(screen.getByText('太阳 刑相 缺失星体 · 容许度 0°')).toBeVisible();
  });

  it('opens each actual luck period with its original field selection, date and keyboard focus return', async () => {
    render(<LuckPeriods data={baziDemo} date="2026-10-18" />);
    const trigger = screen.getByRole('button', { name: /^查看戊辰大运解释/ });
    expect(trigger).toHaveAccessibleName(/2002–2011/);
    trigger.focus();
    await userEvent.keyboard('{Enter}');
    const dialog = await screen.findByRole('dialog', { name: '戊辰 · 大运依据' });
    expect(dialog).toHaveTextContent('2002–2011');
    expect(dialog).toHaveTextContent('不是这十年会发生什么的预测');
    const link = within(dialog).getByRole('link', { name: '带着这项依据问明镜' });
    const params = new URLSearchParams(link.getAttribute('href')!.split('?')[1]);
    expect(Object.fromEntries(params)).toEqual({
      system: 'bazi',
      key: 'dayun.0',
      focus: 'dayun.0',
      date: '2026-10-18',
    });
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it('labels a legacy year-only highlight as illustrative, without claiming an exact current period', () => {
    render(<LuckPeriods data={baziDemo} date="2026-10-18" />);
    expect(screen.getByRole('button', { name: /^查看庚午大运解释/ })).toHaveTextContent('所选年份示意');
    expect(screen.getByRole('button', { name: /^查看庚午大运解释/ })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('button', { name: /^查看戊辰大运解释/ })).not.toHaveAttribute('aria-current');
  });

  it('shows an explicit gap instead of generating missing luck periods', () => {
    render(<LuckPeriods data={{}} date="2026-10-18" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText(/没有返回大运分段/)).toBeVisible();
  });
});

describe('declared time-basis projection and synthetic separation', () => {
  it('uses the declared true-solar primary and only the matching Beijing comparison, without birth originals', () => {
    const data = structuredClone(timeBasisDemo);
    data.birth = { date: 'PRIVATE_BIRTH', reported_time: 'PRIVATE_CLOCK', place: 'PRIVATE_PLACE' };
    list(data.charts).forEach((chart) => {
      object(chart.time_basis).coordinate_datetime = 'PRIVATE_COORDINATE';
    });
    render(<TimeBasis data={data} />);
    expect(screen.getByRole('heading', { name: '真太阳时' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '按北京时间则为' })).toBeVisible();
    expect(screen.getByText(/时柱 甲辰/)).toBeVisible();
    expect(screen.getByText(/时柱 乙巳/)).toBeVisible();
    expect(document.body.textContent).not.toMatch(/PRIVATE_/);
  });

  it('does not show a Beijing duplicate when the readout reports no differences', () => {
    render(
      <TimeBasis
        data={{ ...timeBasisDemo, interpretation: { primary_chart_ids: ['demo:true_solar'], comparisons: [] } }}
      />,
    );
    expect(screen.queryByRole('heading', { name: '按北京时间则为' })).not.toBeInTheDocument();
    expect(screen.getByText(/未报告需要并列的北京时间差异/)).toBeVisible();
  });

  it('never compares two different physical instant candidates', () => {
    const data = structuredClone(timeBasisDemo);
    object(list(data.charts)[1].time_basis).instant_id = 'different-fold';
    render(<TimeBasis data={data} />);
    expect(screen.queryByRole('heading', { name: '按北京时间则为' })).not.toBeInTheDocument();
  });

  it('keeps all unresolved true-solar candidates and the physical-time confirmation warning', () => {
    const first = list(timeBasisDemo.charts)[0];
    const second = { ...first, id: 'fold2:true_solar', time_basis: { basis: 'true_solar', instant_id: 'fold2' } };
    render(
      <TimeBasis
        data={{
          charts: [first, second],
          interpretation: {
            primary_chart_ids: [first.id, second.id],
            physical_instant_confirmation_required: true,
            comparisons: [],
          },
        }}
      />,
    );
    expect(screen.getByRole('heading', { name: '真太阳时 · 候选 1' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '真太阳时 · 候选 2' })).toBeVisible();
    expect(screen.getByRole('status')).toHaveTextContent('默认口径不会替你选定一个真实时刻');
  });

  it('does not label a legacy mean-solar response as a full true-solar result', () => {
    render(
      <TimeBasis
        data={{
          time_basis: '地方平太阳时：仅经度修正，未计均时差；不是完整真太阳时',
          method: { equation_of_time_applied: false },
        }}
      />,
    );
    expect(screen.getByText(/当前响应尚未提供可核对/)).toBeVisible();
    expect(screen.getByText(/本次未应用均时差/)).toBeVisible();
    expect(screen.queryByRole('heading', { name: '真太阳时' })).not.toBeInTheDocument();
  });

  it('keeps the standalone demo explicitly synthetic and renders all three systems without fetching', async () => {
    const fetcher = vi.spyOn(globalThis, 'fetch');
    render(<ChartDemo />);
    expect(screen.getByText('合成盘面 · 组件演示')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '紫微' }));
    expect(screen.getByRole('region', { name: '紫微十二宫可视化' })).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '星盘' }));
    expect(screen.getByRole('img', { name: /本命星盘轮，10颗星体，5条已返回相位/ })).toBeVisible();
    expect(fetcher).not.toHaveBeenCalled();
  });
});
