import { test, expect, type Page, type APIRequestContext } from '@playwright/test';

let token = 'synthetic-frontend-token';
const headers = { 'X-Token': token };
async function login(page: Page) {
  await page.addInitScript((value) => sessionStorage.setItem('mingjing-auth-token', value), token);
}
async function choose(page: Page, label: string, option: string) {
  await page.getByRole('combobox', { name: label, exact: true }).click();
  await page.getByRole('option', { name: option, exact: true }).click();
}
async function newCase(request: APIRequestContext, title: string) {
  const response = await request.post('/api/cases', {
    headers,
    data: { request_id: crypto.randomUUID(), title, goal: '合成目标' },
  });
  expect(response.ok()).toBe(true);
  return (await response.json()) as { id: string; revision: number };
}
async function control(request: APIRequestContext, data: { failures?: number; delay?: number }) {
  expect((await request.post('/__test__/model-control', { data })).ok()).toBe(true);
}

async function confirmProfile(request: APIRequestContext) {
  const state = (await (await request.get('/api/state', { headers })).json()) as { revision: number };
  const response = await request.post('/api/subjects/self/profile/confirm', {
    headers,
    data: {
      request_id: crypto.randomUUID(),
      expected_revision: state.revision,
      confirmed: true,
      profile: {
        gender: '女',
        birth: {
          solar_datetime: '1998-03-12 08:15',
          precision: 'exact',
          timezone_offset: 8,
          location: { city: '合成地点', lng: 116.4, lat: 39.9 },
        },
      },
    },
  });
  expect(response.ok()).toBe(true);
}

test.beforeEach(async ({ request }) => {
  const response = await request.post('/__test__/owner');
  expect(response.ok()).toBe(true);
  token = ((await response.json()) as { token: string }).token;
  headers['X-Token'] = token;
});

test.afterEach(async ({ request, page }) => {
  await control(request, {});
  await page.unrouteAll({ behavior: 'wait' });
});

