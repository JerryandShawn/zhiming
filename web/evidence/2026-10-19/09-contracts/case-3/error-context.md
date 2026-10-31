# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: contracts.spec.ts >> 9 焦点陷阱/回返、减动效与手机输入可见
- Location: tests\e2e\contracts.spec.ts:305:1

# Error details

```
Error: expect(locator).toBeFocused() failed

Locator:  getByRole('button', { name: '新建事项', exact: true })
Expected: focused
Received: inactive
Timeout:  5000ms

Call log:
  - Expect "toBeFocused" getByRole('button', { name: '新建事项', exact: true }) with timeout 5000ms
  - waiting for getByRole('button', { name: '新建事项', exact: true })
    - waiting for navigation to finish...
    - navigated to "http://127.0.0.1:4174/#/cases"
    7 × locator resolved to <button type="button" data-state="closed" aria-expanded="false" aria-haspopup="dialog" class="button secondary  ">新建事项</button>
      - unexpected value "inactive"

```

```yaml
- button "新建事项"
```

# Test source

```ts
  217 |   await page.getByRole('button', { name: '准备牌背，开始选牌' }).click();
  218 |   await expect(page.getByRole('group', { name: '亲手点选牌背' })).toBeVisible();
  219 |   await page.getByRole('button', { name: '第1张牌背', exact: true }).focus();
  220 |   await page.keyboard.press('ArrowRight');
  221 |   await expect(page.getByRole('button', { name: '第2张牌背', exact: true })).toBeFocused();
  222 |   await page.keyboard.press('Enter');
  223 |   await expect(page.getByRole('status').filter({ hasText: '已选 1 / 3' })).toBeVisible();
  224 |   await page.getByRole('button', { name: '第3张牌背', exact: true }).click();
  225 |   await expect(page.getByRole('status').filter({ hasText: '已选 2 / 3' })).toBeVisible();
  226 |   await page.getByRole('button', { name: '第4张牌背', exact: true }).click();
  227 |   await expect(page.getByRole('img', { name: '不透明的塔罗牌背' })).toHaveCount(3);
  228 |   const drawId = new URLSearchParams(page.url().split('?draw=')[1] ? `draw=${page.url().split('?draw=')[1]}` : '').get(
  229 |     'draw',
  230 |   );
  231 |   await page.getByRole('button', { name: '全部揭开 · 跳过动画' }).click();
  232 |   await expect(page.getByRole('group', { name: '本次固定牌阵' })).toHaveAttribute('data-reduced-motion', 'true');
  233 |   await expect(page.getByRole('img', { name: '不透明的塔罗牌背' })).toHaveCount(0);
  234 |   const frozen = await request.get(`/api/tarot/draws/${drawId}`, { headers });
  235 |   const before = ((await frozen.json()) as { cards: unknown[] }).cards;
  236 |   await control(request, { failures: 100 });
  237 |   await page.getByRole('button', { name: '生成 AI 解读' }).click();
  238 |   await expect(page.getByRole('status').filter({ hasText: '解释未完成' })).toBeVisible({ timeout: 30000 });
  239 |   await control(request, {});
  240 |   await page.getByRole('button', { name: '重试原解读 · 不换牌' }).click();
  241 |   await expect(page.getByRole('status').filter({ hasText: '解读已保存' })).toBeVisible({ timeout: 30000 });
  242 |   const after = await request.get(`/api/tarot/draws/${drawId}`, { headers });
  243 |   expect(((await after.json()) as { cards: unknown[] }).cards).toEqual(before);
  244 | });
  245 |
  246 | test('7 报告 PATCH 严格键、北京时间、提前准备、回执校验与409草稿', async ({ page, request }) => {
  247 |   await login(page);
  248 |   await page.goto('/#/settings/reports');
  249 |   await expect(page.getByText(/北京时间.*提前 15 分钟准备/)).toBeVisible();
  250 |   const report = page.locator('[data-report-kind="daily"]');
  251 |   await expect(report.getByRole('button', { name: '保存晨报设置' })).toBeEnabled();
  252 |   const data = await request.get('/api/reports/schedules', { headers });
  253 |   const row = ((await data.json()) as { schedules: { kind: string; revision: number }[] }).schedules.find(
  254 |     (r) => r.kind === 'daily',
  255 |   )!;
  256 |   await report.getByRole('switch', { name: '启用晨报' }).click();
  257 |   expect(
  258 |     (
  259 |       await request.patch('/api/reports/schedules', {
  260 |         headers,
  261 |         data: {
  262 |           kind: 'daily',
  263 |           request_id: crypto.randomUUID(),
  264 |           expected_revision: row.revision,
  265 |           enabled: true,
  266 |           time: '08:00',
  267 |         },
  268 |       })
  269 |     ).ok(),
  270 |   ).toBe(true);
  271 |   const payloads: Record<string, unknown>[] = [];
  272 |   page.on('request', (event) => {
  273 |     if (event.method() === 'PATCH' && event.url().endsWith('/api/reports/schedules'))
  274 |       payloads.push(event.postDataJSON() as Record<string, unknown>);
  275 |   });
  276 |   await report.getByRole('button', { name: '保存晨报设置' }).click();
  277 |   await expect(report.getByRole('button', { name: '保存晨报设置' })).toBeDisabled();
  278 |   await expect(report.getByRole('switch', { name: '启用晨报' })).toBeChecked();
  279 |   await report.getByRole('button', { name: '读取最新设置，保留草稿' }).click();
  280 |   await report.getByRole('button', { name: '保存晨报设置' }).click();
  281 |   await expect(report.getByRole('status')).toContainText('已保存晨报设置');
  282 |   expect(Object.keys(payloads.at(-1)!).sort()).toEqual(['enabled', 'expected_revision', 'kind', 'request_id', 'time']);
  283 | });
  284 |
  285 | test('8 全部旧深链保持对应数据页，含报告归档日期', async ({ page }) => {
  286 |   await login(page);
  287 |   for (const [old, name] of [
  288 |     ['', 'today'],
  289 |     ['chat', 'chat'],
  290 |     ['chart?tab=ziwei&date=2026-10-21', 'chart'],
  291 |     ['tarot', 'tarot'],
  292 |     ['cases', 'cases'],
  293 |     ['memory', 'me'],
  294 |     ['timeline', 'me'],
  295 |     ['graph', 'me'],
  296 |     ['dict', 'me'],
  297 |     ['reportsettings', 'settings'],
  298 |     ['reports?date=2026-10-17', 'settings'],
  299 |   ]) {
  300 |     await page.goto(`/#/${old}`);
  301 |     await expect(page.locator(`[data-page="${name}"]`)).toBeVisible();
  302 |   }
  303 | });
  304 |
  305 | test('9 焦点陷阱/回返、减动效与手机输入可见', async ({ page }) => {
  306 |   await login(page);
  307 |   await page.setViewportSize({ width: 390, height: 844 });
  308 |   await page.goto('/#/cases');
  309 |   const trigger = page.getByRole('button', { name: '新建事项', exact: true });
  310 |   await trigger.click();
  311 |   const dialog = page.getByRole('dialog');
  312 |   await expect(dialog).toBeVisible();
  313 |   await page.getByRole('button', { name: '关闭', exact: true }).focus();
  314 |   await page.keyboard.press('Tab');
  315 |   expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  316 |   await page.keyboard.press('Escape');
> 317 |   await expect(trigger).toBeFocused();
      |                         ^ Error: expect(locator).toBeFocused() failed
  318 |   await page.goto('/#/chat');
  319 |   const composer = page.getByRole('textbox', { name: '和明镜说说' });
  320 |   await composer.focus();
  321 |   await page.evaluate(() => {
  322 |     Object.defineProperty(window.visualViewport, 'height', { configurable: true, get: () => 420 });
  323 |     window.visualViewport!.dispatchEvent(new Event('resize'));
  324 |   });
  325 |   await expect(page.locator('.shell')).toHaveAttribute('data-keyboard', 'open');
  326 |   await expect(page.getByRole('navigation', { name: '底部导航' })).toBeHidden();
  327 |   await expect(composer).toBeInViewport();
  328 |   expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);
  329 | });
  330 |
  331 | test('10 X-Token登录及401统一重登并保留编辑草稿', async ({ page }) => {
  332 |   await page.goto('/#/cases');
  333 |   await expect(page.getByRole('dialog', { name: '登录明镜台' })).toBeVisible();
  334 |   await page.getByRole('textbox', { name: '网站口令' }).fill(token);
  335 |   await page.getByRole('button', { name: '登录', exact: true }).click();
  336 |   await expect(page.getByRole('dialog', { name: '登录明镜台' })).toHaveCount(0);
  337 |   await page.getByRole('button', { name: '新建事项', exact: true }).click();
  338 |   await page.getByRole('textbox', { name: '标题', exact: true }).fill('401时保留的草稿');
  339 |   await page.route('**/api/cases', async (route) =>
  340 |     route.request().method() === 'POST' ? route.fulfill({ status: 401, body: '{}' }) : route.continue(),
  341 |   );
  342 |   await page.getByRole('button', { name: '创建事项', exact: true }).click();
  343 |   await expect(page.getByRole('dialog', { name: '登录明镜台' })).toBeVisible();
  344 |   await page.getByRole('textbox', { name: '网站口令' }).fill(token);
  345 |   await page.getByRole('button', { name: '登录', exact: true }).click();
  346 |   await expect(page.getByRole('textbox', { name: '标题', exact: true })).toHaveValue('401时保留的草稿');
  347 | });
  348 |
  349 | test('11 私有洗牌与出生原值不在非资料页渲染，零境外请求', async ({ page, request }) => {
  350 |   await confirmProfile(request);
  351 |   expect(
  352 |     (
  353 |       await request.post('/api/chat', {
  354 |         headers,
  355 |         data: { request_id: crypto.randomUUID(), message: '核对今天的合成安排', depth: 'fast' },
  356 |       })
  357 |     ).ok(),
  358 |   ).toBe(true);
  359 |   await login(page);
  360 |   const external: string[] = [];
  361 |   page.on('request', (event) => {
  362 |     const url = new URL(event.url());
  363 |     if (['http:', 'https:'].includes(url.protocol) && url.hostname !== '127.0.0.1') external.push(url.hostname);
  364 |   });
  365 |   await page.route('**/api/chart?*', async (route) => {
  366 |     const response = await route.fetch();
  367 |     if (!response.ok()) return route.fulfill({ response });
  368 |     const data = (await response.json()) as Record<string, unknown>;
  369 |     await route.fulfill({
  370 |       json: { ...data, private_order: 'PRIVATE_CARD_ORDER_SENTINEL', birth_raw: 'PRIVATE_BIRTH_RAW_SENTINEL' },
  371 |     });
  372 |   });
  373 |   for (const path of ['today', 'chart', 'tarot', 'me?section=memory', 'chat']) {
  374 |     const chartResponse = ['today', 'chart'].includes(path)
  375 |       ? page.waitForResponse((response) => response.url().includes('/api/chart?') && response.ok())
  376 |       : undefined;
  377 |     await page.goto(`/#/${path}`);
  378 |     if (chartResponse) await chartResponse;
  379 |     await expect(page.locator('[data-page]').first()).toBeVisible();
  380 |     await expect(page.locator('body')).not.toContainText('PRIVATE_CARD_ORDER_SENTINEL');
  381 |     await expect(page.locator('body')).not.toContainText('PRIVATE_BIRTH_RAW_SENTINEL');
  382 |     await expect(page.locator('body')).not.toContainText('1998-03-12');
  383 |   }
  384 |   expect(external).toEqual([]);
  385 |   await page.unrouteAll({ behavior: 'wait' });
  386 |   expect(
  387 |     ((await (await request.get('/__test__/metrics')).json()) as { real_model_calls: number }).real_model_calls,
  388 |   ).toBe(0);
  389 | });
  390 |
  391 | test('SSE v2 本地事件服务中断续传去重、修订替换、工具/回执/提问/决策渲染', async ({ page, request }) => {
  392 |   await page.goto('/tests/fixtures/v2.html');
  393 |   await expect(page.getByText('复核后的合成回答。', { exact: true })).toBeVisible();
  394 |   await expect(page.getByText('待复核的旧说法。', { exact: true })).toHaveCount(0);
  395 |   await expect(page.getByText('已修订', { exact: true })).toBeVisible();
  396 |   await expect(page.getByText('想先看哪一项？', { exact: true })).toBeVisible();
  397 |   await expect(page.getByRole('heading', { name: '先准备', exact: true })).toBeVisible();
  398 |   await expect(page.getByText('已记下：合成偏好', { exact: true })).toHaveCount(1);
  399 |   const metrics = (await (await request.get('/__test__/metrics')).json()) as { v2_cursors: string[] };
  400 |   expect(metrics.v2_cursors).toContain('4');
  401 | });
  402 |
```