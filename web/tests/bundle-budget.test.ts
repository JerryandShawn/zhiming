import { createHash } from 'node:crypto';
import { mkdir, mkdtemp, rm, symlink, unlink, writeFile } from 'node:fs/promises';
import { dirname, isAbsolute, relative, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { gzipSync } from 'node:zlib';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

type Entry = { file?: string; imports?: string[]; dynamicImports?: string[]; css?: string[]; assets?: string[] };
type Manifest = Record<string, Entry>;
type FileMeasurement = { file: string; bytes: number; gzip: number; sha256: string };
type Budget = {
  entry: string;
  today_placement: string;
  roots: string[];
  manifest_entries: string[];
  files: FileMeasurement[];
  js_gzip_bytes: number;
  css_gzip_bytes: number;
  gzip_bytes: number;
  limit_bytes: number;
  passed: boolean;
  manifest_sha256: string;
  manifest: Manifest;
  note: string;
};

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const scriptUrl = pathToFileURL(resolve(root, 'scripts/bundle-budget.mjs')).href;
const { calculateBundleBudget, safeWebPath, webRoot } = (await import(scriptUrl)) as {
  calculateBundleBudget: (directory: string) => Promise<Budget>;
  safeWebPath: (value: string) => Promise<string>;
  webRoot: string;
};
const results = resolve(root, 'test-results');
let temporaryRoot: string;
const hash = (body: string) => createHash('sha256').update(body).digest('hex');
const contained = (parent: string, target: string) => {
  const path = relative(parent, target);
  return path !== '' && !isAbsolute(path) && path !== '..' && !path.startsWith(`..${sep}`);
};

beforeAll(async () => {
  await mkdir(results, { recursive: true });
  temporaryRoot = await mkdtemp(resolve(results, 'bundle-budget-fixture-'));
});
afterAll(async () => {
  // Resolve and check the exact unique fixture directory before recursive cleanup.
  if (temporaryRoot && contained(results, resolve(temporaryRoot))) await rm(temporaryRoot, { recursive: true });
});

async function fixture(manifest: Manifest, files: Record<string, string> = {}, html = '<!doctype html><div id="root"></div>') {
  const directory = await mkdtemp(resolve(temporaryRoot, 'build-'));
  const bodies: Record<string, string> = { ...files, 'index.html': html };
  for (const [file, body] of Object.entries(bodies)) {
    const target = resolve(directory, file);
    if (!contained(directory, target)) throw new Error('A fixture write must stay inside its build directory');
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, body);
  }
  const manifestBytes = JSON.stringify(manifest);
  await mkdir(resolve(directory, '.vite'), { recursive: true });
  await writeFile(resolve(directory, '.vite/manifest.json'), manifestBytes);
  return { directory, bodies, manifestBytes };
}