test('1 稳定 request_id 跨断线与刷新重放，成功后新操作换号', async ({ page }) => {
  await login(page);
  const ids: string[] = [];
  let lose = true;
  await page.route('**/api/cases', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    ids.push((route.request().postDataJSON() as { request_id: string }).request_id);
    const response = await route.fetch();
    if (lose) {
      lose = false;
      return route.abort('failed');
    }
    await route.fulfill({ response });
  });
  await page.goto('/#/cases');
  await page.getByRole('button', { name: '新建事项', exact: true }).click();
  await page.getByRole('textbox', { name: '标题', exact: true }).fill('断线后重放的合成事项');
  await page.getByRole('textbox', { name: '目标', exact: true }).fill('不要重复建立事项');
  await page.getByRole('button', { name: '创建事项', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('尚未确认提交');
  await page.reload();
  await page.getByRole('button', { name: '新建事项', exact: true }).click();
  await expect(page.getByRole('textbox', { name: '标题', exact: true })).toHaveValue('断线后重放的合成事项');
  await page.getByRole('button', { name: '重试创建原事项' }).click();
  await expect(page.getByRole('status')).toContainText('事项已保存');
  expect(ids).toHaveLength(2);
  expect(ids[0]).toBe(ids[1]);
  await page.getByRole('textbox', { name: '标题', exact: true }).fill('成功后新的合成事项');
  await page.getByRole('button', { name: '创建事项', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('事项已保存');
  expect(ids[2]).not.toBe(ids[1]);
});

test('2 真实 revision 冲突保留草稿、禁写、核对最新后再保存', async ({ page, request }) => {
  await login(page);
  const title = `冲突核对${Date.now()}`,
    item = await newCase(request, title);
  await page.goto('/#/cases');
  await page.getByRole('button', { name: new RegExp(title) }).click();
  await page.getByRole('textbox', { name: '事项目标' }).fill('用户尚未保存的草稿');
  const concurrent = await request.patch(`/api/cases/${item.id}`, {
    headers,
    data: {
      request_id: crypto.randomUUID(),
      expected_revision: item.revision,
      changes: { goal: '另一处已保存的目标' },
    },
  });
  expect(concurrent.ok()).toBe(true);
  await page.getByRole('button', { name: '保存事项更正', exact: true }).click();
  await expect(page.getByText('内容已在别处更新，草稿已保留。请读取最新版本并核对。')).toBeVisible();
  await expect(page.getByRole('textbox', { name: '事项目标' })).toHaveValue('用户尚未保存的草稿');
  await expect(page.getByRole('button', { name: '保存事项更正', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '读取最新事项，保留草稿', exact: true }).click();
  await expect(page.getByRole('button', { name: '保存事项更正', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '保存事项更正', exact: true }).click();
  await expect(page.getByText('事项更正已保存。')).toBeVisible();
});

test('3 v3 同轮重试与成功恢复；取消接口422时不伪报停止', async ({ page, request }) => {
  await login(page);
  await control(request, { failures: 100 });
  const chats: string[] = [],
    retries: string[] = [],
    cancels: string[] = [];
  page.on('request', (event) => {
    if (event.method() !== 'POST') return;
    const url = new URL(event.url());
    if (url.pathname === '/api/chat') chats.push((event.postDataJSON() as { request_id: string }).request_id);
    if (url.pathname.endsWith('/retry')) retries.push(url.pathname);
    if (url.pathname.endsWith('/cancel')) cancels.push(url.pathname);
  });
  await page.goto('/#/chat');
  await page.getByRole('textbox', { name: '和明镜说说' }).fill('请核对这次合成安排');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  const continueCurrent = page
    .locator('.chat-inner > section.ask-card')
    .getByRole('button', { name: '继续原来这一轮', exact: true });
  await expect(continueCurrent).toBeVisible({
    timeout: 30000,
  });
  await control(request, {});
  await continueCurrent.click();
  await expect.poll(() => retries.length).toBe(1);
  await expect(page.getByText('先核对现实安排，再做一个小行动。').last()).toBeVisible({ timeout: 30000 });
  expect(chats).toHaveLength(1);
  expect(retries).toHaveLength(1);
  await expect
    .poll(
      async () => {
        const complete = await request.get(`/api/runs/${encodeURIComponent(chats[0])}`, { headers });
        return ((await complete.json()) as { status: string }).status;
      },
      { timeout: 30000 },
    )
    .toBe('succeeded');
  await control(request, { delay: 4 });
  await page.getByRole('textbox', { name: '和明镜说说' }).fill('下一轮的合成安排');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止回答' })).toBeEnabled();
  await page.getByRole('button', { name: '停止回答' }).click();
  await expect(page.getByRole('alert')).toContainText('内容没有通过核对');
  await expect(page.getByText('已停止本轮', { exact: true })).toHaveCount(0);
  expect(cancels).toHaveLength(1);
  expect(chats[1]).not.toBe(chats[0]);
});

test('4 资料明确同意、未知禁用时刻、大约必填分钟、回执确认', async ({ page }) => {
  await login(page);
  await page.goto('/#/me?section=profile');
  await expect(page.getByRole('heading', { name: '核对出生资料' })).toBeVisible();
  await choose(page, '排盘所用性别', '女');
  await page.getByRole('textbox', { name: '阳历出生日期', exact: true }).fill('1998-03-12');
  await choose(page, '出生时刻精度', '时刻未知');
  await expect(page.getByRole('combobox', { name: '当地出生时间小时' })).toBeDisabled();
  await choose(page, '出生时刻精度', '大约时刻');
  await expect(page.getByRole('spinbutton', { name: '前后误差（分钟）' })).toBeVisible();
  await page.getByRole('textbox', { name: '出生地名称' }).fill('合成地点');
  await page.getByRole('spinbutton', { name: '经度', exact: true }).fill('116.4');
  await page.getByRole('spinbutton', { name: '纬度', exact: true }).fill('39.9');
  await page.getByRole('spinbutton', { name: '出生地 UTC 偏移（小时）' }).fill('8');
  await expect(page.getByRole('button', { name: '确认并保存资料' })).toBeDisabled();
  await page.getByRole('checkbox', { name: '我已核对并授权保存出生与性别资料' }).check();
  await expect(page.getByRole('spinbutton', { name: '前后误差（分钟）' })).toHaveAttribute('required', '');
  await page.getByRole('spinbutton', { name: '前后误差（分钟）' }).fill('30');
  await page.getByRole('button', { name: '确认并保存资料' }).click();
  await expect(page.getByRole('status').filter({ hasText: /已保存.*项经你确认的资料/ })).toBeVisible();
});

test('5 记忆更正与删除范围只依程序回执，未知提案不可确认', async ({ page }) => {
  await login(page);
  await page.goto('/#/me?section=memory');
  const card = page
    .getByRole('article', { name: '记忆条目' })
    .filter({ has: page.locator('textarea:enabled') })
    .first();
  await expect(card).toBeVisible();
  await card.getByRole('textbox', { name: '记忆内容' }).fill('我喜欢傍晚阅读');
  await card.getByRole('button', { name: '保存记忆更正' }).click();
  await expect(page.getByRole('status').filter({ hasText: '记忆更正已保存' })).toBeVisible();
  const corrected = page
    .getByRole('article', { name: '记忆条目' })
    .filter({ has: page.locator('textarea:enabled').filter({ hasText: '我喜欢傍晚阅读' }) });
  await expect(corrected.getByRole('textbox', { name: '记忆内容' })).toBeVisible();
  await corrected.getByText('删除范围', { exact: true }).click();
  await corrected.getByRole('combobox', { name: '删除范围' }).click();
  await page.getByRole('option', { name: '删除整段来源及关联内容' }).click();
  await corrected.getByRole('checkbox', { name: '确认删除所选范围' }).check();
  await corrected.getByRole('button', { name: '确认删除所选范围' }).click();
  await expect(corrected).toHaveCount(0);
  await page.getByRole('button', { name: '待确认', exact: true }).click();
  await expect(page.getByRole('button', { name: '确认记忆提案' })).toBeDisabled();
});

test('6 服务端亲选牌背、固定牌、揭牌与失败解读恢复不重抽', async ({ page, request }) => {
  await login(page);
  await page.goto('/#/tarot');
  await page.getByRole('textbox', { name: '想问什么？' }).fill('如何准备合成面试');
  await page.getByRole('button', { name: '亲手点选', exact: true }).click();
  await page.getByRole('button', { name: '准备牌背，开始选牌' }).click();
  await expect(page.getByRole('group', { name: '亲手点选牌背' })).toBeVisible();
  await page.getByRole('button', { name: '第1张牌背', exact: true }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('button', { name: '第2张牌背', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('status').filter({ hasText: '已选 1 / 3' })).toBeVisible();
  await page.getByRole('button', { name: '第3张牌背', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: '已选 2 / 3' })).toBeVisible();
  await page.getByRole('button', { name: '第4张牌背', exact: true }).click();
  await expect(page.getByRole('img', { name: '不透明的塔罗牌背' })).toHaveCount(3);
  const drawId = new URLSearchParams(page.url().split('?draw=')[1] ? `draw=${page.url().split('?draw=')[1]}` : '').get(
    'draw',
  );
  await page.getByRole('button', { name: '全部揭开 · 跳过动画' }).click();
  await expect(page.getByRole('group', { name: '本次固定牌阵' })).toHaveAttribute('data-reduced-motion', 'true');
  await expect(page.getByRole('img', { name: '不透明的塔罗牌背' })).toHaveCount(0);
  const frozen = await request.get(`/api/tarot/draws/${drawId}`, { headers });
  const before = ((await frozen.json()) as { cards: unknown[] }).cards;
  await control(request, { failures: 100 });
  await page.getByRole('button', { name: '生成 AI 解读' }).click();
  await expect(page.getByRole('status').filter({ hasText: '解释未完成' })).toBeVisible({ timeout: 30000 });
  await control(request, {});
  await page.getByRole('button', { name: '重试原解读 · 不换牌' }).click();
  await expect(page.getByRole('status').filter({ hasText: '解读已保存' })).toBeVisible({ timeout: 30000 });
  const after = await request.get(`/api/tarot/draws/${drawId}`, { headers });
  expect(((await after.json()) as { cards: unknown[] }).cards).toEqual(before);
});

test('7 报告 PATCH 严格键、北京时间、提前准备、回执校验与409草稿', async ({ page, request }) => {
  await login(page);
  await page.goto('/#/settings/reports');
  await expect(page.getByText(/北京时间.*提前 15 分钟准备/)).toBeVisible();
  const report = page.locator('[data-report-kind="daily"]');
  await expect(report.getByRole('button', { name: '保存晨报设置' })).toBeEnabled();
  const data = await request.get('/api/reports/schedules', { headers });
  const row = ((await data.json()) as { schedules: { kind: string; revision: number }[] }).schedules.find(
    (r) => r.kind === 'daily',
  )!;
  await report.getByRole('switch', { name: '启用晨报' }).click();
  expect(
    (
      await request.patch('/api/reports/schedules', {
        headers,
        data: {
          kind: 'daily',
          request_id: crypto.randomUUID(),
          expected_revision: row.revision,
          enabled: true,
          time: '08:00',
        },
      })
    ).ok(),
  ).toBe(true);
  const payloads: Record<string, unknown>[] = [];
  page.on('request', (event) => {
    if (event.method() === 'PATCH' && event.url().endsWith('/api/reports/schedules'))
      payloads.push(event.postDataJSON() as Record<string, unknown>);
  });
  await report.getByRole('button', { name: '保存晨报设置' }).click();
  await expect(report.getByRole('button', { name: '保存晨报设置' })).toBeDisabled();
  await expect(report.getByRole('switch', { name: '启用晨报' })).toBeChecked();
  await report.getByRole('button', { name: '读取最新设置，保留草稿' }).click();
  await report.getByRole('button', { name: '保存晨报设置' }).click();
  await expect(report.getByRole('status')).toContainText('已保存晨报设置');
  expect(Object.keys(payloads.at(-1)!).sort()).toEqual(['enabled', 'expected_revision', 'kind', 'request_id', 'time']);
});

test('8 全部旧深链保持对应数据页，含报告归档日期', async ({ page }) => {
  await login(page);
  for (const [old, name] of [
    ['', 'today'],
    ['chat', 'chat'],
    ['chart?tab=ziwei&date=2026-10-21', 'chart'],
    ['tarot', 'tarot'],
    ['cases', 'cases'],
    ['memory', 'me'],
    ['timeline', 'me'],
    ['graph', 'me'],
    ['dict', 'me'],
    ['reportsettings', 'settings'],
    ['reports?date=2026-10-17', 'settings'],
  ]) {
    await page.goto(`/#/${old}`);
    await expect(page.locator(`[data-page="${name}"]`)).toBeVisible();
  }
});

test('9 焦点陷阱/回返、减动效与手机输入可见', async ({ page }) => {
  await login(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/#/cases');
  const trigger = page.getByRole('button', { name: '新建事项', exact: true });
  await trigger.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await page.getByRole('button', { name: '关闭', exact: true }).focus();
  await page.keyboard.press('Tab');
  expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
  await page.goto('/#/chat');
  const composer = page.getByRole('textbox', { name: '和明镜说说' });
  await composer.focus();
  await page.evaluate(() => {
    Object.defineProperty(window.visualViewport, 'height', { configurable: true, get: () => 420 });
    window.visualViewport!.dispatchEvent(new Event('resize'));
  });
  await expect(page.locator('.shell')).toHaveAttribute('data-keyboard', 'open');
  await expect(page.getByRole('navigation', { name: '底部导航' })).toBeHidden();
  await expect(composer).toBeInViewport();
  expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);
});

test('10 X-Token登录及401统一重登并保留编辑草稿', async ({ page }) => {
  await page.goto('/#/cases');
  await expect(page.getByRole('dialog', { name: '登录明镜台' })).toBeVisible();
  await page.getByRole('textbox', { name: '网站口令' }).fill(token);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '登录明镜台' })).toHaveCount(0);
  await page.getByRole('button', { name: '新建事项', exact: true }).click();
  await page.getByRole('textbox', { name: '标题', exact: true }).fill('401时保留的草稿');
  await page.route('**/api/cases', async (route) =>
    route.request().method() === 'POST' ? route.fulfill({ status: 401, body: '{}' }) : route.continue(),
  );
  await page.getByRole('button', { name: '创建事项', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '登录明镜台' })).toBeVisible();
  await page.getByRole('textbox', { name: '网站口令' }).fill(token);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('textbox', { name: '标题', exact: true })).toHaveValue('401时保留的草稿');
});

test('11 私有洗牌与出生原值不在非资料页渲染，零境外请求', async ({ page, request }) => {
  await confirmProfile(request);
  expect(
    (
      await request.post('/api/chat', {
        headers,
        data: { request_id: crypto.randomUUID(), message: '核对今天的合成安排', depth: 'fast' },
      })
    ).ok(),
  ).toBe(true);
  await login(page);
  const external: string[] = [];
  page.on('request', (event) => {
    const url = new URL(event.url());
    if (['http:', 'https:'].includes(url.protocol) && url.hostname !== '127.0.0.1') external.push(url.hostname);
  });
  await page.route('**/api/chart?*', async (route) => {
    const response = await route.fetch();
    if (!response.ok()) return route.fulfill({ response });
    const data = (await response.json()) as Record<string, unknown>;
    await route.fulfill({
      json: { ...data, private_order: 'PRIVATE_CARD_ORDER_SENTINEL', birth_raw: 'PRIVATE_BIRTH_RAW_SENTINEL' },
    });
  });
  for (const path of ['today', 'chart', 'tarot', 'me?section=memory', 'chat']) {
    const chartResponse = ['today', 'chart'].includes(path)
      ? page.waitForResponse((response) => response.url().includes('/api/chart?') && response.ok())
      : undefined;
    await page.goto(`/#/${path}`);
    if (chartResponse) await chartResponse;
    await expect(page.locator('[data-page]').first()).toBeVisible();
    await expect(page.locator('body')).not.toContainText('PRIVATE_CARD_ORDER_SENTINEL');
    await expect(page.locator('body')).not.toContainText('PRIVATE_BIRTH_RAW_SENTINEL');
    await expect(page.locator('body')).not.toContainText('1998-03-12');
  }
  expect(external).toEqual([]);
  await page.unrouteAll({ behavior: 'wait' });
  expect(
    ((await (await request.get('/__test__/metrics')).json()) as { real_model_calls: number }).real_model_calls,
  ).toBe(0);
});

test('SSE v2 本地事件服务中断续传去重、修订替换、工具/回执/提问/决策渲染', async ({ page, request }) => {
  await page.goto('/tests/fixtures/v2.html');
  await expect(page.getByText('复核后的合成回答。', { exact: true })).toBeVisible();
  await expect(page.getByText('待复核的旧说法。', { exact: true })).toHaveCount(0);
  await expect(page.getByText('已修订', { exact: true })).toBeVisible();
  await expect(page.getByText('想先看哪一项？', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '先准备', exact: true })).toBeVisible();
  await expect(page.getByText('程序回执：已记下：合成偏好', { exact: true })).toHaveCount(1);
  const metrics = (await (await request.get('/__test__/metrics')).json()) as { v2_cursors: string[] };
  expect(metrics.v2_cursors).toContain('4');
});
