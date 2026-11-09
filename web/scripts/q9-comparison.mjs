import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { safeWebPath, webRoot } from './bundle-budget.mjs';

const inputSchema = 'frontend-q9-visual-v1';
const expectedSource = 'c824eb01d62b29d6949a6f533ae29eaad1ef12b01cb55f79db82940064da9601';
const referenceFiles = {
  'mobile-today-light-390.png': '76755cb6846e6e3c1a20aa798efd70f18f764385cae07dc223cd2970fa474627',
  'mobile-chat-light-390.png': 'ac1a75fbacca22c73ae3c03a497eb2324c92bc0803d91d856a6ac672c3a5cbea',
  'mobile-chart-light-390.png': 'd60a285c6fa3829d9a599cbebfe7a3f1006275d57ad2c1ea142a2ad5a8cae8f0',
  'mobile-tarot-light-390.png': 'da33f63a595ba9d71628e6e90fca61bb536fb4d16d123556a95925b6fafab981',
  'desktop-chat-light-1080.png': '27a04a832761703f1ff6911e712c0948eda289f8f04f3ff914f533c0eef3a7e5',
  'components-1-light.png': 'f6133cbc1209b83fa344a16ff9a52fc870aa77edf10746298af0d89bc1d89787',
  'components-2-light.png': '8bf79ca8d4406a12322ea7d51bac0430d935b0b04ca525c2cb191a689d9bca79',
  'components-3-light.png': '5b241db352dd6fd3fba15ab0a8fed3270d931358ddd575635feac4a8e33ffc37',
  'components-4-light.png': '777b36733110a4653ac3e7a10e16e7059e2d4ffc34175bbf14830e44bc3f4974',
  'components-5-light.png': '3607f8184a3f30bc3476c6a9801a8ac130a7bed60e3787a1b846fa5882ff0ccd',
  'components-6-light.png': 'e8c7a99ecfcb56fc26c64c146eb6eb19793574a89512156d99c95de5d4d55e34',
  'overview-light-1760.png': '7a178c0b4843b36ef331ac8fa7e8509a650812b2f424d4d1eacf597dd660fe02',
  'mobile-today-dark-390.png': '2adcfae9d1d762325e2131c03d72738e3dec2628446fe702a285218428e35721',
  'mobile-chat-dark-390.png': '6455b089e0bce94ba8999ba22c96def8e57dd72693e154c7a9267bb3a3d42beb',
  'mobile-chart-dark-390.png': '38e076ff0234deff8442119f9113f2ce5cd6a70bfea6fe152770c2cedfa34aa6',
  'mobile-tarot-dark-390.png': '853bb796461004586f501d1428b9cc017735d36b336b7add4652f979b3518277',
  'desktop-chat-dark-1080.png': 'e363a7b55e974e70e901a3bf3263de088f338c2b3c63d9e68216852e68b638d9',
  'components-1-dark.png': '7caebe09fa04101c57891c550ee2b327afc149a6581ac390ea95b287c4a36603',
  'components-2-dark.png': '311498d6f5ae9eaa57ccb1d2981f7ccfcef58bc59baf1da61aecccc3e9645671',
  'components-3-dark.png': '7a8ab20e8d7d895dd860abfd818b2ed1e01fe291d73b36b832e368cb25f31a4b',
  'components-4-dark.png': 'de5e90362cefda7a0450f2143f8f5bb82e3e47dd1a4571c367260ab3ca8aa88f',
  'components-5-dark.png': 'd2917931e56fd70b3bcf7e8f01f10e1e43096df9f75a4ef02ce5ab4c59fe3454',
  'components-6-dark.png': 'fe9efcfb999c605bfeb8bd3b7f1ec8751034e68b872bc56b543c7c272dd11d07',
  'overview-dark-1760.png': 'd28307daafdce99617897adcffdcb7771fba948662c3b9c437b8e534c5232b57',
};
const heights = { 375: 812, 390: 844, 768: 1024, 1440: 900 };
const digest = (bytes) => createHash('sha256').update(bytes).digest('hex');
const bjt = () => new Date(Date.now() + 8 * 3600000).toISOString().replace('Z', '+08:00');
const escape = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (char) =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[char],
  );