describe('the real bundle budget script measures the populated Today startup graph', () => {
  it('walks the actual index static closure, including CSS and owned assets, without unrelated lazy pages', async () => {
    const build = await fixture(
      {
        'index.html': {
          file: 'assets/index.js',
          imports: ['_react', '_shared'],
          dynamicImports: ['src/pages/Chat.tsx'],
          css: ['assets/index.css'],
        },
        _react: { file: 'assets/react.js' },
        _shared: { file: 'assets/shared.js', imports: ['_react'], assets: ['assets/seal.svg'] },
        'src/pages/Chat.tsx': { file: 'assets/chat.js' },
      },
      {
        'assets/index.js': 'import "./shared.js";',
        'assets/index.css': 'body{margin:0}',
        'assets/react.js': 'export const react = true;',
        'assets/shared.js': 'export const ready = true;',
        'assets/seal.svg': '<svg/>',
      },
    );
    const budget = await calculateBundleBudget(build.directory);
    expect(budget.roots).toEqual(['index.html']);
    expect(budget.manifest_entries).toEqual(['_react', '_shared', 'index.html']);
    expect(budget.files.map((file) => file.file)).toEqual(Object.keys(build.bodies).sort());
    expect(budget.files.some((file) => file.file.includes('chat'))).toBe(false);
  });

  it('retains the eager Today entry bytes when Vite emits no independent Today manifest entry', async () => {
    const build = await fixture(
      { 'index.html': { file: 'assets/index.js', imports: ['_todayData'] }, _todayData: { file: 'assets/day.js' } },
      { 'assets/index.js': 'function LiveToday(){return "filled 今日"}', 'assets/day.js': 'export const day="丙午";' },
    );
    const budget = await calculateBundleBudget(build.directory);
    expect(budget.today_placement).toBe('eager in index closure');
    expect(budget.manifest_entries).toEqual(['_todayData', 'index.html']);
    expect(budget.files.find((file) => file.file === 'assets/index.js')?.bytes).toBe(
      Buffer.byteLength(build.bodies['assets/index.js']),
    );
  });

  it('includes a lazy Today route and every required parent shell with their static dependencies', async () => {
    const build = await fixture(
      {
        'index.html': { file: 'assets/index.js', dynamicImports: ['src/App.tsx'] },
        'src/App.tsx': {
          file: 'assets/app.js',
          imports: ['_shared'],
          dynamicImports: ['src/live/Today.tsx', 'src/pages/Settings.tsx'],
        },
        'src/live/Today.tsx': { file: 'assets/today.js', imports: ['_shared', '_day'] },
        _shared: { file: 'assets/shared.js', css: ['assets/shared.css'] },
        _day: { file: 'assets/day.js' },
        'src/pages/Settings.tsx': { file: 'assets/settings.js', imports: ['_dialog'] },
        _dialog: { file: 'assets/dialog.js' },
      },
      {
        'assets/index.js': 'import("./app.js");',
        'assets/app.js': 'export const shell = true;',
        'assets/today.js': 'export const heading = "今日";',
        'assets/shared.js': 'export const shared = true;',
        'assets/shared.css': '.shell{display:grid}',
        'assets/day.js': 'export const loaded = true;',
      },
    );
    const budget = await calculateBundleBudget(build.directory);
    expect(budget.today_placement).toBe('independent manifest entry');
    expect(budget.roots).toEqual(['index.html', 'src/App.tsx', 'src/live/Today.tsx']);
    expect(budget.manifest_entries).toEqual(['_day', '_shared', 'index.html', 'src/App.tsx', 'src/live/Today.tsx']);
    expect(budget.files.map((file) => file.file)).toEqual(Object.keys(build.bodies).sort());
  });

  it('counts shared files once across duplicate imports, cyclic chunks, CSS and HTML references', async () => {
    const build = await fixture(
      {
        'index.html': { file: 'assets/index.js', imports: ['_shared', '_shared', '_alias'], css: ['assets/shared.css'] },
        _shared: { file: 'assets/shared.js', imports: ['_cycle'], css: ['assets/shared.css'] },
        _alias: { file: 'assets/shared.js' },
        _cycle: { file: 'assets/cycle.js', imports: ['_shared'] },
      },
      {
        'assets/index.js': 'export const entry = true;',
        'assets/shared.js': 'export const shared = true;',
        'assets/cycle.js': 'export const cycle = true;',
        'assets/shared.css': 'body{display:block}',
      },
      '<script src="/assets/index.js"></script><link href="/assets/shared.css?v=1" rel="stylesheet">',
    );
    const budget = await calculateBundleBudget(build.directory);
    const expected = Object.entries(build.bodies).map(([file, body]) => ({
      file,
      bytes: Buffer.byteLength(body),
      gzip: gzipSync(Buffer.from(body)).length,
      sha256: hash(body),
    }));
    expect(budget.files).toEqual(expected.sort((left, right) => left.file.localeCompare(right.file)));
    expect(budget.gzip_bytes).toBe(expected.reduce((total, file) => total + file.gzip, 0));
    expect(budget.js_gzip_bytes).toBe(expected.filter((file) => file.file.endsWith('.js')).reduce((n, file) => n + file.gzip, 0));
    expect(budget.css_gzip_bytes).toBe(expected.find((file) => file.file.endsWith('.css'))?.gzip);
    expect(budget.manifest_sha256).toBe(hash(build.manifestBytes));
    expect(budget.manifest).toEqual(JSON.parse(build.manifestBytes));
    expect(budget.limit_bytes).toBe(200 * 1024);
    expect(budget.passed).toBe(true);
    expect(budget.entry).toContain('static closure');
    expect(budget.note).toContain('not an LCP result');
  });

  it('adds local HTML-only JS/CSS references, decodes names, and excludes external references', async () => {
    const build = await fixture(
      { 'index.html': { file: 'assets/index.js' } },
      { 'assets/index.js': 'export {};', 'assets/extra.js': 'export const extra=true;', 'assets/html.css': '.html{}' },
      '<script src="/assets/%65xtra.js?v=2"></script><link rel="stylesheet" href="assets/html.css"><script src="https://external.invalid/external.js"></script>',
    );
    const budget = await calculateBundleBudget(build.directory);
    expect(budget.files.map((file) => file.file)).toEqual(Object.keys(build.bodies).sort());
    expect(budget.files.some((file) => file.file.includes('external'))).toBe(false);
  });
});

