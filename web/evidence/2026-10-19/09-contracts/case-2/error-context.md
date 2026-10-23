# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: contracts.spec.ts >> 6 服务端亲选牌背、固定牌、揭牌与失败解读恢复不重抽
- Location: tests\e2e\contracts.spec.ts:212:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByRole('status').filter({ hasText: '解释未完成' })
Expected: visible
Timeout: 30000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" getByRole('status').filter({ hasText: '解释未完成' }) with timeout 30000ms
  - waiting for getByRole('status').filter({ hasText: '解释未完成' })
    - waiting for navigation to finish...
    - navigated to "http://127.0.0.1:4174/#/tarot?draw=cce81c2ccd6b422aacea43bbf3b42103"

```

```yaml
- link "跳到主要内容":
  - /url: "#main"
- complementary "主导航":
  - link "明镜印章 明镜":
    - /url: "#/today"
    - img "明镜印章"
    - text: 明镜
  - paragraph: 10月19日周一
  - navigation:
    - link "今日":
      - /url: "#/today"
    - link "对话":
      - /url: "#/chat"
    - link "命盘":
      - /url: "#/chart"
    - link "塔罗":
      - /url: "#/tarot"
    - link "事项":
      - /url: "#/cases"
    - link "关于我":
      - /url: "#/me"
  - img
  - text: 无痕模式
  - switch "侧栏无痕模式" [disabled]
  - paragraph: 无痕对话正在准备，暂不可用。
  - link "设置":
    - /url: "#/settings"
    - img
    - text: 设置
  - link "功能区预览":
    - /url: "?spaces=demo#/chat"
- main "塔罗":
  - heading "塔罗" [level=1]
  - button "新问题"
  - status
  - heading "如何准备合成面试" [level=2]
  - paragraph: 梳理问题 · 含逆位 · 2026-10-18 · 第1次录入
  - group "本次固定牌阵":
    - figure "当前处境的反思 命运之轮 逆位":
      - button "当前处境的反思：命运之轮，逆位" [disabled]:
        - img "命运之轮 · 逆位"
      - paragraph: 当前处境的反思
      - heading "命运之轮" [level=3]
      - text: 逆位
    - figure "可能忽视的因素 月亮 逆位":
      - button "可能忽视的因素：月亮，逆位" [disabled]:
        - img "月亮 · 逆位"
      - paragraph: 可能忽视的因素
      - heading "月亮" [level=3]
      - text: 逆位
    - figure "可尝试的行动 圣杯八":
      - button "可尝试的行动：圣杯八，正位" [disabled]:
        - img "圣杯八 · 正位"
      - paragraph: 可尝试的行动
      - heading "圣杯八" [level=3]
  - region "每张牌的牌意与反思问题":
    - group: 当前处境的反思 · 命运之轮 · 逆位
    - group: 可能忽视的因素 · 月亮 · 逆位
    - group: 可尝试的行动 · 圣杯八 · 正位
  - region "固定牌阵解读":
    - heading "把牌面放回现实" [level=2]
    - paragraph: 可以补充真实背景再解读，每个已保存版本都可查看。
    - paragraph: 先读静态牌意也可以。解释失败不会更换已经固定的牌。
    - text: 补充现实背景
    - textbox "补充现实背景"
    - button "重试原解读 · 不换牌"
    - button "刷新解读记录"
    - status
  - link "带去对话":
    - /url: "#/chat?case=case_c7928ea368c5686b574ad4c26c15665b&draw=cce81c2ccd6b422aacea43bbf3b42103"
  - button "明确开始新一轮"
  - complementary:
    - heading "以前问过的" [level=2]
    - button "如何准备合成面试 · 2026-10-18 · 查看固定牌阵"