const href = (from, target) => path.relative(from, target).split(path.sep).map(encodeURIComponent).join('/');
const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const hash = (value) => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const text = (value) =>
  typeof value === 'string' &&
  value.trim() &&
  value.length <= 120 &&
  [...value].every((char) => char.codePointAt(0) >= 32);
function require(condition, message) {
  if (!condition) throw new Error(message);
}
function hashMap(value) {
  return object(value) && Object.keys(value).length > 0 && Object.values(value).every(hash);
}

export async function pngInfo(filename, expectedHash) {
  const bytes = await fs.readFile(filename);
  require(bytes.length >= 24 &&
    bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])) &&
    bytes.toString('ascii', 12, 16) === 'IHDR', 'A declared screenshot is not a PNG');
  const sha256 = digest(bytes),
    width = bytes.readUInt32BE(16),
    height = bytes.readUInt32BE(20);
  require(width > 0 && height > 0 && sha256 === expectedHash, 'Screenshot dimensions or SHA256 do not match');
  return { width, height, bytes: bytes.length, sha256 };
}

export function validateManifest(manifest) {
  require(object(manifest) && manifest.schema === inputSchema, 'Expected the frontend Q9 visual manifest');
  require(Number.isInteger(manifest.expected) &&
    manifest.expected > 0 &&
    manifest.captured === manifest.expected &&
    Array.isArray(manifest.captures) &&
    manifest.captures.length === manifest.expected, 'Q9 matrix is incomplete');
  require(typeof manifest.source_commit === 'string' &&
    /^[a-f0-9]{40}$/.test(manifest.source_commit) &&
    hashMap(manifest.source_hashes) &&
    hashMap(manifest.build_hashes), 'Missing frozen source/build provenance');
  const groups = new Map(),
    identities = new Set();
  for (const item of manifest.captures) {
    require(object(item) &&
      text(item.id) &&
      text(item.mode) &&
      ['light', 'dark'].includes(item.theme) &&
      object(item.viewport) &&
      Number.isInteger(item.viewport.width) &&
      Object.hasOwn(heights, item.viewport.width) &&
      heights[item.viewport.width] === item.viewport.height &&
      object(item.checks) &&
      hash(item.sha256) &&
      typeof item.screenshot === 'string', 'Invalid Q9 capture metadata');
    const group = JSON.stringify([item.mode, item.id]),
      combination = `${item.viewport.width}/${item.theme}`;
    const identity = JSON.stringify([group, combination]);
    require(!identities.has(identity), 'Duplicate Q9 capture identity');
    identities.add(identity);
    if (!groups.has(group)) groups.set(group, new Set());
    groups.get(group).add(combination);
  }
  require([...groups.values()].every(
    (combinations) => combinations.size === 8,
  ), 'Each page/state must contain four widths and both themes');
}

async function loadReferences(repository, comparison) {
  const directory = path.join(repository, 'docs/v4/evidence/P10/reference');
  const manifestPath = path.join(directory, 'reference-manifest.json');
  const bytes = await fs.readFile(manifestPath),
    manifest = JSON.parse(bytes.toString('utf8'));
  require(manifest.source === 'docs/v4/08b_设计参考稿.html' &&
    manifest.source_sha256 === expectedSource, 'Reference manifest does not match the pinned original design');
  const source = path.join(repository, manifest.source),
    sourceHash = digest(await fs.readFile(source));
  require(sourceHash === expectedSource, 'Original 08b source changed; review it before comparing');
  require(Array.isArray(manifest.files) &&
    manifest.files.length === Object.keys(referenceFiles).length &&
    new Set(manifest.files).size === Object.keys(referenceFiles).length &&
    manifest.files.every((filename) => Object.hasOwn(referenceFiles, filename)), 'Reference image inventory changed');
  const images = {};
  for (const filename of manifest.files)
    images[filename] = {
      path: href(comparison, path.join(directory, filename)),
      ...(await pngInfo(path.join(directory, filename), referenceFiles[filename])),
    };
  return {
    source: manifest.source,
    source_sha256: sourceHash,
    manifest_sha256: digest(bytes),
    fonts: manifest.fonts,
    native_phone_frame: manifest.native_phone_frame,
    native_desktop_frame: manifest.native_desktop_frame,
    images,
  };
}

