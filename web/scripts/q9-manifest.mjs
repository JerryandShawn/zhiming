import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { safeWebPath, webRoot } from './bundle-budget.mjs';
import { validateManifest } from './q9-comparison.mjs';

const digest = (bytes) => createHash('sha256').update(bytes).digest('hex');
const json = async (filename) => JSON.parse((await fs.readFile(filename, 'utf8')).replace(/^\uFEFF/, ''));
const require = (condition, message) => {
  if (!condition) throw new Error(message);
};
const [nightId, staticId, v3Id] = process.argv.slice(2);
for (const id of [nightId, staticId, v3Id])
  require(typeof id === 'string' && /^[a-zA-Z0-9-]{1,140}$/.test(id), 'Three safe unique run ids are required');

const root = path.join(webRoot, 'evidence/2026-10-21/Q9');
const nightDirectory = path.join(root, 'night', nightId);
const before = await json(path.join(nightDirectory, 'run.json'));
const closing = await json(path.join(nightDirectory, 'closing.json'));
require(closing.immutable_source_and_build === true, 'Night source/build changed during capture');
require(before.base_HEAD === closing.base_HEAD, 'Night HEAD changed during capture');
require(JSON.stringify(before.files) === JSON.stringify(closing.files), 'Night fingerprints differ');
const head = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: webRoot, encoding: 'utf8' }).trim();
require(head === before.base_HEAD, 'HEAD changed between visual batches');
for (const [filename, expected] of Object.entries(before.files)) {
  require(digest(await fs.readFile(path.resolve(webRoot, filename))) ===
    expected, `Source/build changed between visual batches: ${filename}`);
}

const reports = [];
for (const [name, filename, expected] of [
  ['night', `test-results/q9-night/${nightId}/report.json`, 112],
  ['static', `test-results/q9-static/${staticId}/report.json`, 128],
  ['v3', `evidence/2026-10-21/Q9/v3/${v3Id}/playwright.json`, 56],
]) {
  const bytes = await fs.readFile(path.join(webRoot, filename));
  const report = JSON.parse(bytes.toString('utf8'));
  require(report.stats.expected === expected &&
    report.stats.unexpected === 0 &&
    report.stats.skipped === 0 &&
    report.stats.flaky === 0, `${name} visual report is not completely green`);
  reports.push({ name, path: `web/${filename}`, sha256: digest(bytes), stats: report.stats });
}

async function audits(directory, predicate) {
  const entries = await fs.readdir(directory);
  return Promise.all(
    entries
      .filter(predicate)
      .sort()
      .map((file) => json(path.join(directory, file))),
  );
}
const captures = [];
const groups = [
  ['night', await audits(path.join(nightDirectory, 'audits'), (name) => name.endsWith('.json'))],
  ['static', await audits(path.join(root, 'static', staticId), (name) => /^(static|components)-.*\.json$/.test(name))],
  ['v3', await audits(path.join(root, 'v3', v3Id), (name) => /^Q9-v3-.*\.json$/.test(name))],
];
const emptyArrays = (activity, allowedNonempty = []) =>
  Object.entries(activity).every(
    ([key, value]) => allowedNonempty.includes(key) || (Array.isArray(value) && value.length === 0),
  );
for (const [group, values] of groups) {
  require(values.length === { night: 112, static: 128, v3: 56 }[group], `Missing ${group} audits`);
  for (const audit of values) {
    const inspection = group === 'night' ? audit : group === 'v3' ? audit.checks.inspection : audit.checks;
    require(inspection.document.lang === 'zh-CN' &&
      inspection.document.theme === audit.theme &&
      inspection.document.font_faces > 0 &&
      inspection.document.overflow === false &&
      inspection.violations.length === 0 &&
      inspection.screens.length > 0 &&
      inspection.screens.every(
        (screen) => screen.small_text.length === 0 && screen.cinnabar_uses.length <= 3,
      ), `Visual checks failed in ${group}/${audit.id}`);
    if (group === 'night')
      require(audit.readiness_error === '' && emptyArrays(audit.activity), 'Night readiness/boundary failed');
    if (group === 'static') require(emptyArrays(audit.activity), 'Static boundary failed');
    if (group === 'v3')
      require(audit.checks.ready === true &&
        emptyArrays(audit.checks.boundary, ['arrivals', 'expected_cancellations']) &&
        Array.isArray(audit.checks.boundary.expected_cancellations) &&
        audit.checks.boundary.expected_cancellations.length <= (audit.page === 'tarot' ? 1 : 0) &&
        audit.checks.boundary.expected_cancellations.every(
          (entry) => entry === 'GET /api/cases: net::ERR_ABORTED',
        ), 'v3 readiness/boundary failed');
    const images = audit.images ?? [{ screenshot: audit.screenshot, sha256: audit.sha256, full_page: true }];
    for (const image of images) {
      require(typeof image.screenshot === 'string' &&
        image.screenshot.startsWith('web/') &&
        !image.screenshot.split('/').some((part) => !part || part === '.' || part === '..'), 'Unsafe screenshot path');
      const filename = await safeWebPath(image.screenshot.slice(4));
      require(digest(await fs.readFile(filename)) === image.sha256, 'Screenshot hash differs');
    }
    const first = images[0];
    captures.push({
      id: group === 'v3' ? audit.page : audit.id,
      mode: group === 'v3' ? 'v3' : audit.mode,
      theme: audit.theme,
      viewport: audit.viewport,
      screenshot: first.screenshot,
      sha256: first.sha256,
      images,
      checks: { ...inspection, boundary: group === 'v3' ? audit.checks.boundary : audit.activity },
    });
  }
}
const sourceHashes = Object.fromEntries(
  Object.entries(before.files).filter(([name]) => !name.startsWith('../static/dist/')),
);
const buildHashes = Object.fromEntries(
  Object.entries(before.files).filter(([name]) => name.startsWith('../static/dist/')),
);
const result = {
  schema: 'frontend-q9-visual-v1',
  captured_beijing: new Date(Date.now() + 28800000).toISOString().replace('Z', '+08:00'),
  expected: 296,
  captured: captures.length,
  source_commit: head,
  source_hashes: sourceHashes,
  build_hashes: buildHashes,
  immutable_runtime_source_and_build: true,
  synthetic_only: true,
  counting:
    '14 I.6 per document and inner-scroll viewport; only labelled brand artwork excluded from reading-text size checks',
  reports,
  captures,
};
validateManifest(result);
await fs.writeFile(path.join(root, 'manifest.json'), JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
process.stdout.write(
  JSON.stringify({ captured: captures.length, states: captures.length / 8, source_commit: head }) + '\n',
);