```

# Test source

```ts
  138 |   });
  139 |   await control(request, {});
  140 |   await continueCurrent.click();
  141 |   await expect.poll(() => retries.length).toBe(1);
  142 |   await expect(page.getByText('先核对现实安排，再做一个小行动。').last()).toBeVisible({ timeout: 30000 });
  143 |   expect(chats).toHaveLength(1);
  144 |   expect(retries).toHaveLength(1);
  145 |   await expect
  146 |     .poll(
  147 |       async () => {
  148 |         const complete = await request.get(`/api/runs/${encodeURIComponent(chats[0])}`, { headers });
  149 |         return ((await complete.json()) as { status: string }).status;
  150 |       },
  151 |       { timeout: 30000 },
  152 |     )
  153 |     .toBe('succeeded');
  154 |   await control(request, { delay: 4 });
  155 |   await page.getByRole('textbox', { name: '和明镜说说' }).fill('下一轮的合成安排');
  156 |   await page.getByRole('button', { name: '发送', exact: true }).click();
  157 |   await expect(page.getByRole('button', { name: '停止回答' })).toBeEnabled();
  158 |   await page.getByRole('button', { name: '停止回答' }).click();
  159 |   await expect(page.getByRole('alert')).toContainText('内容没有通过核对');
  160 |   await expect(page.getByText('已停止本轮', { exact: true })).toHaveCount(0);
  161 |   expect(cancels).toHaveLength(1);
  162 |   expect(chats[1]).not.toBe(chats[0]);
  163 | });
  164 |
  165 | test('4 资料明确同意、未知禁用时刻、大约必填分钟、回执确认', async ({ page }) => {
  166 |   await login(page);
  167 |   await page.goto('/#/me?section=profile');
  168 |   await expect(page.getByRole('heading', { name: '核对出生资料' })).toBeVisible();
  169 |   await choose(page, '排盘所用性别', '女');
  170 |   await page.getByRole('textbox', { name: '阳历出生日期', exact: true }).fill('1998-03-12');
  171 |   await choose(page, '出生时刻精度', '时刻未知');
  172 |   await expect(page.getByRole('combobox', { name: '当地出生时间小时' })).toBeDisabled();
  173 |   await choose(page, '出生时刻精度', '大约时刻');
  174 |   await expect(page.getByRole('spinbutton', { name: '前后误差（分钟）' })).toBeVisible();
  175 |   await page.getByRole('textbox', { name: '出生地名称' }).fill('合成地点');
  176 |   await page.getByRole('spinbutton', { name: '经度', exact: true }).fill('116.4');
  177 |   await page.getByRole('spinbutton', { name: '纬度', exact: true }).fill('39.9');
  178 |   await page.getByRole('spinbutton', { name: '出生地 UTC 偏移（小时）' }).fill('8');
  179 |   await expect(page.getByRole('button', { name: '确认并保存资料' })).toBeDisabled();
  180 |   await page.getByRole('checkbox', { name: '我已核对并授权保存出生与性别资料' }).check();
  181 |   await expect(page.getByRole('spinbutton', { name: '前后误差（分钟）' })).toHaveAttribute('required', '');
  182 |   await page.getByRole('spinbutton', { name: '前后误差（分钟）' }).fill('30');
  183 |   await page.getByRole('button', { name: '确认并保存资料' }).click();
  184 |   await expect(page.getByRole('status').filter({ hasText: /已保存.*项经你确认的资料/ })).toBeVisible();
  185 | });
  186 |
  187 | test('5 记忆更正与删除范围只依程序回执，未知提案不可确认', async ({ page }) => {
  188 |   await login(page);
  189 |   await page.goto('/#/me?section=memory');
  190 |   const card = page
  191 |     .getByRole('article', { name: '记忆条目' })
  192 |     .filter({ has: page.locator('textarea:enabled') })
  193 |     .first();
  194 |   await expect(card).toBeVisible();
  195 |   await card.getByRole('textbox', { name: '记忆内容' }).fill('我喜欢傍晚阅读');
  196 |   await card.getByRole('button', { name: '保存记忆更正' }).click();
  197 |   await expect(page.getByRole('status').filter({ hasText: '记忆更正已保存' })).toBeVisible();
  198 |   const corrected = page
  199 |     .getByRole('article', { name: '记忆条目' })
  200 |     .filter({ has: page.locator('textarea:enabled').filter({ hasText: '我喜欢傍晚阅读' }) });
  201 |   await expect(corrected.getByRole('textbox', { name: '记忆内容' })).toBeVisible();
  202 |   await corrected.getByText('删除范围', { exact: true }).click();
  203 |   await corrected.getByRole('combobox', { name: '删除范围' }).click();
  204 |   await page.getByRole('option', { name: '删除整段来源及关联内容' }).click();
  205 |   await corrected.getByRole('checkbox', { name: '确认删除所选范围' }).check();
  206 |   await corrected.getByRole('button', { name: '确认删除所选范围' }).click();
  207 |   await expect(corrected).toHaveCount(0);
  208 |   await page.getByRole('button', { name: '待确认', exact: true }).click();
  209 |   await expect(page.getByRole('button', { name: '确认记忆提案' })).toBeDisabled();
  210 | });
  211 |
  212 | test('6 服务端亲选牌背、固定牌、揭牌与失败解读恢复不重抽', async ({ page, request }) => {
  213 |   await login(page);
  214 |   await page.goto('/#/tarot');
  215 |   await page.getByRole('textbox', { name: '想问什么？' }).fill('如何准备合成面试');
  216 |   await page.getByRole('button', { name: '亲手点选', exact: true }).click();
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
> 238 |   await expect(page.getByRole('status').filter({ hasText: '解释未完成' })).toBeVisible({ timeout: 30000 });
      |                                                                       ^ Error: expect(locator).toBeVisible() failed
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
  317 |   await expect(trigger).toBeFocused();
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
```