describe('bundle evidence fails closed instead of silently undercounting', () => {
  it('rejects a manifest without an index entry', async () => {
    const build = await fixture({});
    await expect(calculateBundleBudget(build.directory)).rejects.toThrow('Missing index bundle manifest entry');
  });

  it.each(['imports', 'dynamicImports'] as const)('rejects a missing %s entry while tracing required shells', async (kind) => {
    const build = await fixture({
      'index.html': { file: 'assets/index.js', [kind]: ['missing-entry'] },
      'src/live/Today.tsx': { file: 'assets/today.js' },
    });
    await expect(calculateBundleBudget(build.directory)).rejects.toThrow('Missing referenced manifest entry: missing-entry');
  });

  it('rejects a static closure entry with no output file', async () => {
    const build = await fixture({ 'index.html': { file: 'assets/index.js', imports: ['_broken'] }, _broken: {} });
    await expect(calculateBundleBudget(build.directory)).rejects.toThrow('Manifest entry has no file: _broken');
  });

  it.each(['manifest CSS', 'HTML reference'])('rejects missing build bytes from a %s', async (source) => {
    const build = await fixture(
      { 'index.html': { file: 'assets/index.js', ...(source === 'manifest CSS' ? { css: ['assets/missing.css'] } : {}) } },
      { 'assets/index.js': 'export {};' },
      source === 'HTML reference' ? '<script src="/assets/missing.js"></script>' : '<div id="root"></div>',
    );
    await expect(calculateBundleBudget(build.directory)).rejects.toMatchObject({ code: 'ENOENT' });
  });

  it.each(['../escaped.js', resolve(root, '../escaped.js')])('rejects escaping manifest output %s before reading it', async (file) => {
    const build = await fixture({ 'index.html': { file } });
    await expect(calculateBundleBudget(build.directory)).rejects.toThrow('Build manifest path escapes its output');
  });

  it('rejects traversal encoded in an HTML reference after URL decoding', async () => {
    const build = await fixture(
      { 'index.html': { file: 'assets/index.js' } },
      { 'assets/index.js': 'export {};' },
      '<script src="/%2e%2e%2fescaped.js"></script>',
    );
    await expect(calculateBundleBudget(build.directory)).rejects.toThrow('Build manifest path escapes its output');
  });
});

describe('evidence output is restricted to the real web directory', () => {
  it('allows an as-yet nonexistent nested output inside this test fixture', async () => {
    expect(webRoot).toBe(root);
    const output = resolve(temporaryRoot, 'new-evidence/nested/budget.json');
    await expect(safeWebPath(relative(root, output))).resolves.toBe(output);
    await expect(safeWebPath(output)).resolves.toBe(output);
  });

  it.each(['../outside-budget.json', '../web-other/budget.json'])('rejects lexical outside output %s', async (output) => {
    await expect(safeWebPath(output)).rejects.toThrow('Evidence output must stay inside web');
  });

  it('rejects an existing symlink or Windows junction that leads outside web', async () => {
    const link = resolve(temporaryRoot, 'outside-link');
    await symlink(dirname(root), link, process.platform === 'win32' ? 'junction' : 'dir');
    try {
      await expect(safeWebPath(resolve(link, 'not-created/nested/budget.json'))).rejects.toThrow(
        'Evidence output follows a path outside web',
      );
    } finally {
      // Unlink the junction itself; never traverse its destination during cleanup.
      await unlink(link);
    }
  });
});