export function referenceFor(item) {
  const id = item.id.toLowerCase().replace(/^(?:night|v3|live|static|components?)[-_]/, '');
  const layout = item.viewport.width < 1024 ? 'mobile' : 'desktop';
  const component = /component/i.test(item.mode) || /^components?[-_]/i.test(item.id);
  const canonical = !component && ['today', 'chat', 'chart', 'tarot'].includes(id);
  let category = /(?:bazi|ziwei|astro|chart)/i.test(id)
    ? 'chart'
    : /(?:tarot)/i.test(id)
      ? 'tarot'
      : /(?:today|morning)/i.test(id)
        ? 'today'
        : 'chat';
  let kind = 'shared-framework-only',
    note = '原稿没有本页独立成图；这里只核对共同框架、字体、配色与间距。';
  if (layout === 'desktop') {
    category = 'chat';
    if (canonical && id === 'chat') {
      kind = 'same-page-layout';
      note = '对话页版式参照；桌面原稿按75%缩放绘制，原PNG未经放大，数据与业务状态不同。';
    } else note = '原稿没有该桌面页面成图；左侧为桌面对话公共框架，不作为同页验收。';
  } else if (canonical) {
    kind = 'same-page-layout';
    note = '同类页面版式参照；日期、数据、业务状态与字体不同，不作像素一致性判定。';
  } else if (category !== 'chat' || /chat|private|queue|recovery|guide|onboard|conversation/.test(id)) {
    kind = 'shared-section-framework';
    note = '原稿没有此业务状态或盘种的独立成图；左侧仅为同类页面框架参考，不作为同页验收。';
  }
  if (item.viewport.width === 768) note += ' 768px按规范属于平板手机布局，参照390px原稿放宽边距。';
  return {
    filename: `${layout}-${category}-${item.theme}-${layout === 'mobile' ? 390 : 1080}.png`,
    layout,
    comparison_kind: kind,
    same_page_reference: kind === 'same-page-layout',
    explanation: note,
  };
}

async function captureRecord(item, repository, comparison, references) {
  const normalized = item.screenshot.replaceAll('\\', '/');
  require(normalized.startsWith('web/') &&
    !normalized
      .split('/')
      .some((part) => !part || part === '.' || part === '..'), 'Capture path must be repository-relative inside web');
  require(normalized.endsWith('.png'), 'Capture path must name a PNG');
  const actualPath = await safeWebPath(path.relative(webRoot, path.resolve(repository, normalized)));
  const actual = { path: href(comparison, actualPath), ...(await pngInfo(actualPath, item.sha256)) };
  require(actual.width === item.viewport.width, 'Screenshot width differs from its declared viewport');
  const reference = referenceFor(item);
  require(references.images[reference.filename], 'The selected original reference image is missing');
  return {
    id: item.id,
    mode: item.mode,
    theme: item.theme,
    viewport: item.viewport,
    checks: item.checks,
    ...reference,
    actual,
    reference: { file: reference.filename, ...references.images[reference.filename] },
  };
}

