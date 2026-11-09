import { describe, expect, it } from 'vitest';
import { chartSamples, readChartExample } from '../src/night/charts/port';
import { object } from '../src/charts/data';

describe('offline P8 chart sample projection', () => {
  it('keeps actual primary pillars and the explicit target noon snapshot', () => {
    const bazi = chartSamples.bazi.data;
    expect(object(object(bazi.pillars).year).ganzhi).toBe('甲戌');
    expect(object(object(bazi.pillars).day).ganzhi).toBe('丁酉');
    expect(object(object(object(bazi.p8).calendar_layers).day).sample_at).toBe('2026-10-19T12:00:00+08:00');
    expect(object(object(bazi.p8).decade_luck).decades).toHaveLength(10);
    const periods = object(object(bazi.p8).decade_luck).decades as Record<string, unknown>[];
    expect(
      periods.every((period) => period.nominal_start_at === undefined && period.nominal_end_exclusive === undefined),
    ).toBe(true);
  });
  it('keeps twelve real palaces and the chart rather than a substituted fixture', () => {
    expect(chartSamples.ziwei.data.palaces).toHaveLength(12);
    expect(chartSamples.ziwei.data).toMatchObject({ ming_gong: '亥', shen_gong: '未', wuxing_ju: '火六局' });
    expect(Object.keys(object(chartSamples.astro.data.planets))).toHaveLength(10);
    expect(chartSamples.astro.data.houses).toHaveLength(12);
    expect(chartSamples.astro.data.house_system).toBe('Placidus');
  });
  it.each(['bazi', 'ziwei', 'astro'] as const)(
    'keeps immutable %s data/hash/basis while excluding raw birth and alias ledgers',
    (tab) => {
      const sample = readChartExample(tab),
        serialized = JSON.stringify(sample);
      expect(sample).toBe(chartSamples[tab]);
      expect(Object.isFrozen(sample.data)).toBe(true);
      expect(sample.sourceSha256).toMatch(/^[a-f0-9]{64}$/);
      expect(object(sample.basis.interpretation).comparisons).toEqual([]);
      expect(object(sample.basis.time_basis).requires_confirmation).toBe(false);
      expect(serialized).not.toMatch(
        /1994-03-12|08:20|07:06|civil_time|utc_time|corrected_time|lunar_date|reported_time|physical_birth|owner_user_id|subject_id|aliases|"request"|"profile"/,
      );
      expect(object(sample.basis.interpretation).primary_chart_ids).toEqual(['time-chart-0dae00e864cc58abf97376b0']);
    },
  );
});
