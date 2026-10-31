import { expect, test, type Page, type TestInfo } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { assertNightQuiet, auditNight, guardNight } from './night-helpers';

const sourceDocument = 'tool-469316cf15ee75cfd4f7f6ad9f61fc38a84e758372cc045ba5a3cf8a8b5cc2d2';
const counts = { a: [3, 2, 2, 1, 0], b: [3, 0, 1, 2, 2] } as const;
const elements = ['木', '火', '土', '金', '水'];
async function approve(page: Page) {
  await page.getByRole('checkbox', { name: '允许本次展示A方合成盘面', exact: true }).check();
  await page.getByRole('checkbox', { name: '允许本次展示B方合成盘面', exact: true }).check();
}
async function capture(page: Page, width: number, info: TestInfo) {
  await page.evaluate(() => window.scrollTo(0, 0));
  const directory = process.env.NIGHT_EVIDENCE_DIR ?? 'evidence/2026-10-21/tools-elements';
  await fs.mkdir(directory, { recursive: true });
  const file = path.join(directory, `synastry-elements-${width}.png`);
  await fs.writeFile(file, await page.screenshot({ fullPage: true, animations: 'disabled' }), { flag: 'wx' });
  info.annotations.push({ type: 'tool_elements_screenshot', description: file.replaceAll('\\', '/') });
  info.annotations.push({ type: 'published_document', description: sourceDocument });
}

test.beforeEach(async ({ page }) => {
  guardNight(page);
  await page.clock.setFixedTime(new Date('2026-10-21T08:00:00+08:00'));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (
      ['http:', 'https:'].includes(url.protocol) &&
      (url.origin !== 'http://127.0.0.1:4173' || /^\/(?:api|__test__|__frontend_fixture__)(?:\/|$)/.test(url.pathname))
    )
      await route.abort();
    else await route.continue();
  });
});
test.afterEach(({ page }) => assertNightQuiet(page));

for (const width of [390, 1440]) {
  test(`真实公开合盘计数、原分项依据和撤回 ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(
      (theme) => localStorage.setItem('mingjing-theme', theme),
      width === 390 ? 'dark' : 'light',
    );
    await page.goto('/?tools=demo#/chart?tool=synastry');
    const read = page.getByRole('button', { name: '查看已确认的样例', exact: true });
    await expect(read).toBeDisabled();
    await expect(page.getByRole('heading', { name: '表层五行计数', exact: true })).toHaveCount(0);
    await approve(page);
    await expect(page.getByRole('region', { name: '双方表层五行计数', exact: true })).toHaveCount(0);
    await read.click();
    const result = page.locator(`[data-tool-document="${sourceDocument}"]`);
    await expect(result).toBeVisible();
    const region = result.getByRole('region', { name: '双方表层五行计数', exact: true });
    await expect(region).toBeVisible();
    await expect(region.getByRole('table', { name: '已返回的表层出现次数', exact: true })).toBeVisible();
    await expect(region.locator('tbody tr')).toHaveCount(5);
    for (const [index, element] of elements.entries())
      for (const side of ['a', 'b'] as const) {
        const cell = region.locator(`tr[data-element="${element}"] td[data-side="${side}"]`);
        await expect(cell).toHaveText(String(counts[side][index]));
        await expect(cell.locator('data')).toHaveAttribute('value', String(counts[side][index]));
      }
    const occurrenceSection = result.locator('.tool-elements');
    await expect(occurrenceSection).toContainText('不代表气量、旺衰、喜忌或关系适配，也不合计为总分');
    await expect(occurrenceSection.locator('meter,progress,[role="meter"],[role="progressbar"]')).toHaveCount(0);
    await expect(result.getByRole('region', { name: 'A方盘面', exact: true }).locator('.tool-pillars dd')).toHaveText([
      '甲戌',
      '丁卯',
      '丁酉',
      '甲辰',
    ]);
    await expect(result.getByRole('region', { name: 'B方盘面', exact: true }).locator('.tool-pillars dd')).toHaveText([
      '乙亥',
      '甲申',
      '庚寅',
      '癸未',
    ]);
    const candidateSummary = result.getByText('表层元素与三种候选路径', { exact: true });
    await candidateSummary.click();
    const candidates = candidateSummary.locator('..');
    await expect(candidates).toContainText('对方透干 乙、甲、庚、癸');
    await expect(candidates).toContainText('对方透干 甲、丁、丁、甲');
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await auditNight(page);
    await capture(page, width, info);

    await result.getByText('本结果的公开依据', { exact: true }).click();
    await expect(result.locator('.tool-evidence-row')).toHaveCount(113);
    const evidence = result
      .locator('.tool-evidence-row')
      .first()
      .getByRole('button', { name: '依据〔c1〕', exact: true });
    await evidence.click();
    const dialog = page.getByRole('dialog', { name: '本结果依据〔c1〕', exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText('A方海王与B方火星刑相，误差0.0232°。');
    await expect(dialog).not.toContainText('2026-10-21 · 三合');
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(evidence).toBeFocused();
    await page.getByRole('button', { name: '撤回本次展示', exact: true }).click();
    await expect(page.locator('[data-tool-document]')).toHaveCount(0);
    await expect(page.getByRole('region', { name: '双方表层五行计数', exact: true })).toHaveCount(0);
    await expect(page.getByRole('checkbox', { name: '允许本次展示A方合成盘面', exact: true })).not.toBeChecked();
    await expect(page.getByRole('checkbox', { name: '允许本次展示B方合成盘面', exact: true })).not.toBeChecked();

    await approve(page);
    await read.click();
    await expect(region).toBeVisible();
    await page.getByRole('textbox', { name: '统一相位容许度（度）', exact: true }).fill('0');
    await expect(page.locator('[data-tool-document]')).toHaveCount(0);
    await expect(read).toBeDisabled();
    await approve(page);
    await read.click();
    await expect(page.locator('[data-published-state="unavailable"]')).toBeVisible();
    await expect(page.getByRole('heading', { name: '表层五行计数', exact: true })).toHaveCount(0);
    await expect(page.locator('[data-tool-document]')).toHaveCount(0);
    await expect(page.locator('[aria-invalid="true"]')).toHaveCount(0);
    await auditNight(page);
  });
}
