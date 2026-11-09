import { expect, test } from '@playwright/test';
import { assertNightQuiet, auditNight, captureNight, guardNight, openNight } from './night-helpers';

const systems = [
  ['bazi', '八字'],
  ['ziwei', '紫微'],
  ['astro', '星盘'],
] as const;
test.beforeEach(({ page }) => guardNight(page));
test.afterEach(({ page }) => assertNightQuiet(page));

for (const [system, label] of systems)
  for (const width of [390, 1440])
    for (const theme of ['light', 'dark']) {
      test(`P8离线样例 ${system} ${width} ${theme}`, async ({ page }) => {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
        await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
        await openNight(page, 'chart');
        const root = page.locator('[data-runtime="night-chart-samples"]');
        await root.getByRole('group', { name: '命盘体系' }).getByRole('button', { name: label, exact: true }).click();
        await expect(root).toHaveAttribute('data-chart-system', system);
        await expect(root).toHaveAttribute('data-source-sha256', /^[a-f0-9]{64}$/);
        await expect(root).toContainText('固定离线结果，不是你的档案');
        await expect(root).toContainText('真太阳时');
        await expect(root.getByRole('heading', { name: '按北京时间则为', exact: true })).toHaveCount(0);
        if (system === 'bazi') {
          await expect(root.locator('.pillars article.pillar')).toHaveCount(4);
          for (const [name, value] of [
            ['年柱', '甲戌'],
            ['月柱', '丁卯'],
            ['日柱', '丁酉'],
            ['时柱', '甲辰'],
          ])
            await expect(root.getByRole('button', { name: `查看${name}${value}依据`, exact: true })).toBeVisible();
          await expect(root.locator('.chart-luck-period')).toHaveCount(10);
          await expect(root.getByRole('heading', { name: '大运 · 逐步查看', exact: true })).toBeVisible();
        }
        if (system === 'ziwei') {
          const palaces = root.getByRole('region', { name: '紫微十二宫可视化', exact: true });
          if (width === 390) {
            await expect(palaces.locator('[data-palace-view="list"] details')).toHaveCount(12);
            await expect(palaces.getByRole('button', { name: '网格', exact: true })).toBeVisible();
          } else {
            const cells = palaces.locator('[data-palace-branch]');
            await expect(cells).toHaveCount(12);
            const coordinates = await cells.evaluateAll((elements) =>
              elements.map((element) => {
                const style = getComputedStyle(element);
                return `${style.gridColumnStart}:${style.gridRowStart}`;
              }),
            );
            expect(new Set(coordinates).size).toBe(12);
            expect(coordinates).not.toEqual(expect.arrayContaining(['2:2', '3:2', '2:3', '3:3']));
          }
          await expect(root).toContainText('火六局');
        }
        if (system === 'astro') {
          const wheel = root.locator('svg.chart-astro-wheel');
          await expect(wheel).toBeVisible();
          await expect(wheel.locator('[data-planet]')).toHaveCount(10);
          await expect(wheel.locator('[data-house]')).toHaveCount(12);
          await expect(wheel.locator('[data-aspect]')).toHaveCount(11);
          await expect(wheel.locator('[data-planet="太阳"]')).toHaveAttribute('data-longitude', '351.19654');
          const geometry = await wheel.evaluate((svg) => {
            const planets = new Map(
              Array.from(svg.querySelectorAll('[data-planet]')).map((node) => {
                const dot = node.querySelector('circle')!;
                return [
                  node.getAttribute('data-planet')!,
                  [Number(dot.getAttribute('cx')), Number(dot.getAttribute('cy'))],
                ];
              }),
            );
            return Array.from(svg.querySelectorAll('[data-aspect]')).map((line) => {
              const [from, to] = line.getAttribute('data-aspect')!.split('-');
              return {
                from: planets.get(from),
                to: planets.get(to),
                start: [Number(line.getAttribute('x1')), Number(line.getAttribute('y1'))],
                end: [Number(line.getAttribute('x2')), Number(line.getAttribute('y2'))],
              };
            });
          });
          for (const line of geometry) {
            expect(line.from).toBeDefined();
            expect(line.to).toBeDefined();
            expect(line.start[0]).toBeCloseTo(line.from![0], 4);
            expect(line.start[1]).toBeCloseTo(line.from![1], 4);
            expect(line.end[0]).toBeCloseTo(line.to![0], 4);
            expect(line.end[1]).toBeCloseTo(line.to![1], 4);
          }
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await auditNight(page);
        await captureNight(page, `06-chart-${system}-${width}-${theme}`, true);
      });
    }