function image(label, item, page) {
  return `<figure><figcaption>${escape(label)} · ${item.width}×${item.height} · <a href="${escape(item.path)}">原图</a></figcaption><div class="image"><img loading="lazy" src="${escape(item.path)}" width="${item.width}" height="${item.height}" alt="${escape(page)} ${escape(label)}"></div></figure>`;
}
function select(label, id, values) {
  return `<label>${escape(label)}<select id="${id}"><option value="">全部</option>${values.map((value) => `<option value="${escape(value)}">${escape(value)}</option>`).join('')}</select></label>`;
}
function indexHtml(items, expected) {
  const pages = [...new Set(items.map((item) => item.id))].sort(),
    modes = [...new Set(items.map((item) => item.mode))].sort();
  const cards = items
    .map(
      (item) =>
        `<section data-page="${escape(item.id)}" data-mode="${escape(item.mode)}" data-theme="${item.theme}" data-width="${item.viewport.width}"><h2>${escape(item.id)} · ${escape(item.mode)} · ${item.viewport.width}px · ${item.theme}</h2><p>${escape(item.explanation)}</p><p class="meta">参考与当前截图均按原图尺寸展示，横向滚动查看；完整检查结果见清单。</p><div class="pair">${image('08b原稿', item.reference, item.id)}${image('当前实现', item.actual, item.id)}</div></section>`,
    )
    .join('\n');
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' file:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'"><title>Q9 全站视觉并排复查</title><style>body{margin:0;padding:24px;background:#f6f1e7;color:#1f1b16;font:16px/1.6 system-ui}header{position:sticky;top:0;z-index:1;background:#f6f1e7;padding:12px 0;border-bottom:1px solid #c9bca6}h1{font-size:24px}h2{font-size:19px}p{margin:8px 0}section{padding:24px 0;border-bottom:1px solid #c9bca6}.meta{font-size:13px;color:#4a433a}.pair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}figure{margin:0;min-width:0}figcaption{padding:8px;background:#fbf8f2}.image{overflow:auto;max-height:85vh;background:#efe8da}img{display:block;width:auto;height:auto;max-width:none}select{min-height:44px;padding:8px;margin:4px}a{color:#1f1b16;text-decoration:underline}[hidden]{display:none!important}:focus-visible{outline:2px solid #b23a2e;outline-offset:2px}</style></head><body><header><h1>Q9 全站视觉并排复查</h1><p>${expected}张当前截图 × 只读08b原稿。375/390/768按手机布局，1440按桌面布局。</p><p>这是完整矩阵与原图索引；无独立原稿的页面已标为框架参考，不代表像素、功能或无障碍自动验收通过。</p><p class="meta">08规范优先于参考稿；原稿使用系统回退字体，当前实现自托管字体。<a href="manifest.json">比较清单</a> · <a href="../manifest.json">原始检查清单</a></p>${select('页面', 'page', pages)}${select('入口', 'mode', modes)}${select('主题', 'theme', ['light', 'dark'])}${select('宽度', 'width', [375, 390, 768, 1440])}<span id="count" role="status" aria-live="polite">${expected}项</span></header><main>${cards}</main><script>const controls=['page','mode','theme','width'].map(id=>document.getElementById(id));function filter(){let count=0;document.querySelectorAll('section').forEach(section=>{section.hidden=controls.some(control=>control.value&&section.dataset[control.id]!==control.value);if(!section.hidden)count++});document.getElementById('count').textContent=count+'项'}controls.forEach(control=>control.addEventListener('change',filter));</script></body></html>`;
}

export async function generateComparison() {
  const repository = path.resolve(webRoot, '..'),
    root = await safeWebPath('evidence/2026-10-21/Q9');
  const inputPath = path.join(root, 'manifest.json'),
    output = await safeWebPath(path.join(root, 'comparison'));
  const bytes = await fs.readFile(inputPath),
    input = JSON.parse(bytes.toString('utf8'));
  validateManifest(input);
  const references = await loadReferences(repository, output),
    items = [];
  for (const item of input.captures) items.push(await captureRecord(item, repository, output, references));
  require(digest(await fs.readFile(inputPath)) === digest(bytes), 'Q9 input changed while being compared');
  const manifest = {
    schema: 'frontend-q9-comparison-v1',
    generated_time_bjt: bjt(),
    status: 'complete',
    expected: input.expected,
    captured: items.length,
    input_sha256: digest(bytes),
    source_commit: input.source_commit,
    source_hashes: input.source_hashes,
    build_hashes: input.build_hashes,
    layout_breakpoint: 1024,
    original_reference: references,
    assurance:
      'Complete screenshot inventory with SHA256 verified at generation and side-by-side reference only; no pixel-equality or accessibility acceptance claim.',
    items,
  };
  // All completeness and image integrity checks finish before any new evidence is written.
  // A prior comparison is preserved; rerunning requires a deliberate new evidence handoff.
  await fs.mkdir(output);
  await fs.writeFile(path.join(output, 'index.html'), indexHtml(items, input.expected), { flag: 'wx' });
  await fs.writeFile(path.join(output, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n', { flag: 'wx' });
  return manifest;
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = await generateComparison();
  console.log(
    JSON.stringify({
      status: result.status,
      captures: result.captured,
      index: 'web/evidence/2026-10-21/Q9/comparison/index.html',
    }),
  );
}
