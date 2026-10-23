import fs from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const evidence = new URL('../../docs/v4/evidence/P10/', import.meta.url);
const output = new URL('compare/', evidence);
await fs.mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ deviceScaleFactor: 1 });
const frames = new Set(['today', 'chat', 'chart', 'tarot']);
const records = [];
const size = async (file) => {
  const bytes = await fs.readFile(file);
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
};
for (const width of [375, 390, 768, 1440]) for (const theme of ['light', 'dark']) {
  for (const name of ['today', 'chat', 'chart', 'tarot', 'cases', 'me', 'settings']) {
    const samePage = frames.has(name);
    const reference = width === 1440 && name === 'chat' ? `desktop-chat-${theme}-1080.png`
      : `mobile-${samePage ? name : 'today'}-${theme}-390.png`;
    const actual = `${name}-${theme}-${width}.png`;
    const referenceFile = new URL('reference/' + reference, evidence);
    const actualFile = new URL('screenshots/' + actual, evidence);
    const left = await size(referenceFile); const right = await size(actualFile);
    await page.setViewportSize({ width: left.width + right.width + 72, height: Math.max(left.height, right.height) + 150 });
    const note = samePage ? '左为未修改参考稿原图，右为实际界面；桌面非对话页的两栏版式按08文字规范。'
      : '参考稿没有该页成图；左侧仅比对公共框架、字体与配色，右侧版式按08对应章节。';
    const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>截图并排比较</title>
      <style>:root{--paper:#f6f1e7;--ink:#1f1b16}*{box-sizing:border-box}body{margin:0;padding:24px;background:var(--paper);color:var(--ink);font:15px/24px 'Microsoft YaHei',sans-serif}h1{font-size:19px;margin:0 0 8px}p{margin:0 0 16px}section{display:flex;gap:24px;align-items:flex-start}figure{margin:0}figcaption{font-size:13px;margin-bottom:8px}img{display:block}</style>
      <h1>${name} · ${theme} · ${width}</h1><p>${note}</p><section><figure><figcaption>08b参考稿（原始尺寸）</figcaption>
      <img src="${referenceFile.href}" width="${left.width}" height="${left.height}" alt="参考稿"></figure>
      <figure><figcaption>实际页面（原始尺寸）</figcaption><img src="${actualFile.href}" width="${right.width}" height="${right.height}" alt="实际页面"></figure></section></html>`;
    const scratch = new URL('capture.html', output);
    await fs.writeFile(scratch, html); await page.goto(scratch.href);
    await page.locator('img').evaluateAll((images) => Promise.all(images.map((image) => image.decode())));
    await page.screenshot({ path: fileURLToPath(new URL(actual, output)), fullPage: true });
    records.push({ page: name, theme, width, actual, reference, same_page_reference: samePage,
      same_device_reference: (width < 1024 && samePage) || (width === 1440 && name === 'chat') });
  }
}
await fs.unlink(new URL('capture.html', output));
await fs.writeFile(new URL('manifest.json', output), JSON.stringify({
  comparison: 'Original screenshot pixels at native dimensions, without generated or retouched content.', records,
}, null, 2) + '\n');
await browser.close();
console.log(JSON.stringify({ comparisons: records.length }));
