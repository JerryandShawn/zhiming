import { readFile, readdir, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, resolve, relative, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const web = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const output = resolve(web, 'evidence/2026-10-19/07');
const actualDirectory = resolve(output, 'screenshots');
const referenceDirectory = resolve(web, '../docs/v4/evidence/P10/reference');
const href = (path) => relative(output, path).split('\\').map(encodeURIComponent).join('/');
const escape = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char],
  );

export async function pngInfo(path) {
  const bytes = await readFile(path);
  if (
    !bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])) ||
    bytes.toString('ascii', 12, 16) !== 'IHDR'
  )
    throw new Error(`Invalid PNG: ${path}`);
  return {
    width: bytes.readUInt32BE(16),
    height: bytes.readUInt32BE(20),
    bytes: bytes.length,
    sha256: createHash('sha256').update(bytes).digest('hex'),
  };
}

async function pngFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const groups = await Promise.all(
    entries.map((entry) =>
      entry.isDirectory()
        ? pngFiles(resolve(directory, entry.name))
        : entry.name.endsWith('.png')
          ? [resolve(directory, entry.name)]
          : [],
    ),
  );
  return groups.flat().sort();
}

function identify(path, dimensions) {
  const name = basename(path, '.png');
  const theme = name.match(/(?:^|[-_])(light|dark)(?:[-_]|$)/)?.[1];
  const width = Number(name.match(/(?:^|[-_])(375|390|768|1440)(?:[-_]|$)/)?.[1]);
  if (!theme || !width || dimensions.width !== width)
    throw new Error(`Missing or inconsistent matrix dimensions/theme: ${name}`);
  const page = name
    .replace(/(?:^|[-_])(light|dark)(?=[-_]|$)/g, '')
    .replace(/(?:^|[-_])(375|390|768|1440)(?=[-_]|$)/g, '')
    .replace(/^07[-_]/, '')
    .replace(/^[-_]+|[-_]+$/g, '');
  return { page, theme, viewportWidth: width, layout: width < 768 ? 'mobile' : 'desktop' };
}

function referenceFor(item, references) {
  const category = /(?:bazi|ziwei|astro|chart)/i.test(item.page)
    ? 'chart'
    : /(?:onboarding|guided|private|chat|conversation)/i.test(item.page)
      ? 'chat'
      : /today/i.test(item.page)
        ? 'today'
        : /tarot/i.test(item.page)
          ? 'tarot'
          : null;
  const same =
    category &&
    references.find(
      (path) =>
        basename(path) === `${item.layout}-${category}-${item.theme}-${item.layout === 'mobile' ? 390 : 1080}.png`,
    );
  if (same) {
    const shared = /ziwei|astro|onboarding|guided|private/i.test(item.page);
    return {
      path: same,
      comparisonKind: shared ? 'shared-section-framework' : 'same-section-layout',
      explanation: shared
        ? '参考仅覆盖共同页面框架；业务状态或盘种不同，不作同页像素验收。'
        : '同类页面布局参考；尺寸、数据和状态可能不同，不作像素通过判定。',
    };
  }
  const framework = references.find(
    (path) => basename(path) === `${item.layout}-chat-${item.theme}-${item.layout === 'mobile' ? 390 : 1080}.png`,
  );
  if (!framework) throw new Error(`No ${item.layout}/${item.theme} framework reference`);
  return {
    path: framework,
    comparisonKind: 'shared-framework-only',
    explanation: '原稿无此页面的独立参考，仅并排核对共同导航、排版和间距；不冒充同页验收。',
  };
}

async function optionalCompositePng(items) {
  let sharp;
  try {
    sharp = (await import('sharp')).default;
  } catch {
    return {
      status: 'skipped',
      reason: 'Existing sharp dependency is unavailable; no package was installed.',
      files: [],
    };
  }
  const chosen = ['mobile', 'desktop'].map((layout) =>
    items.find((item) => item.layout === layout && item.theme === 'light'),
  );
  const files = [];
  for (const item of chosen) {
    if (!item) continue;
    const inputs = [
      resolve(output, decodeURIComponent(item.reference.path)),
      resolve(output, decodeURIComponent(item.actual.path)),
    ];
    const images = await Promise.all(
      inputs.map((path) =>
        sharp(path)
          .resize({ width: 600, height: 2200, fit: 'inside', withoutEnlargement: true })
          .png()
          .toBuffer({ resolveWithObject: true }),
      ),
    );
    const file = `comparison-${item.layout}.png`,
      height = Math.max(...images.map((image) => image.info.height));
    await sharp({ create: { width: 1224, height: height + 24, channels: 4, background: '#e5e7eb' } })
      .composite(images.map((image, index) => ({ input: image.data, left: 8 + index * 608, top: 12 })))
      .png()
      .toFile(resolve(output, file));
    files.push({
      file,
      referenceOnLeft: true,
      actualOnRight: true,
      item: item.page,
      ...(await pngInfo(resolve(output, file))),
    });
  }
  return { status: 'generated', files };
}

