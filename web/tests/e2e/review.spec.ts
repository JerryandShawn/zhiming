import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import { cinnabarUsages } from './appearance';

const evidence = path.resolve('test-results/static-evidence/review-2026-10-18');

for (const width of [375, 390, 768, 1440])
  for (const theme of ['light', 'dark']) {
    test(`reviewed layout and calendar ${theme} ${width}`, async ({ page }) => {
      await fs.mkdir(evidence, { recursive: true });
      await page.setViewportSize({
        width,
        height: width === 1440 ? 900 : width === 768 ? 1024 : width === 390 ? 844 : 812,
      });
      await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
      await page.goto('/?preview=1#/today');
      const row = page.locator('.event-row').first();
      const layout = await row.evaluate((element) => {
        const [date, name, tag] = Array.from(element.children);
        name.textContent = '这是一个很长的事项名称，空间不足时只有事项名应截断'.repeat(3);
        return {
          row: element.getBoundingClientRect().toJSON(),
          date: date.getBoundingClientRect().toJSON(),
          name: name.getBoundingClientRect().toJSON(),
          tag: tag.getBoundingClientRect().toJSON(),
          truncated: name.scrollWidth > name.clientWidth,
          overflow: getComputedStyle(name).textOverflow,
        };
      });
      expect(Math.abs(layout.date.top - layout.tag.top)).toBeLessThan(5);
      expect(layout.tag.right).toBeCloseTo(layout.row.right, 0);
      expect(layout.name.right).toBeLessThan(layout.tag.left);
      expect(layout.truncated).toBe(true);
      expect(layout.overflow).toBe('ellipsis');
      await page.goto('/?preview=1#/chart');
      const trigger = page.getByRole('button', { name: /看哪一天：/ });
      await expect(trigger).toHaveText(/看哪一天：今天 10月17日/);
      await trigger.click();
      const dialog = page.getByRole('dialog', { name: '选择查看日期' });
      await expect(dialog).toBeVisible();
      await expect(dialog.locator('.calendar-day')).toHaveCount(35);
      await expect(dialog.getByRole('button', { name: /^2026-10-01 法定假日 国庆/ })).toBeVisible();
      await expect(dialog.getByRole('button', { name: /^2026-10-10 调休上班/ })).toBeVisible();
      await expect(dialog.getByRole('button', { name: /^2026-10-23 霜降/ }).locator('.calendar-term')).toBeVisible();
      const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      expect(accessibility.violations).toEqual([]);
      await page.screenshot({ path: path.join(evidence, `calendar-${theme}-${width}.png`), animations: 'disabled' });
      await page.keyboard.press('Escape');
      await expect(trigger).toBeFocused();
      await trigger.click();
      await dialog.getByRole('button', { name: /^2026-10-18 重阳/ }).click();
      await expect(trigger).toHaveText(/看哪一天：10月18日/);
      await expect(trigger).toBeFocused();
      expect(await page.locator('input[type="date"]').count()).toBe(0);
    });
  }

for (const theme of ['light', 'dark'])
  test(`custom controls, inline citation, and scrolled budget ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.addInitScript((value) => localStorage.setItem('mingjing-theme', value), theme);
    await page.goto('/?preview=1#/chat');
    const checkbox = page.getByRole('checkbox', { name: '聚焦跳槽' });
    await expect(checkbox).toBeChecked();
    await checkbox.focus();
    await page.keyboard.press('Space');
    await expect(checkbox).not.toBeChecked();
    await page.keyboard.press('Space');
    await expect(checkbox).toBeChecked();
    await checkbox.blur();
    const chip = page.getByRole('button', { name: '查看第1条依据' });
    const inline = await chip.evaluate((element) => {
      const paragraph = element.parentElement!;
      const baseline = paragraph.getBoundingClientRect().height;
      const chipRect = element.getBoundingClientRect();
      (element as HTMLElement).style.position = 'absolute';
      const without = paragraph.getBoundingClientRect().height;
      (element as HTMLElement).style.position = '';
      return {
        baseline,
        without,
        width: chipRect.width,
        height: chipRect.height,
        before: element.previousSibling?.textContent,
        after: element.nextSibling?.textContent?.slice(0, 1),
      };
    });
    expect(inline.width).toBe(18);
    expect(inline.height).toBe(18);
    expect(inline.baseline).toBe(inline.without);
    expect(inline.before).toBe('周三是戊辰日');
    expect(inline.after).toBe('，');
    const budgets = [];
    for (const ratio of [0, 0.25, 0.5, 0.75, 1]) {
      await page.locator('.chat-messages').evaluate((element, fraction) => {
        element.scrollTop = (element.scrollHeight - element.clientHeight) * fraction;
      }, ratio);
      const uses = await page.evaluate(cinnabarUsages);
      budgets.push({ ratio, uses });
      expect(uses.length).toBeLessThanOrEqual(3);
    }
    await page.screenshot({ path: path.join(evidence, `chat-controls-${theme}-1440.png`), animations: 'disabled' });
    await page.goto('/?preview=1#/settings');
    await page.getByRole('button', { name: /周报.*下一期/ }).click();
    await page.getByRole('combobox', { name: '报告星期' }).click();
    await page.getByRole('option', { name: '星期三' }).click();
    await expect(page.getByRole('combobox', { name: '报告星期' })).toHaveText('星期三');
    await page.getByRole('button', { name: '发送时间 07:00' }).click();
    await page.getByRole('combobox', { name: '发送时间小时' }).click();
    await page.getByRole('option', { name: '09', exact: true }).click();
    await page.getByRole('combobox', { name: '发送时间分钟' }).click();
    await page.getByRole('option', { name: '30', exact: true }).click();
    await expect(page.getByRole('button', { name: '发送时间 09:30' })).toBeVisible();
    expect(await page.locator('select,input[type="time"],input[type="number"]').count()).toBe(0);
    const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(accessibility.violations).toEqual([]);
    await fs.writeFile(
      path.join(evidence, `review-${theme}.json`),
      JSON.stringify({ inline, chat_scrolled_budgets: budgets, violations: accessibility.violations }, null, 2) + '\n',
    );
    await page.screenshot({ path: path.join(evidence, `settings-controls-${theme}-1440.png`), animations: 'disabled' });
  });
