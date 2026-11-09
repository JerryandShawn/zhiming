# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: contracts.spec.ts >> 3 v3 同轮重试与成功恢复；取消接口422时不伪报停止
- Location: tests\e2e\contracts.spec.ts:117:1

# Error details

```
Error: expect(locator).toBeEnabled() failed

Locator: getByRole('button', { name: '停止回答' })
Expected: enabled
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeEnabled" getByRole('button', { name: '停止回答' }) with timeout 5000ms
  - waiting for getByRole('button', { name: '停止回答' })

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
- main "明镜":
  - heading "和明镜对话" [level=1]
  - article "你说的": 这是飞书上的合成历史。 2026/10/17 08:00:00飞书
  - article "你说的": 我喜欢清晨阅读，请记住 2026/10/19 07:47:08
  - article "你说的": 请核对这次合成安排 2026/10/19 07:47:08
  - article "明镜的回答":
    - img "明镜印章"
    - text: 明镜 · 2026/10/19 07:47:09
    - paragraph: 先核对现实安排，再做一个小行动。
    - paragraph: 现有信息仅用于这次讨论。
    - list:
      - listitem: 先确认可用时间。
    - paragraph: 执行后核对实际反馈。
    - group: 专业依据与来源
  - paragraph: 本轮记录已保留，继续会沿用已保存的问题与资料。
  - button "继续原来这一轮"
  - button "明确开始新一轮"
  - button "添加图片":
    - img
  - button "选择本轮图片"
  - textbox "和明镜说说":
    - /placeholder: 和明镜说说…
    - text: 下一轮的合成安排
  - button "发送":
    - img
  - complementary:
    - heading "这轮对话" [level=2]
    - paragraph: 资料与记忆以程序回执为准。
    - link "查看记忆与来源":
      - /url: "#/me?section=memory"
    - text: 无痕模式
    - switch "无痕模式" [disabled]
    - paragraph: 无痕对话正在准备，暂不可用。
```

# Test source

```ts
  57  |
  58  | test('1 稳定 request_id 跨断线与刷新重放，成功后新操作换号', async ({ page }) => {
  59  |   await login(page);
  60  |   const ids: string[] = [];
  61  |   let lose = true;
  62  |   await page.route('**/api/cases', async (route) => {
  63  |     if (route.request().method() !== 'POST') return route.continue();
  64  |     ids.push((route.request().postDataJSON() as { request_id: string }).request_id);
  65  |     const response = await route.fetch();
  66  |     if (lose) {
  67  |       lose = false;
  68  |       return route.abort('failed');
  69  |     }
  70  |     await route.fulfill({ response });
  71  |   });
  72  |   await page.goto('/#/cases');
  73  |   await page.getByRole('button', { name: '新建事项', exact: true }).click();
  74  |   await page.getByRole('textbox', { name: '标题', exact: true }).fill('断线后重放的合成事项');
  75  |   await page.getByRole('textbox', { name: '目标', exact: true }).fill('不要重复建立事项');
  76  |   await page.getByRole('button', { name: '创建事项', exact: true }).click();
  77  |   await expect(page.getByRole('status')).toContainText('尚未确认提交');
  78  |   await page.reload();
  79  |   await page.getByRole('button', { name: '新建事项', exact: true }).click();
  80  |   await expect(page.getByRole('textbox', { name: '标题', exact: true })).toHaveValue('断线后重放的合成事项');
  81  |   await page.getByRole('button', { name: '重试创建原事项' }).click();
  82  |   await expect(page.getByRole('status')).toContainText('事项已保存');
  83  |   expect(ids).toHaveLength(2);
  84  |   expect(ids[0]).toBe(ids[1]);
  85  |   await page.getByRole('textbox', { name: '标题', exact: true }).fill('成功后新的合成事项');
  86  |   await page.getByRole('button', { name: '创建事项', exact: true }).click();
  87  |   await expect(page.getByRole('status')).toContainText('事项已保存');
  88  |   expect(ids[2]).not.toBe(ids[1]);
  89  | });
  90  |
  91  | test('2 真实 revision 冲突保留草稿、禁写、核对最新后再保存', async ({ page, request }) => {
  92  |   await login(page);
  93  |   const title = `冲突核对${Date.now()}`,
  94  |     item = await newCase(request, title);
  95  |   await page.goto('/#/cases');
  96  |   await page.getByRole('button', { name: new RegExp(title) }).click();
  97  |   await page.getByRole('textbox', { name: '事项目标' }).fill('用户尚未保存的草稿');
  98  |   const concurrent = await request.patch(`/api/cases/${item.id}`, {
  99  |     headers,
  100 |     data: {
  101 |       request_id: crypto.randomUUID(),
  102 |       expected_revision: item.revision,
  103 |       changes: { goal: '另一处已保存的目标' },
  104 |     },
  105 |   });
  106 |   expect(concurrent.ok()).toBe(true);
  107 |   await page.getByRole('button', { name: '保存事项更正', exact: true }).click();
  108 |   await expect(page.getByText('内容已在别处更新，草稿已保留。请读取最新版本并核对。')).toBeVisible();
  109 |   await expect(page.getByRole('textbox', { name: '事项目标' })).toHaveValue('用户尚未保存的草稿');
  110 |   await expect(page.getByRole('button', { name: '保存事项更正', exact: true })).toBeDisabled();
  111 |   await page.getByRole('button', { name: '读取最新事项，保留草稿', exact: true }).click();
  112 |   await expect(page.getByRole('button', { name: '保存事项更正', exact: true })).toBeEnabled();
  113 |   await page.getByRole('button', { name: '保存事项更正', exact: true }).click();
  114 |   await expect(page.getByText('事项更正已保存。')).toBeVisible();
  115 | });
  116 |
  117 | test('3 v3 同轮重试与成功恢复；取消接口422时不伪报停止', async ({ page, request }) => {
  118 |   await login(page);
  119 |   await control(request, { failures: 100 });
  120 |   const chats: string[] = [],
  121 |     retries: string[] = [],
  122 |     cancels: string[] = [];
  123 |   page.on('request', (event) => {
  124 |     if (event.method() !== 'POST') return;
  125 |     const url = new URL(event.url());
  126 |     if (url.pathname === '/api/chat') chats.push((event.postDataJSON() as { request_id: string }).request_id);
  127 |     if (url.pathname.endsWith('/retry')) retries.push(url.pathname);
  128 |     if (url.pathname.endsWith('/cancel')) cancels.push(url.pathname);
  129 |   });
  130 |   await page.goto('/#/chat');
  131 |   await page.getByRole('textbox', { name: '和明镜说说' }).fill('请核对这次合成安排');
  132 |   await page.getByRole('button', { name: '发送', exact: true }).click();
  133 |   const continueCurrent = page
  134 |     .locator('.chat-inner > section.ask-card')
  135 |     .getByRole('button', { name: '继续原来这一轮', exact: true });
  136 |   await expect(continueCurrent).toBeVisible({
  137 |     timeout: 30000,
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
> 157 |   await expect(page.getByRole('button', { name: '停止回答' })).toBeEnabled();
      |                                                            ^ Error: expect(locator).toBeEnabled() failed
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
```