import { expect, test, type Page, type TestInfo } from '@playwright/test';
import {
  assertStudyQuiet,
  auditStudy,
  captureStudy,
  composer,
  openStudy,
  prepareStudy,
  tab,
  tabTo,
  workspace,
} from './night-study-helpers';

const captureCourse = (page: Page, name: string, info: TestInfo) =>
  captureStudy(page, name, info, process.env.STUDY_EVIDENCE_DIR ?? 'test-results/courses-browser-latest');

const course = (page: Page) => page.getByRole('region', { name: '研习课程', exact: true });
const directory = (page: Page) => course(page).getByRole('navigation', { name: '课程目录', exact: true });
async function openCourses(page: Page) {
  await workspace(page).getByRole('button', { name: '研习课程', exact: true }).click();
  await expect(course(page)).toHaveAttribute('data-course-state', 'ready');
  await expect(directory(page).getByRole('button')).toHaveCount(20);
}
async function checkFirstLesson(page: Page) {
  const first = course(page).locator('[data-course-quiz="lesson-01-q1"]');
  await first.getByRole('radio', { name: '甲戌', exact: true }).check();
  await first.getByRole('button', { name: '核对这题', exact: true }).click();
  const second = course(page).locator('[data-course-quiz="lesson-01-q2"]');
  await second.getByRole('radio', { name: '不能，须另听现实资料', exact: true }).check();
  await second.getByRole('button', { name: '核对这题', exact: true }).click();
  await expect(course(page)).toContainText('本页练习：1/20课已核对');
}

test.use({ timezoneId: 'Asia/Shanghai', serviceWorkers: 'allow' });
test.beforeEach(async ({ page }) => prepareStudy(page));
test.afterEach(({ page }) => assertStudyQuiet(page));

for (const width of [375, 390, 768, 1440]) {
  for (const theme of ['light', 'dark']) {
    test(`20课课程矩阵：阅读/核对/西占c7 ${width} ${theme}`, async ({ page }, info) => {
      test.setTimeout(120000);
      await openStudy(page, width, theme);
      await openCourses(page);
      await expect(course(page).getByRole('button', { name: '上一课', exact: true })).toBeDisabled();
      await auditStudy(page);
      await captureCourse(page, `courses-reading-${width}-${theme}`, info);
      await checkFirstLesson(page);
      await auditStudy(page);
      await captureCourse(page, `courses-checked-${width}-${theme}`, info);
      await directory(page).getByRole('button').last().click();
      await expect(course(page).getByRole('heading', { name: '西占几何与三体系复盘', exact: true })).toBeFocused();
      await expect(course(page).getByRole('button', { name: '下一课', exact: true })).toBeDisabled();
      await course(page).locator('summary').filter({ hasText: '本课依据与口径' }).click();
      await expect(course(page)).toContainText('阿远 · 西方占星 · 〔c7〕');
      await auditStudy(page);
      await captureCourse(page, `courses-astro-${width}-${theme}`, info);
    });
  }
}

for (const width of [390, 1440]) {
  test(`课程键盘与暂停：保留草稿和本页答案，刷新清空 ${width}`, async ({ page }, info) => {
    await openStudy(page, width, width === 390 ? 'dark' : 'light');
    const draft = '合成课程问题，先保留在对话草稿。';
    await composer(page).fill(draft);
    const original = await composer(page).elementHandle();
    if (!original) throw new Error('Composer required');
    await openCourses(page);
    const radio = course(page)
      .locator('[data-course-quiz="lesson-01-q1"]')
      .getByRole('radio', { name: '甲戌', exact: true });
    await tabTo(page, radio);
    await page.keyboard.press('Space');
    await expect(radio).toBeChecked();
    await page.keyboard.press('ArrowDown');
    await expect(course(page).getByRole('radio', { name: '丁酉', exact: true })).toBeChecked();
    await checkFirstLesson(page);
    await tab(page, '对话');
    await expect(composer(page)).toHaveValue(draft);
    expect(await original.evaluate((node) => node === document.getElementById('spaces-preview-draft'))).toBe(true);
    await openCourses(page);
    await expect(course(page)).toContainText('本页练习：1/20课已核对');
    await course(page).getByRole('button', { name: '清空本页练习', exact: true }).click();
    await expect(course(page)).toContainText('本页练习：0/20课已核对');
    await auditStudy(page);
    await captureCourse(page, `courses-keyboard-${width}`, info);
    await checkFirstLesson(page);
    await page.reload();
    await expect(workspace(page)).toHaveAttribute('data-study-state', 'ready');
    await openCourses(page);
    await expect(course(page)).toContainText('本页练习：0/20课已核对');
    await original.dispose();
  });
}

test('课程读取失败可重试，原对话/词典仍可用', async ({ page }, info) => {
  let corrupt = true;
  await page.route('**/data/study/courses-v5/course.json', async (route) => {
    if (corrupt)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '{"private":"SECRET_INVALID_COURSE"}',
      });
    else await route.continue();
  });
  await openStudy(page, 390, 'light');
  await composer(page).fill('失败后继续的合成草稿');
  await workspace(page).getByRole('button', { name: '研习课程', exact: true }).click();
  await expect(course(page)).toHaveAttribute('data-course-state', 'error');
  await expect(course(page)).not.toContainText('SECRET_INVALID_COURSE');
  await auditStudy(page);
  await captureCourse(page, 'courses-invalid', info);
  await tab(page, '对话');
  await expect(composer(page)).toHaveValue('失败后继续的合成草稿');
  await tab(page, '术语词典');
  await expect(page.getByRole('searchbox', { name: '搜索术语', exact: true })).toBeVisible();
  await workspace(page).getByRole('button', { name: '研习课程', exact: true }).click();
  corrupt = false;
  await course(page).getByRole('button', { name: '重新读取课程', exact: true }).click();
  await expect(course(page)).toHaveAttribute('data-course-state', 'ready');
});

test('课程深链接直接打开，未交互前已有完整教材', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?spaces=demo#/chat?space=study&topic=chart-study&view=courses');
  await expect(course(page)).toHaveAttribute('data-course-state', 'ready');
  await expect(directory(page).getByRole('button')).toHaveCount(20);
  await expect(course(page).getByRole('heading', { name: '四柱先按位置读', exact: true })).toBeVisible();
  await auditStudy(page);
  await captureCourse(page, 'courses-deep-link', info);
});
