import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { compactFontCss } from './font-css.mjs';

const destination = new URL('../public/fonts/', import.meta.url);
await fs.mkdir(destination, { recursive: true });
const records = [];
let css = '/* Fontsource 5.3.1, unmodified font binaries; SIL Open Font License. */\n';
for (const family of ['noto-sans-sc', 'noto-serif-sc']) {
  const source = new URL(`../node_modules/@fontsource-variable/${family}/`, import.meta.url);
  for (const filename of (await fs.readdir(new URL('files/', source)))
    .filter((name) => name.endsWith('.woff2'))
    .sort()) {
    const bytes = await fs.readFile(new URL(`files/${filename}`, source));
    await fs.writeFile(new URL(filename, destination), bytes);
    records.push({
      file: filename,
      bytes: bytes.length,
      sha256: crypto.createHash('sha256').update(bytes).digest('hex'),
    });
  }
  const sourceCss = await fs.readFile(new URL('index.css', source), 'utf8');
  css += compactFontCss(sourceCss.replaceAll('./files/', './').replaceAll(' SC Variable', ' SC')) + '\n';
  await fs.copyFile(new URL('LICENSE', source), new URL(`${family}-OFL.txt`, destination));
}
const bytes = records.reduce((total, item) => total + item.bytes, 0);
if (bytes > 15 * 1024 * 1024) throw new Error('Font budget exceeds 15 MiB; use documented system fallback');
await fs.writeFile(new URL('fonts.css', destination), css);
await fs.writeFile(
  new URL('manifest.json', destination),
  JSON.stringify(
    {
      source: '@fontsource-variable/noto-{sans,serif}-sc@5.3.1',
      bytes,
      files: records,
    },
    null,
    2,
  ) + '\n',
);
console.log(JSON.stringify({ font_files: records.length, bytes, path: path.basename(destination.pathname) }));
