import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import { cinnabarUsages } from './appearance';

const runId = process.env.MINGJING_DRAFT_ORGANIZE_RUN_ID ?? new Date().toISOString();
const batch = runId.replace(/[^a-zA-Z0-9-]/g, '-');
const evidence = path.resolve('evidence/2026-10-31/draft-organize');
const audits = path.resolve('test-results/draft-organize-evidence', batch, 'audits');

async function open(page: import('@playwright/test').Page, theme = 'light') {
  await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
  await page.goto('/?spaces=demo#/organize-draft');
  await expect(page.getByRole('heading', { name: '合成话题', exact: true })).toBeVisible();
}

test.beforeAll(async () => {
  await fs.mkdir(path.join(evidence, 'screenshots'), { recursive: true });
  await fs.mkdir(audits, { recursive: true });
});

test('审阅后仍显示 record_only 应用拒绝', async ({ page }) => {
  await open(page);
  await page.getByRole('button', { name: '审阅当前计划' }).click();
  await expect(page.getByText(/审阅凭证已签发/)).toBeVisible();
  await page.getByRole('button', { name: '核对应用资格' }).click();
  await expect(page.getByText('这项整理尚未开放自动应用。', { exact: true })).toBeVisible();
  await expect(page.getByText('应用已由程序回执确认。', { exact: true })).toHaveCount(0);
});

test('改名使旧审阅失效并需要重新审阅', async ({ page }) => {
  await open(page);
  await page.getByRole('textbox', { name: '话题名称' }).fill('新的审阅话题');
  await page.getByRole('button', { name: '保存改名' }).click();
  await expect(page.getByRole('heading', { name: '新的审阅话题', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '核对应用资格' })).toBeDisabled();
});

for (const viewport of [
  { width: 375, height: 812 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
])
  for (const theme of ['light', 'dark'])
    test(`draft organize ${theme} ${viewport.width}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      const outside: string[] = [],
        errors: string[] = [],
        consoleMessages: string[] = [];
      page.on('request', (request) => {
        const url = new URL(request.url());
        if (url.pathname.startsWith('/api/')) errors.push(`unexpected API ${url.pathname}`);
        if (['http:', 'https:'].includes(url.protocol) && url.origin !== 'http://127.0.0.1:4173')
          outside.push(url.origin);
      });
      page.on('pageerror', (error) => errors.push(error.message));
      page.on('console', (message) => {
        if (['warning', 'error'].includes(message.type())) consoleMessages.push(message.text());
      });
      await open(page, theme);
      await page.getByRole('button', { name: '审阅当前计划' }).click();
      await expect(page.getByText(/审阅凭证已签发/)).toBeVisible();
      await page.getByRole('button', { name: '核对应用资格' }).click();
      await expect(page.getByText('这项整理尚未开放自动应用。', { exact: true })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.waitForLoadState('networkidle');
      const visual = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > innerWidth,
        small_text: Array.from(document.querySelectorAll('main *'))
          .filter(
            (element) =>
              element instanceof HTMLElement &&
              Array.from(element.childNodes).some((node) => node.nodeType === 3 && node.textContent?.trim()) &&
              element.getBoundingClientRect().width > 0 &&
              getComputedStyle(element).display !== 'none' &&
              parseFloat(getComputedStyle(element).fontSize) < 13,
          )
          .map((element) => element.className),
      }));
      const cinnabar = await page.evaluate(cinnabarUsages);
      const axe = await new AxeBuilder({ page }).analyze();
      await page.evaluate(() =>
        document.activeElement instanceof HTMLElement ? document.activeElement.blur() : undefined,
      );
      const filename = `organize-${theme}-${viewport.width}`;
      await page.screenshot({
        path: path.join(evidence, 'screenshots', `${filename}.png`),
        fullPage: true,
        animations: 'disabled',
      });
      await fs.writeFile(
        path.join(audits, `${filename}.json`),
        JSON.stringify(
          {
            run_id: runId,
            theme,
            viewport,
            overflow: visual.overflow,
            small_text: visual.small_text,
            cinnabar_uses: cinnabar,
            outside_requests: outside,
            page_errors: errors,
            console_messages: consoleMessages,
            violations: axe.violations,
          },
          null,
          2,
        ) + '\n',
      );
      expect.soft(visual.overflow).toBe(false);
      expect.soft(visual.small_text).toEqual([]);
      expect.soft(cinnabar.length).toBeLessThanOrEqual(3);
      expect.soft(outside).toEqual([]);
      expect.soft(errors).toEqual([]);
      expect.soft(consoleMessages).toEqual([]);
      expect.soft(axe.violations).toEqual([]);
    });
