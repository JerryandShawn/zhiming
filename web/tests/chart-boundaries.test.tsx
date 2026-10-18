import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import LuckPeriods from '../src/charts/LuckPeriods';
import TimeBasis from '../src/charts/TimeBasis';
import { AstroData } from '../src/live/ChartData';
import { timeBasisDemo } from '../src/charts/demo';
import { list, object } from '../src/charts/data';

const decades = [
  {
    ganzhi: '甲子',
    legacy_start_year: 2026,
    legacy_end_year: 2026,
    nominal_start_at: '2026-01-01T00:00:00+08:00',
    nominal_end_exclusive: '2026-06-01T12:00:00+08:00',
  },
  {
    ganzhi: '乙丑',
    legacy_start_year: 2026,
    legacy_end_year: 2036,
    nominal_start_at: '2026-06-01T12:00:00+08:00',
    nominal_end_exclusive: '2036-06-01T12:00:00+08:00',
  },
];
const data = (sample?: string) => ({
  p8: {
    decade_luck: { decades },
    ...(sample !== undefined ? { calendar_layers: { day: { sample_at: sample } } } : {}),
  },
});

describe('P8 luck period timestamp boundaries', () => {
  it.each([
    ['2026-01-01T00:00:00+08:00', '甲子'],
    ['2026-06-01T11:59:59+08:00', '甲子'],
    ['2026-06-01T12:00:00+08:00', '乙丑'],
    ['2026-06-01T04:00:00Z', '乙丑'],
  ])('uses the returned sample %s and a half-open interval for %s', (sample, ganzhi) => {
    render(<LuckPeriods data={data(sample)} date="2026-12-31" />);
    expect(screen.getByRole('button', { name: `查看${ganzhi}大运解释` })).toHaveAttribute('aria-current', 'date');
    expect(document.querySelectorAll('[aria-current="date"]')).toHaveLength(1);
  });

  it('excludes the exact final end timestamp', () => {
    render(<LuckPeriods data={data('2036-06-01T12:00:00+08:00')} date="2036-01-01" />);
    expect(document.querySelector('[aria-current]')).not.toBeInTheDocument();
  });

  it.each([
    ['2026-05-31', '甲子'],
    ['2026-06-01', '乙丑'],
  ])('uses declared Beijing noon for date-only %s', (date, ganzhi) => {
    render(<LuckPeriods data={data()} date={date} />);
    expect(screen.getByText(/所选日期北京时间正午快照/)).toBeVisible();
    expect(screen.getByRole('button', { name: `查看${ganzhi}大运解释` })).toHaveAttribute('aria-current', 'date');
    expect(document.querySelectorAll('[aria-current="date"]')).toHaveLength(1);
  });

  it.each(['not-time', '2026-02-30T12:00:00+08:00', '2026-06-01T24:00:00+08:00', '2026-06-01T12:00:00'])(
    'does not fall back to a plausible year after invalid explicit sample %s',
    (sample) => {
      render(<LuckPeriods data={data(sample)} date="2026-07-01" />);
      expect(document.querySelector('[aria-current]')).not.toBeInTheDocument();
      expect(screen.getByText(/快照时间无效/)).toBeVisible();
    },
  );

  it('does not infer a period from legacy years when P8 timestamp bounds are invalid', () => {
    render(
      <LuckPeriods
        data={{ p8: { decade_luck: { decades: [{ ...decades[0], nominal_start_at: 'invalid' }] } } }}
        date="2026-03-01"
      />,
    );
    expect(document.querySelector('[aria-current]')).not.toBeInTheDocument();
  });
});

describe('safe chart comparisons and actual v3 aliases', () => {
  it.each([
    [undefined, undefined],
    [undefined, 'demo'],
    ['demo', undefined],
    ['', ''],
    [' ', ' '],
  ])('does not equate missing physical instant ids (%s, %s)', (primary, comparison) => {
    const value = structuredClone(timeBasisDemo);
    const charts = list(value.charts);
    object(charts[0].time_basis).instant_id = primary;
    object(charts[1].time_basis).instant_id = comparison;
    render(<TimeBasis data={value} />);
    expect(screen.queryByRole('heading', { name: '按北京时间则为' })).not.toBeInTheDocument();
  });

  it('describes palace, calendar and element differences while hiding birth dates and raw comparison prose', () => {
    const value = structuredClone(timeBasisDemo);
    const charts = list(value.charts);
    charts[1].data = structuredClone(charts[0].data);
    charts[1].ziwei_column = {
      ...object(charts[0].ziwei_column),
      wuxing_ju: '木三局',
      lunar_date: 'PRIVATE_LUNAR_DATE',
    };
    const comparison = list(object(value.interpretation).comparisons)[0];
    comparison.fields_changed = ['ziwei.palaces', 'ziwei.lunar_date', 'ziwei.wuxing_ju'];
    comparison.text = 'PRIVATE_RAW_COMPARISON';
    render(<TimeBasis data={value} />);
    expect(screen.getByText(/本次差异：十二宫配置不同；农历换算不同/)).toBeVisible();
    expect(screen.getByText('五行局：木三局')).toBeVisible();
    expect(document.body.textContent).not.toMatch(/PRIVATE_/);
  });

  it('marks unknown difference fields as unsupported without rendering their names or private values', () => {
    const value = structuredClone(timeBasisDemo);
    const comparison = list(object(value.interpretation).comparisons)[0];
    comparison.fields_changed = ['PRIVATE_FIELD', '__proto__'];
    comparison.text = 'PRIVATE_BODY';
    render(<TimeBasis data={value} />);
    expect(screen.getByText(/部分差异当前页暂不支持展示/)).toBeVisible();
    expect(document.body.textContent).not.toMatch(/PRIVATE_|__proto__/);
  });

  it('includes the actual v3 outer-planet names once and preserves aliases from older responses', () => {
    render(
      <AstroData
        data={{
          planets: Object.fromEntries(
            [
              '太阳',
              '月亮',
              '水星',
              '金星',
              '火星',
              '木星',
              '土星',
              '天王',
              '海王',
              '冥王',
              '天王星',
              '海王星',
              '冥王星',
            ].map((name) => [name, { sign: '白羊', deg: 1, longitude: 1, house: 1 }]),
          ),
        }}
      />,
    );
    expect(document.querySelectorAll('.list-row')).toHaveLength(10);
    for (const name of ['天王', '海王', '冥王']) expect(screen.getByText(new RegExp(`^${name} ·`))).toBeVisible();
  });
});