export async function generateComparison() {
  const actuals = await pngFiles(actualDirectory),
    references = await pngFiles(referenceDirectory);
  if (actuals.length !== 88)
    throw new Error(`Expected complete 88-image matrix; found ${actuals.length}. No comparison outputs written.`);
  const items = [];
  for (const path of actuals) {
    const dimensions = await pngInfo(path),
      identity = identify(path, dimensions),
      reference = referenceFor(identity, references);
    items.push({
      ...identity,
      comparisonKind: reference.comparisonKind,
      explanation: reference.explanation,
      actual: { path: href(path), ...dimensions },
      reference: { path: href(reference.path), ...(await pngInfo(reference.path)) },
    });
  }
  const pages = [...new Set(items.map((item) => item.page))].sort();
  if (
    pages.length !== 11 ||
    new Set(items.map((item) => `${item.page}/${item.viewportWidth}/${item.theme}`)).size !== 88
  )
    throw new Error('Matrix must contain 11 distinct pages × 4 widths × 2 themes. No comparison outputs written.');
  await mkdir(output, { recursive: true });
  const pngComparisons = await optionalCompositePng(items);
  const manifest = {
    generatedAt: new Date().toISOString(),
    actualCount: items.length,
    referenceSource: href(referenceDirectory),
    assurance: 'Visual side-by-side index only; no pixel-equality or accessibility acceptance claim.',
    pngComparisons,
    items,
  };
  const cards = items
    .map(
      (item) =>
        `<section data-page="${escape(item.page)}" data-theme="${item.theme}" data-width="${item.viewportWidth}"><h2>${escape(item.page)} · ${item.viewportWidth}px · ${item.theme}</h2><p>${escape(item.explanation)}</p><div class="pair">${[
          ['参考', item.reference],
          ['当前实现', item.actual],
        ]
          .map(
            ([label, img]) =>
              `<figure><figcaption>${label} · ${img.width}×${img.height} · <a href="${img.path}">原图</a></figcaption><div class="image"><img loading="lazy" src="${img.path}" width="${img.width}" height="${img.height}" alt="${escape(item.page)} ${label}" /></div></figure>`,
          )
          .join('')}</div></section>`,
    )
    .join('\n');
  const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>夜间前端 88 项并排比较</title><style>body{margin:0;padding:24px;background:#f4f1eb;color:#27231f;font:16px/1.6 system-ui}header{position:sticky;top:0;z-index:1;background:#f4f1eb;padding:12px 0;border-bottom:1px solid #aaa}h1{font-size:24px}h2{font-size:19px}section{padding:24px 0;border-bottom:1px solid #aaa}.pair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}figure{margin:0;min-width:0}figcaption{padding:8px;background:#fff}.image{overflow:auto;max-height:85vh;background:#ddd}img{display:block;width:100%;height:auto;object-fit:contain;object-position:top}select{padding:8px;margin:4px}a{color:#075985}[hidden]{display:none!important}</style><header><h1>88 项当前实现与只读设计参考</h1><p>11 页面 × 375/390/768/1440 × 浅/暗。每张图片标实际尺寸。无独立参考的页面仅比较共同框架，不作同页像素验收；768 使用桌面框架适配参考。</p><label>页面<select id="page"><option value="">全部</option>${pages.map((page) => `<option>${escape(page)}</option>`).join('')}</select></label><label>主题<select id="theme"><option value="">全部</option><option>light</option><option>dark</option></select></label><label>宽度<select id="width"><option value="">全部</option>${[375, 390, 768, 1440].map((width) => `<option>${width}</option>`).join('')}</select></label><span id="count">88 项</span></header><main>${cards}</main><script>const controls=['page','theme','width'].map(id=>document.getElementById(id));function filter(){let count=0;document.querySelectorAll('section').forEach(section=>{section.hidden=controls.some(control=>control.value&&section.dataset[control.id]!==control.value);if(!section.hidden)count++});document.getElementById('count').textContent=count+' 项'}controls.forEach(control=>control.addEventListener('change',filter));</script></html>`;
  await writeFile(resolve(output, 'comparison-manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
  await writeFile(resolve(output, 'index.html'), html);
  return manifest;
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = await generateComparison();
  console.log(
    JSON.stringify({
      actualCount: result.actualCount,
      pngComparisons: result.pngComparisons.status,
      index: relative(web, resolve(output, 'index.html')),
    }),
  );
}
