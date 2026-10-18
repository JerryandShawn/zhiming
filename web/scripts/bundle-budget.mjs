import fs from 'node:fs/promises';
import path from 'node:path';
import zlib from 'node:zlib';

const directory = path.resolve('../static/dist');
const manifest = JSON.parse(await fs.readFile(path.join(directory, '.vite/manifest.json'), 'utf8'));
const seen = new Set();
function visit(key) {
  if (seen.has(key)) return;
  if (!manifest[key]) throw new Error(`Missing bundle manifest entry: ${key}`);
  seen.add(key);
  for (const child of manifest[key]?.imports ?? []) visit(child);
}
visit('index.html');
visit('src/live/Today.tsx');
const files = [];
for (const key of seen) {
  const file = manifest[key]?.file;
  if (!file?.endsWith('.js')) continue;
  const bytes = await fs.readFile(path.join(directory, file));
  files.push({ file, bytes: bytes.length, gzip: zlib.gzipSync(bytes).length });
}
const total = files.reduce((sum, file) => sum + file.gzip, 0);
const result = {
  entry: 'index.html + default live Today route',
  files,
  gzip_bytes: total,
  limit_bytes: 200 * 1024,
  passed: total <= 200 * 1024,
  note: 'Static bundle budget only; this does not establish LCP or real mobile performance.',
};
const output = process.argv[2] ?? 'evidence/2026-10-18/bundle-budget.json';
await fs.mkdir(path.dirname(output), { recursive: true });
await fs.writeFile(output, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ gzip_bytes: total, limit_bytes: result.limit_bytes, passed: result.passed }));
if (!result.passed) process.exitCode = 1;
