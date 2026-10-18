import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import { cinnabarUsages } from './appearance';

const evidence = path.resolve('../docs/v4/evidence/P10');
const pages = ['today', 'chat', 'chart', 'tarot', 'cases', 'me', 'settings'];
const viewports = [
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
];

for (const viewport of viewports)
  for (const theme of ['light', 'dark'])
    for (const name of pages) {
      test(`${name} ${theme} ${viewport.width}`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
        const outside: string[] = [];
        const api: string[] = [];
        const errors: string[] = [];
        page.on('request', (request) => {
          const url = new URL(request.url());
          if (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
            outside.push(url.hostname);
          if (url.pathname.startsWith('/api/')) api.push(url.pathname);
        });
        page.on('pageerror', (error) => errors.push(error.name));
        await page.goto(`/#/${name}`);
        await expect(page.locator(`[data-page="${name}"]`)).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
        const audit = await page.evaluate(() => ({
          overflow: document.documentElement.scrollWidth > innerWidth,
          fontFaces: document.fonts.size,
          smallText: Array.from(document.querySelectorAll('main *'))
            .filter(
              (element) =>
                element instanceof HTMLElement &&
                Array.from(element.childNodes).some((node) => node.nodeType === 3 && node.textContent?.trim()) &&
                element.getBoundingClientRect().width > 0 &&
                getComputedStyle(element).display !== 'none' &&
                parseFloat(getComputedStyle(element).fontSize) < 13 &&
                !element.closest('.citation, .calendar-mark, .calendar-festival'),
            )
            .map((element) => element.className),
        }));
        const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
        const cinnabar = await page.evaluate(cinnabarUsages);
        const filename = `${name}-${theme}-${viewport.width}`;
        await fs.mkdir(path.join(evidence, 'screenshots'), { recursive: true });
        await fs.mkdir(path.join(evidence, 'audits'), { recursive: true });
        await page.screenshot({ path: path.join(evidence, 'screenshots', filename + '.png'), animations: 'disabled' });
        await fs.writeFile(
          path.join(evidence, 'audits', filename + '.json'),
          JSON.stringify(
            {
              page: name,
              theme,
              viewport,
              ...audit,
              cinnabar_uses: cinnabar,
              outside_requests: outside,
              api_requests: api,
              page_errors: errors,
              violations: accessibility.violations.map((violation) => ({
                id: violation.id,
                impact: violation.impact,
                nodes: violation.nodes.map((node) => ({ target: node.target, summary: node.failureSummary })),
              })),
            },
            null,
            2,
          ) + '\n',
        );
        expect(outside).toEqual([]);
        expect(api).toEqual([]);
        expect(errors).toEqual([]);
        expect(audit.overflow).toBe(false);
        expect(audit.smallText).toEqual([]);
        expect(audit.fontFaces).toBeGreaterThan(0);
        expect(cinnabar.length).toBeLessThanOrEqual(3);
        expect(accessibility.violations).toEqual([]);
      });
    }

test('component showcase, keyboard, themes, and old deep links', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/#/__design');
  await expect(page.getByRole('heading', { name: '组件一览' }).last()).toBeVisible();
  await page.getByRole('button', { name: '打开对话框' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: '打开对话框' })).toBeFocused();
  await page.getByRole('button', { name: '打开抽屉' }).click();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: '打开抽屉' })).toBeFocused();
  await page.getByRole('button', { name: '我自己说' }).click();
  await expect(page.getByRole('textbox', { name: '和明镜说说' })).toBeFocused();
  for (const [old, target] of [
    ['memory', 'me'],
    ['timeline', 'me'],
    ['graph', 'me'],
    ['dict', 'me'],
    ['reportsettings', 'settings'],
    ['reports?date=2026-10-17', 'settings'],
  ]) {
    await page.goto(`/#/${old}`);
    await expect(page.locator(`[data-page="${target}"]`)).toBeVisible();
  }
  await page.goto('/#/settings');
  await page.getByRole('button', { name: '夜墨', exact: true }).click();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
});

test('three chart systems and fixed tarot selection remain keyboard operable', async ({ page }) => {
  await page.goto('/#/chart');
  await page.getByRole('button', { name: '紫微', exact: true }).click();
  await expect(page.getByRole('heading', { name: '十二宫' })).toBeVisible();
  await page.getByRole('button', { name: '星盘', exact: true }).click();
  await expect(page.getByRole('img', { name: '合成星盘示意' })).toBeVisible();
  await page.goto('/#/tarot');
  await page.getByRole('button', { name: '选牌', exact: true }).click();
  await page.getByRole('button', { name: '第1张牌', exact: true }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('button', { name: '第2张牌', exact: true })).toBeFocused();
  await page.keyboard.press('Space');
  await expect(page.getByRole('status')).toContainText('已选 1 / 3');
  await page.getByRole('button', { name: '揭牌', exact: true }).click();
  await expect(page.getByRole('img', { name: '不透明的塔罗牌背' })).toHaveCount(3);
  await page.getByRole('button', { name: '全部揭开' }).click();
  await expect(page.getByRole('img', { name: '星星正位' })).toBeVisible();
});
