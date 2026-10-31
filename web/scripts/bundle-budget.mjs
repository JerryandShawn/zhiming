import fs from 'node:fs/promises';
import path from 'node:path';
import zlib from 'node:zlib';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

export const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const contained = (root, target) => {
  const normalize = (value) => (process.platform === 'win32' ? value.toLowerCase() : value);
  return normalize(target) === normalize(root) || normalize(target).startsWith(normalize(root) + path.sep);
};
export async function safeWebPath(value) {
  const target = path.resolve(webRoot, value);
  if (!contained(webRoot, target)) throw new Error('Evidence output must stay inside web');
  let ancestor = target;
  while (true) {
    try {
      const real = await fs.realpath(ancestor),
        root = await fs.realpath(webRoot);
      if (!contained(root, real)) throw new Error('Evidence output follows a path outside web');
      break;
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      ancestor = path.dirname(ancestor);
    }
  }
  return target;
}
export async function calculateBundleBudget(directory = path.resolve(webRoot, '../static/dist')) {
  const manifestBytes = await fs.readFile(path.join(directory, '.vite/manifest.json'));
  const manifest = JSON.parse(manifestBytes.toString('utf8'));
  const seen = new Set(),
    roots = ['index.html'],
    today = 'src/live/Today.tsx';
  if (!manifest['index.html']) throw new Error('Missing index bundle manifest entry');
  if (manifest[today]) {
    roots.push(today);
    function ancestors(key, visiting = new Set()) {
      if (key === today) return true;
      if (visiting.has(key)) return false;
      if (!manifest[key]) throw new Error(`Missing referenced manifest entry: ${key}`);
      const next = new Set(visiting).add(key);
      let reaches = false;
      for (const child of [...(manifest[key].imports ?? []), ...(manifest[key].dynamicImports ?? [])])
        if (ancestors(child, next)) reaches = true;
      if (reaches) roots.push(key);
      return reaches;
    }
    ancestors('index.html');
  }
  function visit(key) {
    if (seen.has(key)) return;
    const item = manifest[key];
    if (!item) throw new Error(`Missing referenced manifest entry: ${key}`);
    seen.add(key);
    for (const child of item.imports ?? []) visit(child);
  }
  roots.forEach(visit);
  const names = new Set(['index.html']);
  for (const key of seen) {
    const item = manifest[key];
    if (!item.file) throw new Error(`Manifest entry has no file: ${key}`);
    names.add(item.file);
    for (const file of [...(item.css ?? []), ...(item.assets ?? [])]) names.add(file);
  }
  const html = await fs.readFile(path.join(directory, 'index.html'), 'utf8');
  for (const match of html.matchAll(/(?:src|href)=["']([^"']+\.(?:css|js)(?:\?[^"']*)?)["']/g)) {
    const url = new URL(match[1], 'https://build.invalid/');
    if (url.origin === 'https://build.invalid') names.add(decodeURIComponent(url.pathname.slice(1)));
  }
  const files = [];
  for (const file of [...names].sort()) {
    const location = path.resolve(directory, file);
    if (!contained(path.resolve(directory), location)) throw new Error('Build manifest path escapes its output');
    const bytes = await fs.readFile(location);
    files.push({
      file,
      bytes: bytes.length,
      gzip: zlib.gzipSync(bytes).length,
      sha256: createHash('sha256').update(bytes).digest('hex'),
    });
  }
  const total = files.reduce((sum, file) => sum + file.gzip, 0);
  return {
    entry: 'index static closure + independent live Today route and required app shells, if emitted',
    today_placement: manifest[today] ? 'independent manifest entry' : 'eager in index closure',
    roots: [...new Set(roots)].sort(),
    manifest_entries: [...seen].sort(),
    files,
    js_gzip_bytes: files.filter((file) => file.file.endsWith('.js')).reduce((sum, file) => sum + file.gzip, 0),
    css_gzip_bytes: files.filter((file) => file.file.endsWith('.css')).reduce((sum, file) => sum + file.gzip, 0),
    gzip_bytes: total,
    limit_bytes: 200 * 1024,
    passed: total <= 200 * 1024,
    manifest_sha256: createHash('sha256').update(manifestBytes).digest('hex'),
    manifest,
    note: 'Includes HTML, static JS/CSS and manifest-owned assets; font transfers are measured separately. This is not an LCP result.',
  };
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = await calculateBundleBudget();
  const output = await safeWebPath(
    process.env.MINGJING_BUNDLE_OUTPUT ?? process.argv[2] ?? 'evidence/2026-10-18/bundle-budget.json',
  );
  await fs.mkdir(path.dirname(output), { recursive: true });
  await fs.writeFile(output, JSON.stringify(result, null, 2) + '\n');
  console.log(
    JSON.stringify({ gzip_bytes: result.gzip_bytes, limit_bytes: result.limit_bytes, passed: result.passed }),
  );
  if (!result.passed) process.exitCode = 1;
}
