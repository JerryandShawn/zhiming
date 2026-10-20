import { expect, type Page } from '@playwright/test';
import { auditNight, guardNight, assertNightQuiet, captureNight } from './night-helpers';

type MotionRecord = { name: string; state: string | null; duration: string; delay: string; target: string };
type MotionLog = { css: MotionRecord[]; routes: { duration: number | string; keyframes: unknown[] }[] };
declare global {
  interface Window {
    __motionLog: MotionLog;
  }
}

export async function prepareMotion(page: Page, width: number) {
  guardNight(page);
  await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.addInitScript(() => {
    const log: MotionLog = { css: [], routes: [] };
    window.__motionLog = log;
    document.addEventListener(
      'animationstart',
      (event) => {
        const target = event.target;
        if (!(target instanceof Element) || !target.matches('.dialog, .overlay')) return;
        const css = getComputedStyle(target);
        log.css.push({
          name: event.animationName,
          state: target.getAttribute('data-state'),
          duration: css.animationDuration,
          delay: css.animationDelay,
          target: target.className,
        });
      },
      true,
    );
    const native = Element.prototype.animate;
    Element.prototype.animate = function (...args: Parameters<Element['animate']>) {
      const animation = native.apply(this, args);
      if (this.id === 'main' && animation.effect instanceof KeyframeEffect) {
        const duration = animation.effect.getTiming().duration;
        log.routes.push({
          duration: typeof duration === 'number' || typeof duration === 'string' ? duration : String(duration),
          keyframes: animation.effect.getKeyframes(),
        });
      }
      return animation;
    };
  });
}

export const motionLog = (page: Page) => page.evaluate(() => window.__motionLog);
export async function openStaticProfile(page: Page) {
  await page.goto('/?preview=1#/today');
  await expect(page.locator('[data-page="today"]')).toBeVisible();
  expect((await motionLog(page)).routes).toEqual([]);
  await page.evaluate(() => {
    location.hash = '#/me';
  });
  await expect(page.locator('[data-page="me"]')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect.poll(async () => (await motionLog(page)).routes.length).toBe(1);
  return page.getByRole('button', { name: '编辑称呼与基本情况', exact: true });
}

export async function assertMotionQuiet(page: Page, screenshot: string) {
  await page.locator('#main').evaluate(async (node) => {
    await Promise.allSettled(node.getAnimations().map((animation) => animation.finished));
  });
  await auditNight(page);
  assertNightQuiet(page);
  await captureNight(page, screenshot, true);
}

export async function noActiveDialog(page: Page) {
  await expect(page.locator('[role="dialog"]')).toHaveCount(0);
  await expect(page.locator('.overlay')).toHaveCount(0);
}
