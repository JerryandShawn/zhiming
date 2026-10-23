import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import SampleChartPage from '../src/night/charts/SampleChartPage';
import { chartSamples } from '../src/night/charts/port';
import { object } from '../src/charts/data';

beforeEach(() => history.replaceState(null, '', '/?night=demo#/chart'));

it('renders the computed Bazi sample with a fixed offline disclaimer and a verifiable source', () => {
  const fetch = vi.spyOn(globalThis, 'fetch');
  render(<SampleChartPage />);
  expect(screen.getByRole('heading', { name: '阿远 · 合成画像计算样例' })).toBeInTheDocument();
  expect(screen.getByText(/固定离线结果，不是你的档案/)).toBeInTheDocument();
  expect(document.querySelectorAll('.pillars .pillar')).toHaveLength(4);
  expect(document.querySelector('[data-runtime="night-chart-samples"]')).toHaveAttribute(
    'data-source-sha256',
    chartSamples.bazi.sourceSha256,
  );
  expect(chartSamples.bazi.sourceSha256).toMatch(/^[0-9a-f]{64}$/);
  expect(screen.getByText(/日主：/)).toHaveTextContent(String(object(object(chartSamples.bazi.data.pillars).day).gan));
  expect(document.querySelectorAll('.chart-luck-period').length).toBeGreaterThan(0);
  expect(
    screen.getByText('当前预览只展示安全的年龄与年份，精确交运时分暂不展示，也不据此标记精确所属运段。'),
  ).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

it('switches to the sample twelve palaces rather than a fabricated replacement', async () => {
  render(<SampleChartPage />);
  await userEvent.click(screen.getByRole('button', { name: '紫微' }));
  expect(screen.getByRole('region', { name: '紫微十二宫可视化' })).toBeInTheDocument();
  expect(document.querySelector('[data-runtime="night-chart-samples"]')).toHaveAttribute('data-chart-system', 'ziwei');
  expect(document.querySelectorAll('.chart-palace-list > *')).toHaveLength(12);
  expect(document.querySelector('.pillars')).not.toBeInTheDocument();
});

it('uses returned planet longitudes to render an actual wheel and carries the source hash per system', async () => {
  render(<SampleChartPage />);
  await userEvent.click(screen.getByRole('button', { name: '星盘' }));
  expect(screen.getByRole('region', { name: '星盘角度可视化' })).toBeInTheDocument();
  expect(document.querySelector('svg.chart-astro-wheel')).toBeInTheDocument();
  expect(document.querySelectorAll('[data-planet]').length).toBeGreaterThan(0);
  expect(document.querySelector('[data-runtime="night-chart-samples"]')).toHaveAttribute(
    'data-source-sha256',
    chartSamples.astro.sourceSha256,
  );
});

it('does not manufacture a Beijing difference or expose a raw birth field from the source projection', () => {
  render(<SampleChartPage />);
  expect(screen.getByRole('region', { name: '时辰口径核对' })).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: '按北京时间则为' })).not.toBeInTheDocument();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/birth\.solar_datetime|birth\.location|solar_datetime/);
  expect(screen.getByRole('region', { name: '本页展示范围' })).toHaveTextContent('未展示的能力仍需另行核对');
});

it('honors chart deep links, keeps query parameters and follows same-page tab navigation', async () => {
  history.replaceState(null, '', '/?night=demo#/chart?tab=astro&date=2026-10-19');
  render(<SampleChartPage />);
  expect(document.querySelector('[data-chart-system]')).toHaveAttribute('data-chart-system', 'astro');
  await userEvent.click(screen.getByRole('button', { name: '八字' }));
  expect(location.hash).toContain('tab=bazi');
  expect(location.hash).toContain('date=2026-10-19');
  await act(async () => {
    location.hash = '/chart?tab=ziwei';
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
  expect(document.querySelector('[data-chart-system]')).toHaveAttribute('data-chart-system', 'ziwei');
});
